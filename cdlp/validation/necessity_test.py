"""Necessity test: does a simulated learner need A to understand B?

For an edge A -> B:
1. Write n short questions on B from B's own chunks (with reference answers).
2. A simulated learner who knows only the concepts taught before B, and has NEVER
   learned A, answers them ("without A").
3. The same learner, now also knowing A, answers again ("with A").
4. A separate grader prompt grades each run against the reference answers. The
   grader is blind to which run it is grading.
5. necessity_gap = score with A - score without A, mapped to strong / medium / weak /
   none with the thresholds in configs/default.json. A gap <= 0 is none.

Leakage check: a "without A" answer that still uses A's name, an alias, or a
stemmed form of them is flagged (B's own name is masked first, so "binary search
tree" does not count as using "binary tree"). The leakage rate is reported per edge
and overall; a leaky learner shrinks the gap, so high leakage means the grade
understates necessity.

Every role has its own versioned prompt (prompts/necessity_*_v1.txt). All calls go
through cdlp.shared.llm at temperature 0 with a fixed seed, so they are cached.

    python -m cdlp.validation.necessity_test --relationships outputs/relationships.json \
        --concepts outputs/concepts.json --chunks outputs/chunks.jsonl \
        --out outputs/necessity_test.json [--only r2 r4] [--config path.json]
"""

from __future__ import annotations

import argparse
import json
import os
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


def _ask(prompt: str, version: str, cfg: dict, model: str) -> dict:
    try:
        reply = chat_json(
            prompt,
            model=model,
            temperature=cfg["temperature"],
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


def make_questions(target: dict, chunks: list[dict], cfg: dict, model: str) -> list[dict]:
    version = cfg["prompt_versions"]["questions"]
    values = {
        "target_name": target["name"],
        "chunks": _chunk_block(chunks),
        "n_questions": str(cfg["n_questions"]),
    }
    reply = _ask(_prompt(version, values), version, cfg, model)
    questions = []
    for q in reply.get("questions") or []:
        if isinstance(q, dict) and str(q.get("question", "")).strip():
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


def answer(role: str, values: dict, questions: list[dict], cfg: dict, model: str) -> list[str]:
    version = cfg["prompt_versions"][role]
    listed = "\n".join(f"{i}. {q['question']}" for i, q in enumerate(questions, 1))
    reply = _ask(_prompt(version, {**values, "questions": listed}), version, cfg, model)
    return _answers(reply, len(questions))


def grade(
    target: dict, chunks: list[dict], questions: list[dict], answers: list[str], cfg, model
) -> list[dict]:
    """Blind: the grader never sees which run (with / without A) it is grading."""
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
) -> dict:
    source, target = concepts[relationship["source"]], concepts[relationship["target"]]
    chunk_map = {c["chunk_id"]: c for c in chunks}
    target_chunks = [
        chunk_map[s["chunk_id"]]
        for s in target.get("sources", [])
        if s.get("chunk_id") in chunk_map
    ]
    known = known_before(target["id"], source["id"], concept_list, chunks)
    result = {
        "relationship_id": relationship["id"],
        "source": source["id"],
        "target": target["id"],
        "known_without": [c["id"] for c in known],
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
    without = answer(
        "learner_without",
        {
            **common,
            "forbidden_name": source["name"],
            "forbidden_aliases": ", ".join(source.get("aliases") or []) or "no other names",
        },
        questions,
        cfg,
        model,
    )
    with_a = answer(
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
    grades_without = grade(target, target_chunks, questions, without, cfg, model)
    grades_with = grade(target, target_chunks, questions, with_a, cfg, model)
    score_without = _score(grades_without, cfg["points"])
    score_with = _score(grades_with, cfg["points"])
    gap = round(score_with - score_without, 4)

    leaked = [leaks(a, source, target) for a in without]
    question_leaks = [leaks(q["question"], source, target) for q in questions]
    return {
        **result,
        "status": "ok",
        "necessity": gap_grade(gap, cfg["thresholds"]),
        "necessity_gap": gap,
        "score_with": round(score_with, 4),
        "score_without": round(score_without, 4),
        "leakage": {
            "flagged_answers": [i for i, terms in enumerate(leaked) if terms],
            "terms": leaked,
            "rate": round(sum(bool(t) for t in leaked) / len(leaked), 4),
            # a question that names A shows A to the "without" learner; reported, not fixed
            "questions_naming_source": [i for i, t in enumerate(question_leaks) if t],
        },
        "questions": questions,
        "answers_without": without,
        "answers_with": with_a,
        "grades_without": grades_without,
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
    results = [check_relationship(r, concept_map, concept_list, chunks, cfg, model) for r in edges]
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
    args = parser.parse_args()

    result = run(
        read_json(args.relationships),
        read_json(args.concepts),
        read_jsonl(args.chunks),
        cfg=load_config(args.config),
        only=args.only,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    for r in result["results"]:
        print(f"{r['source']} -> {r['target']}: gap {r['necessity_gap']} ({r['necessity']})")
    print(f"leakage rate: {result['leakage_rate']} -> {args.out}")


if __name__ == "__main__":
    main()
