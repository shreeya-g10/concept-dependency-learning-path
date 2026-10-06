from pathlib import Path

import pytest

from cdlp.shared.validate import check_file

EXAMPLES = sorted((Path(__file__).parent / "examples").iterdir())


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_matches_contract(path):
    assert check_file(path) == []
