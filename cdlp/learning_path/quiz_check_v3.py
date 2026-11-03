"""quiz_check_v3: no-LLM checks added to the second model. Settings: configs/quiz_check_v3.json.

The replay of quiz_check_v2 (results/quiz_check_v2_replay_ds101.md) showed the second model
saying "same subject" on all 21 drafts and rarely saying a quote proves nothing. So v3 checks
those two things in code, and the second model only vetoes:

1. Quote match that ignores formatting: LaTeX such as \\log, and line-break hyphens. Sentences
   in a different order still fail.
2. Subject: every concept the question names must be in the quote or its source chunk.
3. Answer support: the quote must contain enough of the correct answer's content words.

Older versions stay usable (generate_quiz_items(check_version="quiz_check_v2")).
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "configs" / "quiz_check_v3.json"
MAX_TERM_WORDS = 6  # the longest name looked for in a question
BIG_O_LIKE = re.compile(r"\b[a-z]\s*\([^()]*\)")


def load_config(path: Path | str = CONFIG_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    """Formatting only: ligatures, LaTeX markup, line-break hyphens, spaces and case."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\\([A-Za-z]+)", r"\1", text)  # \log -> log
    text = re.sub(r"\\[,;:! ]", " ", text)  # LaTeX spacing
    text = re.sub(r"[${}]", "", text)
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)  # la-\nbelled -> labelled
    return " ".join(text.split()).casefold()


def quote_chunk(quote: str, evidence: list[dict]) -> dict | None:
    """The excerpt containing the quote, in the same word order, formatting aside."""
    wanted = normalize(quote)
    return next((c for c in evidence if wanted in normalize(c.get("text", ""))), None)


# ---- subject -------------------------------------------------------------------------


def _squash(text: str) -> str:
    return "".join(re.findall(r"[^\W_]+", text)).casefold()


def _name_forms(squashed: str) -> set[str]:
    """A lowercase name with no separators, plus its plural or singular forms."""
    forms = {squashed, squashed + "s", squashed + "es"}
    if squashed.endswith("y"):
        forms.add(squashed[:-1] + "ies")
    if squashed.endswith(("ix", "ex")):
        forms.add(squashed[:-2] + "ices")
    if squashed.endswith("is"):
        forms.add(squashed[:-2] + "es")
    if squashed.endswith("ies"):
        forms.add(squashed[:-3] + "y")
    if squashed.endswith("ices"):
        forms |= {squashed[:-4] + "ix", squashed[:-4] + "ex"}
    if squashed.endswith("es"):
        forms.add(squashed[:-2])
    if squashed.endswith("s") and not squashed.endswith("ss"):
        forms.add(squashed[:-1])
    return forms


def _usable_alias(alias: str) -> bool:
    """Several words, or one word with a capital after its first letter (BST, SLList)."""
    words = re.findall(r"[^\W_]+", alias)
    return len(words) > 1 or (len(words) == 1 and any(ch.isupper() for ch in words[0][1:]))


def concept_terms(concepts: list[dict]) -> dict[str, str]:
    """{squashed form: concept id}, for every name and every alias that can be trusted."""
    owners: dict[str, set[str]] = {}
    names: dict[str, str] = {}
    for concept in concepts:
        for form in _name_forms(_squash(concept.get("name", ""))):
            if form:
                names.setdefault(form, concept["id"])
        for alias in concept.get("aliases") or []:
            if _usable_alias(alias):
                for form in _name_forms(_squash(alias)):
                    if form:
                        owners.setdefault(form, set()).add(concept["id"])
    aliases = {form: ids.pop() for form, ids in owners.items() if len(ids) == 1}
    return {**aliases, **names}  # a concept's name beats another concept's alias


def named_concepts(question: str, terms: dict[str, str]) -> list[tuple[str, str]]:
    """[(concept id, the words used)], longest name first, so "binary tree" is not "tree"."""
    words = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", question))
    found, start = [], 0
    while start < len(words):
        for end in range(min(start + MAX_TERM_WORDS, len(words)), start, -1):
            concept_id = terms.get("".join(words[start:end]).casefold())
            if concept_id:
                found.append((concept_id, " ".join(words[start:end])))
                start = end
                break
        else:
            start += 1
    return found


def _says(text_words: list[str], phrase: str) -> bool:
    forms = _name_forms(_squash(phrase))
    size = len(re.findall(r"[^\W_]+", phrase)) + 1
    for start in range(len(text_words)):
        for end in range(start + 1, min(start + size, len(text_words)) + 1):
            if "".join(text_words[start:end]) in forms:
                return True
    return False


def missing_subject(
    question: str, quote: str, chunk_text: str, terms: dict[str, str], concepts: dict[str, dict]
) -> str | None:
    """The first concept the question names and the source never mentions, or None."""
    source = re.findall(r"[^\W_]+", normalize(f"{quote} {chunk_text}"))
    for concept_id, used in named_concepts(question, terms):
        name = concepts[concept_id].get("name", concept_id)
        if not _says(source, used) and not _says(source, name):
            return f'question says "{used}" ({concept_id}); not in the quote or its source chunk'
    return None


# ---- answer support ------------------------------------------------------------------


def _stem(word: str) -> str:
    """Light stemming: endings only."""
    for ending, shortest in (("ing", 6), ("ed", 5), ("es", 5), ("s", 4)):
        if word.endswith(ending) and len(word) >= shortest and not word.endswith("ss"):
            return word[: -len(ending)]
    return word


def content_words(text: str, cfg: dict, common_words: frozenset[str]) -> set[str]:
    """Stemmed content words. Numbers are digits; symbols such as O(n + m) stay whole."""
    text = normalize(text)
    symbols = {re.sub(r"\s+", "", m.group(0)) for m in BIG_O_LIKE.finditer(text)}
    text = BIG_O_LIKE.sub(" ", text)
    stop = common_words | set(cfg["extra_stop_words"].split())
    words = set()
    for word in re.findall(r"[^\W_]+", text):
        if word not in stop:
            word = cfg["number_words"].get(word, word)
            words.add(word if word.isdigit() else _stem(word))
    return words | symbols


def answer_support(answer: str, quote: str, cfg: dict, common_words: frozenset[str]) -> float:
    """The share of the answer's content words that the quote contains."""
    wanted = content_words(answer, cfg, common_words)
    if not wanted:
        return 0.0
    return len(wanted & content_words(quote, cfg, common_words)) / len(wanted)
