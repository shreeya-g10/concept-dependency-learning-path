import json
import sys

from cdlp.discovery import candidate_recall, candidates
from cdlp.discovery.candidates import Candidate

GOLD = [
    {"source": "a", "target": "b", "label": "hard"},
    {"source": "b", "target": "c", "label": "soft"},
    {"source": "c", "target": "d", "label": "soft"},
    {"source": "a", "target": "c", "label": "none"},  # negatives don't count
    {"source": "x", "target": "a", "label": "hard"},  # x is not in this course
]


def test_candidate_recall_counts():
    cands = [Candidate("a", "b", []), Candidate("c", "b", [], tied=True), Candidate("a", "d", [])]

    m = candidate_recall.candidate_recall(cands, GOLD, {"a", "b", "c", "d"})

    assert m["gold_positive_edges"] == 4
    assert (m["hits_directed"], m["hits_any_direction"]) == (1, 2)
    assert m["recall_directed"] == 0.25
    assert m["recall_any_direction"] == 0.5
    assert m["missed"] == [{"source": "c", "target": "d", "gold": "soft"}]
    assert m["missing_concepts"] == [{"source": "x", "target": "a", "gold": "hard"}]


def test_cli_writes_per_course_file_with_config(tmp_path, monkeypatch):
    monkeypatch.setattr(candidates, "_embedding_pairs", lambda concepts, threshold=0.55: set())
    gold = tmp_path / "gold.csv"
    gold.write_text("source,target,label\ntrees,binary_tree,hard\nrecursion,binary_tree,soft\n")
    ex = "cdlp/shared/examples"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "candidate_recall",
            *["--concepts", f"{ex}/concepts.json", "--chunks", f"{ex}/chunks.jsonl"],
            *["--gold", str(gold), "--out-dir", str(tmp_path)],
        ],
    )

    candidate_recall.main()

    result = json.loads((tmp_path / "candidate_recall_ds101.json").read_text())
    assert {"model", "prompt_version", "seed", "date", "embedding_model"} <= result["config"].keys()
    assert result["config"]["seed"] == 42
    assert result["metrics"]["recall_directed"] == 1.0
