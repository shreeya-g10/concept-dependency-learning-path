"""Modules talk through JSON files only: no module imports another module's code.

`cdlp.shared` is the only package every module may import. Test files are exempt: a few
tests import another module on purpose to pin a deliberately duplicated rule to its original
(e.g. cdlp/validation/tests/test_review_queue.py vs cdlp/learning_path/api.py).
"""

import ast
from pathlib import Path

CDLP = Path(__file__).resolve().parents[1]
MODULES = sorted(p.name for p in CDLP.iterdir() if (p / "__init__.py").exists())


def imported_packages(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        for name in names:
            parts = name.split(".")
            if parts[0] == "cdlp" and len(parts) > 1:
                found.add(parts[1])
    return found


def test_no_cross_module_imports():
    bad = []
    for module in MODULES:
        for path in (CDLP / module).rglob("*.py"):
            if "tests" in path.parts or path.name.startswith("test_"):
                continue
            for other in imported_packages(path) - {module, "shared"}:
                bad.append(f"{path.relative_to(CDLP.parent)} imports cdlp.{other}")
    assert not bad, "\n".join(bad)
