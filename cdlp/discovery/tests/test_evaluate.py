from cdlp.discovery.evaluate import evaluate


def test_evaluate():
    relationships = [
        {
            "source": "a",
            "target": "b",
            "relationship": "DIRECT",
            "strength": "HARD",
        },
        {
            "source": "b",
            "target": "c",
            "relationship": "NONE",
            "strength": "NONE",
        },
    ]

    gold = [
        {
            "source": "a",
            "target": "b",
            "label": "hard",
        },
        {
            "source": "b",
            "target": "c",
            "label": "none",
        },
    ]

    result = evaluate(
        relationships,
        gold,
    )

    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["f1"] == 1.0
    assert result["strength_accuracy"] == 1.0