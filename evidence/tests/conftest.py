from pathlib import Path

import pytest

from trace_evidence import constants
from trace_evidence.dataset import write_dataset


@pytest.fixture()
def default_seed() -> int:
    """The seed used by the reproducible default dataset."""
    return constants.DEFAULT_SEED


@pytest.fixture()
def dataset_dir(tmp_path: Path, default_seed: int) -> Path:
    """Build a fresh dataset inside a temp directory (never inside the repo)."""
    out = tmp_path / "datasets"
    write_dataset(out, seed=default_seed)
    return out
