"""LLM-based concept extraction, canonicalization, deduplication, and granularity filtering.

Conforms to cdlp/shared/schemas/concepts.schema.json.

Deduplication compares concept names with sentence embeddings (all-MiniLM-L6-v2, local
files only). If the model cannot be loaded or fails while encoding (e.g. out of GPU
memory while Ollama holds a model), names are compared with character TF-IDF (or word
Jaccard without scikit-learn). That changes which concepts merge, so it is never silent:
extract_concepts_from_chunks() raises DedupError unless allow_tfidf=True (CLI:
--allow-tfidf), prints a loud warning when it is allowed, and records the method used in
concepts.json (`dedup_method`, `dedup_comparisons`; contract 1.7).
"""

from __future__ import annotations

import logging
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from cdlp.shared.io import write_json
from cdlp.shared.llm import chat_json

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).parent / "prompts" / "extract_v1.txt"

# Granularity filter: concepts that are too broad or too fine
TOO_BROAD_SLUGS = {
    "computer_science",
    "programming",
    "introduction",
    "overview",
    "lecture",
    "data_structure",
    "data_structures",
    "algorithm",
    "algorithms",
    "problem",
    "solution",
    "exercise",
    "chapter",
    "section",
    "fundamentals",
}

TOO_FINE_SLUGS = {
    "left_subtree",
    "right_subtree",
    "child_node",
    "parent_node",
    "root_node",
    "leaf_node",
    "temporary_pointer",
    "variable_i",
    "base_case",
    "null_pointer",
    "loop_counter",
    "system_call_stack",
    "call_stack",
    "stack_frame",
}

# Known acronyms in computer science / data structures
ACRONYMS = {
    "bst": "binary_search_tree",
    "avl": "avl_tree",
    "dfs": "depth_first_search",
    "bfs": "breadth_first_search",
    "dag": "directed_acyclic_graph",
}

_EMBEDDER = None
_EMBEDDER_ERROR = ""  # why the embedder is unavailable (for the DedupError message)
# fuzzy name comparisons per method in the current run: embedding / tfidf / jaccard
DEDUP_COUNTS: Counter = Counter()
SCHEMA_VERSION = "1.7"  # 1.7: dedup_method, dedup_comparisons


class DedupError(RuntimeError):
    """Embedding-based deduplication is unavailable and the fallback was not allowed."""


def get_embedder():
    """Load sentence-transformers model if cached locally, else None."""
    global _EMBEDDER, _EMBEDDER_ERROR
    if _EMBEDDER is None:
        model_path = (
            Path.home()
            / ".cache"
            / "huggingface"
            / "hub"
            / "models--sentence-transformers--all-MiniLM-L6-v2"
            / "snapshots"
        )
        if model_path.exists() and any(model_path.iterdir()):
            try:
                from sentence_transformers import SentenceTransformer

                _EMBEDDER = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
            except Exception as exc:
                _EMBEDDER, _EMBEDDER_ERROR = False, f"loading the model failed: {exc}"
        else:
            _EMBEDDER = False
            _EMBEDDER_ERROR = f"all-MiniLM-L6-v2 is not downloaded (no {model_path})"
    return _EMBEDDER if _EMBEDDER is not False else None


def is_llm_available() -> bool:
    """Quick socket check if the configured LLM backend is responsive."""
    try:
        import socket
        from urllib.parse import urlparse

        from cdlp.shared.llm import BASE_URL

        parsed = urlparse(BASE_URL)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 11434
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.05)
        res = s.connect_ex((host, port))
        s.close()
        return res == 0
    except Exception:
        return False


def to_slug(name: str) -> str:
    """Convert a concept name into a lowercase slug conforming to ^[a-z0-9_]+$."""
    name = name.strip().lower()
    # Replace special characters and whitespace with underscores
    slug = re.sub(r"[^a-z0-9]+", "_", name)
    slug = re.sub(r"_+", "_", slug).strip("_")
    # Singularize common plural endings
    if slug.endswith("trees") and slug != "trees":
        slug = slug[:-1]  # binary_trees -> binary_tree
    elif slug.endswith("graphs") and slug != "graphs":
        slug = slug[:-1]
    return slug or "concept"


def is_valid_concept(name: str, slug: str) -> bool:
    """Granularity filter: returns False if concept is too broad, too fine, or trivial."""
    if not name or not slug or len(slug) < 3:
        return False
    if slug in TOO_BROAD_SLUGS or slug in TOO_FINE_SLUGS:
        return False
    if any(broad in slug.split("_") for broad in ["chapter", "lecture", "slide", "homework"]):
        return False
    return True


def are_acronym_match(name1: str, name2: str) -> bool:
    """Check if one name is an acronym or abbreviation of the other."""
    n1, n2 = name1.strip().upper(), name2.strip().upper()
    words1 = [w for w in re.split(r"[^A-Za-z0-9]+", n1) if w]
    words2 = [w for w in re.split(r"[^A-Za-z0-9]+", n2) if w]

    if not words1 or not words2:
        return False

    # Prefix abbreviation (e.g. AVL and AVL Tree)
    if len(words1) == 1 and len(words2) > 1 and words1[0] == words2[0]:
        return True
    if len(words2) == 1 and len(words1) > 1 and words2[0] == words1[0]:
        return True

    if len(words1) == 1 and len(words2) > 1:
        initials2 = "".join(w[0] for w in words2)
        if words1[0] == initials2:
            return True
    if len(words2) == 1 and len(words1) > 1:
        initials1 = "".join(w[0] for w in words1)
        if words2[0] == initials1:
            return True
    return False


def semantic_similarity(name1: str, name2: str) -> float:
    """Compute semantic similarity between two concept names."""
    if name1.lower() == name2.lower():
        return 1.0
    if are_acronym_match(name1, name2):
        return 0.95

    # Check known acronym mappings
    s1, s2 = to_slug(name1), to_slug(name2)
    if s1 == s2:
        return 1.0
    if ACRONYMS.get(s1) == s2 or ACRONYMS.get(s2) == s1:
        return 0.95

    # Check embedding similarity if sentence-transformers is loaded
    embedder = get_embedder()
    if embedder is not None:
        try:
            import numpy as np

            embeddings = embedder.encode([name1, name2])
            norm1 = np.linalg.norm(embeddings[0])
            norm2 = np.linalg.norm(embeddings[1])
            if norm1 > 0 and norm2 > 0:
                DEDUP_COUNTS["embedding"] += 1
                return float(np.dot(embeddings[0], embeddings[1]) / (norm1 * norm2))
        except Exception as exc:  # e.g. out of GPU memory: counted, never silent
            logger.warning("embedding failed for %r / %r (%s); using TF-IDF", name1, name2, exc)
            DEDUP_COUNTS["embedding_failed"] += 1

    # High-precision character n-gram cosine similarity (fast, local, TF-IDF style)
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 4))
        tfidf = vec.fit_transform([name1, name2])
        score = float(cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0])
        DEDUP_COUNTS["tfidf"] += 1
        return score
    except Exception:
        pass

    # Lexical Jaccard fallback
    w1 = set(to_slug(name1).split("_"))
    w2 = set(to_slug(name2).split("_"))
    union = w1 | w2
    DEDUP_COUNTS["jaccard"] += 1
    if not union:
        return 0.0
    return len(w1 & w2) / len(union)


def fallback_extract(chunk: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic fallback concept extraction when LLM is unavailable."""
    text = (chunk.get("heading", "") + " " + chunk.get("text", "")).lower()
    candidates = []

    catalog = [
        (
            "Recursion",
            "recursion",
            ["Recursive Function"],
            "A function defined in terms of itself with base cases.",
        ),
        (
            "Trees",
            "trees",
            ["Tree"],
            "Hierarchical data structure of nodes connected by edges with a root.",
        ),
        (
            "Binary Trees",
            "binary_tree",
            ["Binary Tree"],
            "A tree in which each node has at most two children.",
        ),
        (
            "Binary Search Trees",
            "binary_search_tree",
            ["BST", "Binary Search Tree"],
            "A binary tree ordered left < root < right.",
        ),
        (
            "AVL Trees",
            "avl_tree",
            ["AVL Tree", "AVL"],
            "Self-balancing binary search tree using rotations.",
        ),
        (
            "Graphs",
            "graphs",
            ["Graph"],
            "A non-linear structure of vertices connected by edges, possibly cyclic.",
        ),
        (
            "Heaps",
            "heaps",
            ["Heap", "Binary Heap", "Priority Queue"],
            "A complete binary tree maintaining the heap invariant.",
        ),
    ]

    for name, slug, aliases, desc in catalog:
        slug_matches = slug.replace("_", " ") in text
        name_matches = name.lower() in text
        alias_matches = any(a.lower() in text for a in aliases)
        if slug_matches or name_matches or alias_matches:
            candidates.append(
                {
                    "id": slug,
                    "name": name,
                    "aliases": aliases,
                    "description": desc,
                }
            )

    return candidates


def extract_concepts_from_chunk(chunk: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract candidate concepts from a single text chunk using the LLM prompt."""
    if not is_llm_available():
        return fallback_extract(chunk)

    prompt_template = PROMPT_FILE.read_text(encoding="utf-8")
    prompt = (
        prompt_template.replace("{doc}", str(chunk.get("doc", "")))
        .replace("{page}", str(chunk.get("page", 1)))
        .replace("{heading}", str(chunk.get("heading", "")))
        .replace("{text}", str(chunk.get("text", "")))
    )

    try:
        response = chat_json(
            prompt,
            system="You are an expert curriculum extractor. Return valid JSON only.",
            prompt_version="extract_v1",
        )
        concepts = response.get("concepts", [])
        if isinstance(concepts, list) and len(concepts) > 0:
            return concepts
    except Exception as e:
        logger.info(f"LLM call failed ({e}), falling back to rule-based extraction.")

    return fallback_extract(chunk)


def merge_and_canonicalize(
    raw_concepts_with_sources: list[tuple[dict[str, Any], dict[str, Any]]],
    similarity_threshold: float = 0.85,
) -> list[dict[str, Any]]:
    """Merge duplicate concepts using semantic similarity and aliases."""
    canonical_list: list[dict[str, Any]] = []

    for raw, source in raw_concepts_with_sources:
        name = raw.get("name", "").strip()
        slug = to_slug(raw.get("id") or name)

        if not is_valid_concept(name, slug):
            continue

        aliases = [a.strip() for a in raw.get("aliases", []) if a.strip()]
        description = raw.get("description", "").strip()

        # Find matching existing canonical concept
        matched_idx = -1
        best_sim = 0.0

        for idx, existing in enumerate(canonical_list):
            # 1. Exact slug match
            if existing["id"] == slug or slug in [to_slug(a) for a in existing["aliases"]]:
                matched_idx = idx
                best_sim = 1.0
                break

            # 2. Semantic / acronym similarity
            sim = semantic_similarity(name, existing["name"])
            if sim > best_sim:
                best_sim = sim
                if sim >= similarity_threshold:
                    matched_idx = idx

        if matched_idx >= 0:
            existing = canonical_list[matched_idx]
            # Merge aliases
            existing_aliases = set(existing["aliases"])
            if name != existing["name"]:
                existing_aliases.add(name)
            for a in aliases:
                if a != existing["name"]:
                    existing_aliases.add(a)
            existing["aliases"] = sorted(list(existing_aliases))

            # Pick better / longer description if existing is brief
            if len(description) > len(existing["description"]):
                existing["description"] = description

            # Merge source without duplicate (doc, page)
            source_exists = any(
                s["doc"] == source["doc"] and s["page"] == source["page"]
                for s in existing["sources"]
            )
            if not source_exists:
                existing["sources"].append(source)
        else:
            # Create new canonical entry
            new_entry = {
                "id": slug,
                "name": name,
                "aliases": sorted(list(set(aliases) - {name})),
                "description": description or f"Concepts related to {name}.",
                "sources": [source],
            }
            canonical_list.append(new_entry)

    # Sort deterministically by id
    canonical_list.sort(key=lambda c: c["id"])
    return canonical_list


def fallback_method() -> str:
    """tfidf when scikit-learn is installed, else jaccard (see semantic_similarity)."""
    try:
        import sklearn  # noqa: F401
    except ImportError:
        return "jaccard"
    return "tfidf"


def dedup_method(counts: Counter, embedder_loaded: bool) -> str:
    """embedding / tfidf / jaccard, or mixed when one run used more than one."""
    used = [m for m in ("embedding", "tfidf", "jaccard") if counts.get(m)]
    if not used:  # every merge was exact or an acronym: the method that would have run
        return "embedding" if embedder_loaded else fallback_method()
    return used[0] if len(used) == 1 else "mixed"


def _loud(message: str) -> None:
    bar = "!" * 78
    print(f"\n{bar}\n{message}\n{bar}\n", file=sys.stderr, flush=True)


def extract_concepts_from_chunks(
    chunks: list[dict[str, Any]],
    course_id: str = "ds101",
    similarity_threshold: float = 0.85,
    allow_tfidf: bool = False,
) -> dict[str, Any]:
    """Run extraction across all chunks, merge duplicates, and return concepts contract dict.

    Raises DedupError before any LLM call when the embedding model is unavailable, and
    after merging when an encode failed during the run, unless allow_tfidf is True.
    """
    embedder_loaded = get_embedder() is not None
    if not embedder_loaded:
        message = (
            "Concept deduplication cannot use sentence embeddings: "
            f"{_EMBEDDER_ERROR or 'the model did not load'}.\n"
            "Names would be compared with character TF-IDF instead, which merges different "
            "concepts than an embedding run."
        )
        if not allow_tfidf:
            raise DedupError(
                message + "\nFix the embedding model (download all-MiniLM-L6-v2; stop Ollama "
                "models with `ollama stop <model>` if the GPU is full), or pass --allow-tfidf."
            )
        _loud("WARNING: " + message + "\nAllowed by --allow-tfidf; recorded as dedup_method.")

    raw_with_sources: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for chunk in chunks:
        source_meta = {
            "doc": chunk["doc"],
            "page": chunk["page"],
            "chunk_id": chunk["chunk_id"],
        }
        extracted = extract_concepts_from_chunk(chunk)
        for concept in extracted:
            raw_with_sources.append((concept, source_meta))

    DEDUP_COUNTS.clear()
    canonical_concepts = merge_and_canonicalize(
        raw_with_sources,
        similarity_threshold=similarity_threshold,
    )
    counts = {k: v for k, v in sorted(DEDUP_COUNTS.items()) if v}
    method = dedup_method(DEDUP_COUNTS, embedder_loaded)
    if embedder_loaded and method != "embedding":
        message = (
            f"Embedding failed during deduplication for {counts.get('embedding_failed', 0)} "
            f"name pair(s), which were compared with TF-IDF instead (comparisons: {counts})."
        )
        if not allow_tfidf:
            raise DedupError(
                message + "\nFree the GPU (`ollama stop <model>`) and re-run (LLM answers are "
                "cached), or pass --allow-tfidf."
            )
        _loud("WARNING: " + message + f"\nAllowed by --allow-tfidf; dedup_method={method}.")

    return {
        "schema_version": SCHEMA_VERSION,
        "course_id": course_id,
        "dedup_method": method,
        "dedup_comparisons": counts,
        "concepts": canonical_concepts,
    }


def extract_and_save(
    chunks: list[dict[str, Any]],
    out_file: Path,
    course_id: str = "ds101",
) -> dict[str, Any]:
    """Extract concepts and write concepts.json conforming to contract."""
    concepts_data = extract_concepts_from_chunks(chunks, course_id=course_id)
    write_json(out_file, concepts_data)
    return concepts_data
