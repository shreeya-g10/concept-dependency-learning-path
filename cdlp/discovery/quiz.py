"""Diagnostic quiz item generation and catalog management.

Owner: Vaidehi.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdlp.shared.io import write_json

DEFAULT_QUIZ_ITEMS = {
    "schema_version": "1.0",
    "course_id": "ds101",
    "items": [
        {
            "id": "q_rec_01",
            "concept_id": "recursion",
            "question": "What critical component prevents infinite loop in a recursive function?",
            "options": [
                "A base case",
                "A while loop",
                "A larger input size",
                "A global counter",
            ],
            "answer": "A base case",
            "chunk_id": "ch_ds_lec5_p1_0",
        },
        {
            "id": "q_trees_01",
            "concept_id": "trees",
            "question": "In a connected tree with n nodes, how many edges connect the nodes?",
            "options": ["n - 1", "n", "n + 1", "2n"],
            "answer": "n - 1",
            "chunk_id": "ch_ds_lec6_p1_0",
        },
        {
            "id": "q_bt_01",
            "concept_id": "binary_tree",
            "question": "What is the defining degree constraint on each node in a binary tree?",
            "options": [
                "At most 2 children",
                "Exactly 2 children",
                "At least 2 children",
                "Unlimited children",
            ],
            "answer": "At most 2 children",
            "chunk_id": "ch_ds_lec6_p2_0",
        },
        {
            "id": "q_bst_01",
            "concept_id": "binary_search_tree",
            "question": "In a BST, where are all keys strictly smaller than the root stored?",
            "options": [
                "In the left subtree",
                "In the right subtree",
                "At the leaf nodes only",
                "In any sibling node",
            ],
            "answer": "In the left subtree",
            "chunk_id": "ch_ds_lec7_p1_0",
        },
        {
            "id": "q_avl_01",
            "concept_id": "avl_tree",
            "question": "What invariant must hold for node balance factors in an AVL tree?",
            "options": [
                "-1, 0, or +1",
                "Exactly 0",
                "At most 2",
                "Positive integers only",
            ],
            "answer": "-1, 0, or +1",
            "chunk_id": "ch_ds_lec9_p1_0",
        },
        {
            "id": "q_graphs_01",
            "concept_id": "graphs",
            "question": "Unlike trees, what structural feature can general graphs possess?",
            "options": [
                "Cycles and multiple disjoint components",
                "Strict hierarchical roots only",
                "At most two edges per node",
                "Mandatory acyclic topology",
            ],
            "answer": "Cycles and multiple disjoint components",
            "chunk_id": "ch_ds_lec10_p1_0",
        },
    ],
}


def get_quiz_items(course_id: str = "ds101") -> dict[str, Any]:
    """Return structured quiz catalog conforming to quiz_items.schema.json."""
    data = dict(DEFAULT_QUIZ_ITEMS)
    data["course_id"] = course_id
    return data


def save_quiz_items(path: Path | str, course_id: str = "ds101") -> None:
    """Save quiz items conforming to data contracts."""
    write_json(path, get_quiz_items(course_id=course_id))
