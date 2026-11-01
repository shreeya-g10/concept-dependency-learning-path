"""Necessity test: does a simulated learner need A to understand B?

For an edge A -> B:
1. Write n short questions on B from B's own chunks (with reference answers).
2. A simulated learner who knows only the concepts taught before B, and has NEVER
   learned A, answers them ("without A").
3. Control: the same learner, but KNOWING A (by name only, no description) and with an
   unrelated concept C forbidden instead, using the same prompt. C is neither an
   ancestor nor a descendant of B in the proposed edges (and is not A or B); if no
   such concept exists, a concept from the OTHER course (config cross_course_concepts),
   and only as a last resort a neutral placeholder topic from the config. The control
   absorbs the role-play penalty of being told "you never learned X", which the first
   run showed lowers scores on its own.
4. Diagnostic: the same learner also knowing A ("with A"). It is reported, not used
   in the gap, because it also gets A's description (extra context).
5. A separate grader prompt grades each run against the reference answers. The
   grader is blind to which run it is grading.
6. necessity_gap = control score - score without A, mapped to strong / medium /
   weak / none with the thresholds in configs/default.json. A gap <= 0 is none.

question_format "open" (default) grades free-text answers with the grader prompt;
"mcq" writes 4 options per question (shuffled with a fixed seed so the right one is
not always first) and grades by exact match of the chosen letter, with no grader call.

Leakage check: a "without A" answer that still uses A's name, an alias, or a
stemmed form of them is flagged (B's own name is masked first, so "binary search
tree" does not count as using "binary tree"). The leakage rate is reported per edge
and overall; a leaky learner shrinks the gap, so high leakage means the grade
understates necessity.

Every role has its own versioned prompt (prompts/necessity_*_v1.txt). All calls go
through cdlp.shared.llm at temperature 0 with a fixed seed, so they are cached.

    python -m cdlp.validation.necessity_test --relationships outputs/relationships.json \
        --concepts outputs/concepts.json --chunks outputs/chunks.jsonl \
        --out outputs/necessity_test.json [--only r2 r4] [--config path.json] \
        [--n-questions 3]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from cdlp.shared.io import read_json, read_jsonl
from cdlp.shared.llm import chat_json

load_dotenv()

HERE = Path(__file__).parent
DEFAULT_CONFIG = HERE / "configs" / "default.json"
PROMPT_DIR = HERE / "prompts"
GRADES = ("strong", "medium", "weak", "none")


def load_config(path: Path | str = DEFAULT_CONFIG) -> dict:
    return json.loads(Path(path).read_text())["necessity"]


# ---------------------------------------------------------------------------
# Light stemming, COPIED from cdlp/discovery/candidates.py (modules never import
# each other). Keep the two copies in sync; the tests pin the shared behaviour.
MIN_SHARED_PREFIX = 6
_SUFFIXES = ("ations", "ation", "ively", "ingly", "ings", "ing", "ions", "ion", "ies", "ive")
_SUFFIXES += ("ed", "ly", "es", "s")
_WORD = re.compile(r"[a-z0-9]+")


def _stems(word: str) -> set:
    stems = {word}
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            stems.add(word[: -len(suffix)] + ("y" if suffix == "ies" else ""))
    return stems


def _words_match(a: str, b: str) -> bool:
    if _stems(a) & _stems(b):
        return True
    shared = 0
    for x, y in zip(a, b, strict=False):  # words differ in length
        if x != y:
            break
        shared += 1
    return shared >= MIN_SHARED_PREFIX


# ---------------------------------------------------------------------------


def _terms(concept: dict) -> list[list[str]]:
    names = [concept["name"], *(concept.get("aliases") or []), concept["id"].replace("_", " ")]
    terms = {tuple(_WORD.findall(n.lower())) for n in names}
    return [list(t) for t in terms if t]


def _spans(words: list[str], term: list[str]) -> list[range]:
    n = len(term)
    return [
        range(i, i + n)
        for i in range(len(words) - n + 1)
        if all(_words_match(t, w) for t, w in zip(term, words[i : i + n], strict=True))
    ]


def leaks(answer: str, forbidden: dict, target: dict) -> list[str]:
    """Words of the answer that name the forbidden concept (name, alias or stem), after
    masking the target's own name. Returned as the matched phrases, deduplicated."""
    words = _WORD.findall(str(answer).lower())
    masked = set()
    for term in _terms(target):
        for span in _spans(words, term):
            masked.update(span)
    found = set()
    for term in _terms(forbidden):
        for span in _spans(words, term):
            if not set(span) & masked:
                found.add(" ".join(words[i] for i in span))
    return sorted(found)


def course_positions(concepts: list[dict], chunks: list[dict]) -> dict[str, float]:
    """First chunk index each concept appears in (inf if none): the course order."""
    index = {c["chunk_id"]: i for i, c in enumerate(chunks)}
    return {
        c["id"]: min(
            (index[s["chunk_id"]] for s in c.get("sources", []) if s.get("chunk_id") in index),
            default=float("inf"),
        )
        for c in concepts
    }


def known_before(target_id: str, forbidden_id: str, concepts: list[dict], chunks: list[dict]):
    """Concepts taught before B in course order, never A or B themselves."""
    pos = course_positions(concepts, chunks)
    return [
        c
        for c in sorted(concepts, key=lambda c: (pos[c["id"]], c["id"]))
        if pos[c["id"]] < pos[target_id] and c["id"] not in (target_id, forbidden_id)
    ]


def related_to(target_id: str, relationships: list[dict]) -> set[str]:
    """Ancestors and descendants of B along ALL proposed edges (any decision)."""
    up, down = {}, {}
    for r in relationships:
        up.setdefault(r["target"], set()).add(r["source"])
        down.setdefault(r["source"], set()).add(r["target"])

    def walk(start: str, step: dict) -> set:
        seen, stack = set(), list(step.get(start, ()))
        while stack:
            node = stack.pop()
            if node not in seen:
                seen.add(node)
                stack.extend(step.get(node, ()))
        return seen

    return walk(target_id, up) | walk(target_id, down)


def choose_control(
    source: dict,
    target: dict,
    concept_list: list[dict],
    known: list[dict],
    relationships,
    cfg,
    course_id: str | None = None,
) -> tuple[dict, str]:
    """Pick C: not A, not B, neither ancestor nor descendant of B. Prefer a concept the
    learner would not know anyway (taught after B), so the control and "without A"
    runs list the same known concepts. Fallbacks, in order: a concept of the other
    course (cross_course_concepts[course_id]), then the placeholder topic.
    Returns (concept, kind) with kind in in_course / cross_course / placeholder."""
    excluded = related_to(target["id"], relationships) | {source["id"], target["id"]}
    known_ids = {c["id"] for c in known}
    pool = sorted(
        (c for c in concept_list if c["id"] not in excluded),
        key=lambda c: (c["id"] in known_ids, c["id"]),
    )
    if pool:
        return pool[0], "in_course"
    course_ids = {c["id"] for c in concept_list}
    other = (cfg.get("cross_course_concepts") or {}).get(course_id or "", [])
    other = sorted((c for c in other if c["id"] not in course_ids), key=lambda c: c["id"])
    if other:
        return dict(other[0]), "cross_course"
    return dict(cfg["control_placeholder"]), "placeholder"


def gap_grade(gap: float | None, thresholds: dict) -> str:
    if gap is None or gap <= 0:
        return "none"
    for grade in ("strong", "medium", "weak"):
        if gap >= thresholds[grade] - 1e-9:
            return grade
    return "none"


def _prompt(version: str, values: dict) -> str:
    text = (PROMPT_DIR / f"{version}.txt").read_text()
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def _ask(prompt: str, version: str, cfg: dict, model: str, temperature=None) -> dict:
    try:
        reply = chat_json(
            prompt,
            model=model,
            temperature=cfg["temperature"] if temperature is None else temperature,
            seed=cfg["seed"],
            prompt_version=version,
        )
    except ValueError:  # not JSON
        return {}
    return reply if isinstance(reply, dict) else {}


def _chunk_block(chunks: list[dict]) -> str:
    return "\n".join(f"[{c['chunk_id']}] {c['text']}" for c in chunks) or "(no excerpts)"


def _names(concepts: list[dict]) -> str:
    return ", ".join(f'"{c["name"]}"' for c in concepts) or "nothing else from this course"


LETTERS = "ABCD"


def _mcq(cfg: dict) -> bool:
    return cfg.get("question_format", "open") == "mcq"


def _role(cfg: dict, role: str) -> str:
    """Prompt version for a role in the configured question format."""
    return cfg["prompt_versions"][f"{role}_mcq" if _mcq(cfg) else role]


def _mcq_question(q: dict, cfg: dict, target_id: str, index: int) -> dict | None:
    """Validate one MCQ (4 distinct options, a resolvable correct one) and shuffle it."""
    options = q.get("options")
    if not isinstance(options, list) or len(options) != 4:
        return None
    options = [str(o).strip() for o in options]
    if not all(options) or len({o.casefold() for o in options}) != 4:
        return None
    correct = str(q.get("correct", "")).strip()
    if len(correct) == 1 and correct.upper() in LETTERS:
        right = options[LETTERS.index(correct.upper())]
    else:
        matches = [o for o in options if o.casefold() == correct.casefold()]
        if len(matches) != 1:
            return None
        right = matches[0]
    # deterministic shuffle: same seed, target and question -> same order
    random.Random(f"{cfg['seed']}:{target_id}:{index}").shuffle(options)
    return {
        "question": str(q["question"]).strip(),
        "options": options,
        "answer_letter": LETTERS[options.index(right)],
        "reference_answer": right,
        "chunk_id": str(q.get("chunk_id", "")),
    }


def make_questions(target: dict, chunks: list[dict], cfg: dict, model: str) -> list[dict]:
    version = _role(cfg, "questions")
    values = {
        "target_name": target["name"],
        "chunks": _chunk_block(chunks),
        "n_questions": str(cfg["n_questions"]),
    }
    # question writing may sample (question_temperature) so seeds give different question
    # sets; learners and grader always use cfg["temperature"]
    reply = _ask(
        _prompt(version, values),
        version,
        cfg,
        model,
        temperature=cfg.get("question_temperature", cfg["temperature"]),
    )
    questions = []
    raw = reply.get("questions") if isinstance(reply.get("questions"), list) else []
    for q in raw:
        if not (isinstance(q, dict) and str(q.get("question", "")).strip()):
            continue
        if _mcq(cfg):
            mcq = _mcq_question(q, cfg, target["id"], len(questions))
            if mcq:
                questions.append(mcq)
        else:
            questions.append(
                {
                    "question": str(q["question"]).strip(),
                    "reference_answer": str(q.get("reference_answer", "")).strip(),
                    "chunk_id": str(q.get("chunk_id", "")),
                }
            )
    return questions[: cfg["n_questions"]]


def _answers(reply: dict, n: int) -> list[str]:
    answers = reply.get("answers") if isinstance(reply.get("answers"), list) else []
    answers = [str(a).strip() for a in answers][:n]
    return answers + [""] * (n - len(answers))  # a missing answer is graded incorrect


def _listed(questions: list[dict]) -> str:
    lines = []
    for i, q in enumerate(questions, 1):
        line = f"{i}. {q['question']}"
        if "options" in q:
            line += " " + " ".join(f"{L}) {o}" for L, o in zip(LETTERS, q["options"], strict=True))
        lines.append(line)
    return "\n".join(lines)


def answer(role: str, values: dict, questions: list[dict], cfg: dict, model: str) -> list[str]:
    version = _role(cfg, role)
    listed = _listed(questions)
    reply = _ask(_prompt(version, {**values, "questions": listed}), version, cfg, model)
    return _answers(reply, len(questions))


def chosen_letter(answer_text: str, options: list[str]) -> str | None:
    """'B', '(b)', 'B) ...' -> 'B'; an exact option text -> its letter; else None."""
    text = str(answer_text).strip()
    m = re.match(r"^\(?([A-Da-d])(?:[).:\s]|$)", text)
    if m:
        return m.group(1).upper()
    for letter, option in zip(LETTERS, options, strict=True):
        if text.casefold() == option.casefold():
            return letter
    return None


def grade_mcq(questions: list[dict], answers: list[str]) -> list[dict]:
    """Exact match on the chosen letter; no LLM call."""
    grades = []
    for q, a in zip(questions, answers, strict=True):
        picked = chosen_letter(a, q["options"])
        ok = picked == q["answer_letter"]
        grades.append(
            {
                "grade": "correct" if ok else "incorrect",
                "reason": f"picked {picked or 'nothing'}, key {q['answer_letter']}",
            }
        )
    return grades


def grade(
    target: dict, chunks: list[dict], questions: list[dict], answers: list[str], cfg, model
) -> list[dict]:
    """Blind: the grader never sees which run (with / without A) it is grading."""
    if _mcq(cfg):
        return grade_mcq(questions, answers)
    version = cfg["prompt_versions"]["grader"]
    items = "\n".join(
        f'{i}. Question: "{q["question"]}"\n   Reference: "{q["reference_answer"]}"\n'
        f'   Student: "{a or "(no answer)"}"'
        for i, (q, a) in enumerate(zip(questions, answers, strict=True), 1)
    )
    values = {"target_name": target["name"], "chunks": _chunk_block(chunks), "items": items}
    reply = _ask(_prompt(version, values), version, cfg, model)
    raw = reply.get("grades") if isinstance(reply.get("grades"), list) else []
    grades = []
    for i in range(len(questions)):
        item = raw[i] if i < len(raw) and isinstance(raw[i], dict) else {}
        label = str(item.get("grade", "")).strip().lower()
        label = label if label in cfg["points"] else "incorrect"
        if not answers[i]:
            label = "incorrect"
        grades.append({"grade": label, "reason": str(item.get("reason", "")).strip()})
    return grades


def _score(grades: list[dict], points: dict) -> float:
    return sum(points[g["grade"]] for g in grades) / len(grades) if grades else 0.0


def check_relationship(
    relationship: dict,
    concepts: dict[str, dict],
    concept_list: list[dict],
    chunks: list[dict],
    cfg: dict,
    model: str,
    relationships: list[dict] | None = None,
    course_id: str | None = None,
) -> dict:
    source, target = concepts[relationship["source"]], concepts[relationship["target"]]
    chunk_map = {c["chunk_id"]: c for c in chunks}
    target_chunks = [
        chunk_map[s["chunk_id"]]
        for s in target.get("sources", [])
        if s.get("chunk_id") in chunk_map
    ]
    known = known_before(target["id"], source["id"], concept_list, chunks)
    # the control learner knows A (by name only, so no extra context) and has C banned;
    # it differs from "without A" only in which concept is banned and whether A is known
    pos = course_positions(concept_list, chunks)
    with_source = sorted([*known, source], key=lambda c: (pos[c["id"]], c["id"]))
    control, control_kind = choose_control(
        source, target, concept_list, with_source, relationships or [relationship], cfg, course_id
    )
    known_control = [c for c in with_source if c["id"] != control["id"]]
    result = {
        "relationship_id": relationship["id"],
        "source": source["id"],
        "target": target["id"],
        "known_without": [c["id"] for c in known],
        "control_concept": {"id": control["id"], "name": control["name"], "kind": control_kind},
        "question_format": cfg.get("question_format", "open"),
        "n_questions": cfg["n_questions"],
        "known_control": [c["id"] for c in known_control],
    }
    questions = make_questions(target, target_chunks, cfg, model) if target_chunks else []
    if not questions:
        return {
            **result,
            "status": "no_chunks" if not target_chunks else "no_questions",
            "necessity": "none",
            "necessity_gap": None,
        }

    lesson = (
        f'Your lesson on "{target["name"]}":\n{_chunk_block(target_chunks)}'
        if cfg.get("learner_sees_lesson")
        else ""
    )
    common = {"known_concepts": _names(known), "target_name": target["name"], "lesson": lesson}

    def forbid(concept: dict, known_list: list[dict]) -> list[str]:
        values = {
            **common,
            "known_concepts": _names(known_list),
            "forbidden_name": concept["name"],
            "forbidden_aliases": ", ".join(concept.get("aliases") or []) or "no other names",
        }
        return answer("learner_without", values, questions, cfg, model)

    without = forbid(source, known)
    control_answers = forbid(control, known_control)
    diagnostic = cfg.get("with_a_diagnostic", True)
    with_a = (
        answer(
            "learner_with",
            {
                **common,
                "source_name": source["name"],
                "source_description": source.get("description") or "(no description)",
            },
            questions,
            cfg,
            model,
        )
        if diagnostic
        else []
    )
    grades_without = grade(target, target_chunks, questions, without, cfg, model)
    grades_control = grade(target, target_chunks, questions, control_answers, cfg, model)
    grades_with = grade(target, target_chunks, questions, with_a, cfg, model) if diagnostic else []
    score_without = _score(grades_without, cfg["points"])
    score_control = _score(grades_control, cfg["points"])
    score_with = _score(grades_with, cfg["points"]) if diagnostic else None
    gap = round(score_control - score_without, 4)

    leaked = [leaks(a, source, target) for a in without]
    control_leaked = [leaks(a, control, target) for a in control_answers]
    question_leaks = [
        leaks(" ".join([q["question"], *q.get("options", [])]), source, target) for q in questions
    ]
    return {
        **result,
        "status": "ok",
        "necessity": gap_grade(gap, cfg["thresholds"]),
        "necessity_gap": gap,
        "score_control": round(score_control, 4),
        "score_without": round(score_without, 4),
        # diagnostic only: also gets A's description, so it mixes in extra context
        "score_with": round(score_with, 4) if diagnostic else None,
        "gap_with_minus_without": round(score_with - score_without, 4) if diagnostic else None,
        "leakage": {
            "flagged_answers": [i for i, terms in enumerate(leaked) if terms],
            "terms": leaked,
            "rate": round(sum(bool(t) for t in leaked) / len(leaked), 4),
            # a question (or MCQ option) naming A shows A to the "without" learner
            "questions_naming_source": [i for i, t in enumerate(question_leaks) if t],
            # same check on the control run, against C
            "control_flagged_answers": [i for i, t in enumerate(control_leaked) if t],
        },
        "questions": questions,
        "answers_without": without,
        "answers_control": control_answers,
        "answers_with": with_a,
        "grades_without": grades_without,
        "grades_control": grades_control,
        "grades_with": grades_with,
    }


def run(
    relationships: dict,
    concepts: dict,
    chunks: list[dict],
    *,
    cfg: dict | None = None,
    only: list[str] | None = None,
) -> dict:
    cfg = cfg or load_config()
    model = cfg.get("model") or os.getenv("LLM_VALIDATOR_MODEL", "llama3.1:8b")
    concept_list = concepts["concepts"]
    concept_map = {c["id"]: c for c in concept_list}
    edges = [r for r in relationships["relationships"] if not only or r["id"] in only]
    results = [
        check_relationship(
            r,
            concept_map,
            concept_list,
            chunks,
            cfg,
            model,
            relationships["relationships"],
            relationships.get("course_id"),
        )
        for r in edges
    ]
    answered = [r for r in results if r["status"] == "ok"]
    flagged = sum(len(r["leakage"]["flagged_answers"]) for r in answered)
    total = sum(len(r["answers_without"]) for r in answered)
    return {
        "course_id": relationships["course_id"],
        "model": model,
        "prompt_versions": cfg["prompt_versions"],
        "temperature": cfg["temperature"],
        "seed": cfg["seed"],
        "config": cfg,
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "leakage_rate": round(flagged / total, 4) if total else None,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relationships", type=Path, required=True)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--only", nargs="*", help="relationship ids to test (default: all)")
    parser.add_argument("--n-questions", type=int, help="override the config (default 3)")
    parser.add_argument("--question-format", choices=["open", "mcq"], help="override the config")
    parser.add_argument("--seed", type=int, help="override the config seed")
    parser.add_argument("--no-with-a", action="store_true", help="skip the 'with A' diagnostic")
    parser.add_argument("--question-temperature", type=float, help="override the config")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.n_questions:
        cfg["n_questions"] = args.n_questions
    if args.question_format:
        cfg["question_format"] = args.question_format
    if args.seed is not None:
        cfg["seed"] = args.seed
    if args.no_with_a:
        cfg["with_a_diagnostic"] = False
    if args.question_temperature is not None:
        cfg["question_temperature"] = args.question_temperature
    result = run(
        read_json(args.relationships),
        read_json(args.concepts),
        read_jsonl(args.chunks),
        cfg=cfg,
        only=args.only,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    for r in result["results"]:
        print(
            f"{r['source']} -> {r['target']}: control {r.get('score_control')} "
            f"without {r.get('score_without')} gap {r['necessity_gap']} ({r['necessity']})"
        )
    print(f"leakage rate: {result['leakage_rate']} -> {args.out}")


if __name__ == "__main__":
    main()
