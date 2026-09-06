from pathlib import Path

import pytest

from drought_forecasting.recent_diagnostic import load_config
from drought_forecasting.validation_core import ValidationError


def test_registered_p3d1_config_is_single_execution_and_two_million_rows() -> None:
    config = load_config(Path("configs/phase3d1_recent_diagnostic.yaml"))
    assert config["historical_origin"].isoformat() == "2014-10-01"
    assert config["sampling"]["cap"] == 992_477
    assert sum(config["sampling"]["retained_by_horizon"].values()) == 2_000_000
    assert config["execution_limit"] == 1


def test_rejects_repeatable_execution_contract(tmp_path: Path) -> None:
    config = Path("configs/phase3d1_recent_diagnostic.yaml").read_text(encoding="utf-8")
    path = tmp_path / "bad.yaml"
    path.write_text(config.replace("execution_limit: 1", "execution_limit: 2"), encoding="utf-8")
    with pytest.raises(ValidationError, match="single-execution"):
        load_config(path)
