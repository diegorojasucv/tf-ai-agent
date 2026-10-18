import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def manifest_path() -> Path:
    return FIXTURES / "manifest_min.json"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    dest = tmp_path / "project"
    shutil.copytree(FIXTURES / "project", dest)
    return dest
