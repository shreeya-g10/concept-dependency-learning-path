"""Diagnostic quiz item generation and catalog management.

Owner: Vaidehi.
Provides robust quiz item validation, skipping malformed LLM outputs safely
without raising KeyError, and ensuring the correct answer is among the options.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from cdlp.shared.io import write_json

logger = logging.getLogger(__name__)

DEFAULT_QUIZ_ITEMS: dict[str, list[dict[str, Any]]] = {
    "ds101": [
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
    "ml101": [
        {
            "id": "q_linreg_01",
            "concept_id": "linear_regression",
            "question": "What functional form does simple linear regression use to model targets?",
            "options": [
                "y = wx + b",
                "y = 1 / (1 + e^-x)",
                "y = max(0, x)",
                "y = e^x",
            ],
            "answer": "y = wx + b",
            "chunk_id": "ch_ml_lec1_p1_0",
        },
        {
            "id": "q_mse_01",
            "concept_id": "mean_squared_error",
            "question": "How is Mean Squared Error (MSE) computed between predictions and targets?",
            "options": [
                "Average of squared differences",
                "Average of absolute differences",
                "Maximum absolute difference",
                "Cross-entropy loss",
            ],
            "answer": "Average of squared differences",
            "chunk_id": "ch_ml_lec2_p1_0",
        },
        {
            "id": "q_gd_01",
            "concept_id": "gradient_descent",
            "question": "In gradient descent optimization, which direction are parameters updated?",
            "options": [
                "Opposite to the loss gradient",
                "In the direction of the loss gradient",
                "Perpendicular to the loss gradient",
                "Random walk direction",
            ],
            "answer": "Opposite to the loss gradient",
            "chunk_id": "ch_ml_lec3_p1_0",
        },
        {
            "id": "q_logreg_01",
            "concept_id": "logistic_regression",
            "question": "What activation function yields probabilities in logistic regression?",
            "options": [
                "Sigmoid function",
                "ReLU function",
                "Step function",
                "Linear identity function",
            ],
            "answer": "Sigmoid function",
            "chunk_id": "ch_ml_lec4_p1_0",
        },
        {
            "id": "q_reg_01",
            "concept_id": "regularization",
            "question": "What is the primary purpose of L1/L2 regularization in training?",
            "options": [
                "Prevent overfitting by penalizing large weights",
                "Accelerate training step convergence",
                "Increase training set accuracy",
                "Convert classification to regression",
            ],
            "answer": "Prevent overfitting by penalizing large weights",
            "chunk_id": "ch_ml_lec5_p1_0",
        },
        {
            "id": "q_nn_01",
            "concept_id": "neural_networks",
            "question": "What enables multi-layer neural networks to learn non-linear boundaries?",
            "options": [
                "Non-linear activation functions",
                "Linear transformations only",
                "Increasing the learning rate",
                "Removing bias units",
            ],
            "answer": "Non-linear activation functions",
            "chunk_id": "ch_ml_lec6_p1_0",
        },
    ],
}


def validate_quiz_item(item: Any) -> bool:
    """Validate that an item conforms to quiz contract requirements.

    Checks:
    1. Item is a dict.
    2. Has a non-empty question string.
    3. Has at least 2 non-empty options in a list.
    4. Has an answer/correct_answer that is strictly contained within options.
    Never raises KeyError on missing or ill-typed fields.
    """
    if not isinstance(item, dict):
        return False

    question = item.get("question")
    if not isinstance(question, str) or not question.strip():
        return False

    options = item.get("options")
    if not isinstance(options, list) or len(options) < 2:
        return False

    cleaned_options = [str(opt).strip() for opt in options if str(opt).strip()]
    if len(cleaned_options) < 2:
        return False

    # Normalize answer field: may be 'answer' or 'correct_answer'
    answer = item.get("answer") or item.get("correct_answer")
    if not isinstance(answer, str) or not answer.strip():
        return False

    # Verify that the answer is strictly one of the options (case-insensitive fallback)
    ans_clean = answer.strip()
    match = next(
        (opt for opt in cleaned_options if opt.lower() == ans_clean.lower()),
        None,
    )
    if match is None:
        return False

    return True


def clean_and_filter_quiz_items(
    raw_items: list[Any],
    default_concept_id: str = "",
) -> list[dict[str, Any]]:
    """Sanitize and filter quiz items from LLM or external sources.

    Skips bad items missing fields or whose answer is not in options without raising KeyError.
    """
    validated = []
    if not isinstance(raw_items, list):
        return []

    for idx, raw in enumerate(raw_items):
        if not validate_quiz_item(raw):
            continue

        concept_id = raw.get("concept_id") or default_concept_id or "concept"
        item_id = raw.get("id") or raw.get("item_id") or f"q_{concept_id}_{idx + 1:02d}"
        options = [str(opt).strip() for opt in raw.get("options", []) if str(opt).strip()]
        raw_answer = str(raw.get("answer") or raw.get("correct_answer", "")).strip()

        matched_answer = next(
            (opt for opt in options if opt.lower() == raw_answer.lower()),
            raw_answer,
        )

        clean_item: dict[str, Any] = {
            "id": str(item_id),
            "concept_id": str(concept_id),
            "question": str(raw.get("question", "")).strip(),
            "options": options,
            "answer": matched_answer,
        }

        chunk_id = raw.get("chunk_id")
        if chunk_id and isinstance(chunk_id, str):
            clean_item["chunk_id"] = chunk_id

        validated.append(clean_item)

    return validated


def get_quiz_items(course_id: str = "ds101") -> dict[str, Any]:
    """Return validated structured quiz catalog conforming to quiz_items.schema.json."""
    raw_list = DEFAULT_QUIZ_ITEMS.get(course_id, DEFAULT_QUIZ_ITEMS["ds101"])
    clean_items = clean_and_filter_quiz_items(raw_list)

    return {
        "schema_version": "1.0",
        "course_id": course_id,
        "items": clean_items,
    }


def save_quiz_items(path: Path | str, course_id: str = "ds101") -> None:
    """Save quiz items conforming to data contracts."""
    write_json(path, get_quiz_items(course_id=course_id))
