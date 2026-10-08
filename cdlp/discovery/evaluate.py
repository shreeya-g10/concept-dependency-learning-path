import csv
from pathlib import Path


def load_gold(path: Path) -> list[dict]:
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def evaluate(
    relationships: list[dict],
    gold: list[dict],
) -> dict:
    gold_map = {
        (row["source"], row["target"]): row["label"].lower()
        for row in gold
    }

    predicted_map = {
        (row["source"], row["target"]): row
        for row in relationships
    }

    positive_labels = {"hard", "soft"}

    true_positive = 0
    false_positive = 0
    false_negative = 0
    strength_correct = 0

    for pair, label in gold_map.items():
        predicted = predicted_map.get(pair)

        if label in positive_labels:
            if predicted and predicted.get("relationship") == "DIRECT":
                true_positive += 1

                predicted_strength = predicted.get(
                    "strength",
                    "",
                ).lower()

                if predicted_strength == label:
                    strength_correct += 1
            else:
                false_negative += 1
        else:
            if predicted and predicted.get("relationship") == "DIRECT":
                false_positive += 1

    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )

    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )

    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )

    strength_accuracy = (
        strength_correct / true_positive
        if true_positive
        else 0.0
    )

    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "strength_accuracy": strength_accuracy,
    }