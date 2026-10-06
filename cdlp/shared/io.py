"""Read and write contract files. Writes are validated, so a module can never
hand a broken file to the next module."""

import json
from pathlib import Path

from cdlp.shared.validate import check, schema_for

EXAMPLES = Path(__file__).parent / "examples"


def read_json(path: Path | str) -> dict:
    return json.loads(Path(path).read_text())


def read_jsonl(path: Path | str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_json(path: Path | str, data: dict) -> None:
    path = Path(path)
    errors = check(data, schema_for(path))
    if errors:
        raise ValueError(f"{path.name} breaks the contract:\n  " + "\n  ".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_jsonl(path: Path | str, rows: list[dict]) -> None:
    path = Path(path)
    schema = schema_for(path)
    for n, row in enumerate(rows, start=1):
        errors = check(row, schema)
        if errors:
            raise ValueError(f"{path.name} row {n} breaks the contract:\n  " + "\n  ".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
