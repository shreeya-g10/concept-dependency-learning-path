"""Check JSON / JSONL files against the team's data contracts.

Usage:
    python -m cdlp.shared.validate outputs/concepts.json outputs/chunks.jsonl
    python -m cdlp.shared.validate cdlp/shared/examples/*

The schema is picked from the file name ending, so `mock_concepts.json` is
checked as `concepts.json`.
"""

import json
import sys
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).parent / "schemas"

# file-name ending -> schema name
FILE_SCHEMAS = {
    "chunks.jsonl": "chunk",
    "concepts.json": "concepts",
    "relationships.json": "relationships",
    "validated_graph.json": "validated_graph",
    "quiz_items.json": "quiz_items",
    "sim_students.json": "sim_students",
    "student_state.json": "student_state",
    "learning_path.json": "learning_path",
}


@lru_cache
def _validator(schema: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMA_DIR / f"{schema}.schema.json").read_text()))


def schema_for(path: Path) -> str:
    for ending, schema in FILE_SCHEMAS.items():
        if path.name.endswith(ending):
            return schema
    raise ValueError(f"No contract matches file name {path.name!r}")


def check(data, schema: str) -> list[str]:
    """Return a list of human-readable errors (empty list = valid)."""
    return [
        f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
        for e in _validator(schema).iter_errors(data)
    ]


def check_file(path: Path, schema: str | None = None) -> list[str]:
    schema = schema or schema_for(path)
    if path.suffix == ".jsonl":
        errors = []
        for n, line in enumerate(path.read_text().splitlines(), start=1):
            if line.strip():
                errors += [f"line {n}: {e}" for e in check(json.loads(line), schema)]
        return errors
    return check(json.loads(path.read_text()), schema)


def main(argv: list[str]) -> int:
    failed = False
    for arg in argv:
        path = Path(arg)
        errors = check_file(path)
        status = "OK" if not errors else "FAIL"
        print(f"[{status}] {path}")
        for e in errors:
            print(f"    {e}")
        failed |= bool(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
