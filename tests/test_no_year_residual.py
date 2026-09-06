from pathlib import Path

import numpy as np

from drought_forecasting.deterministic_baselines import _sha256
from drought_forecasting.lightgbm_benchmark import APPROVED_FEATURES
from drought_forecasting.residual_benchmark import (
    load_config,
    reconstruct,
    residual_target,
)

CONFIG = Path("configs/phase3m3b_no_year_residual.yaml")


def test_exact_ordered_p3m1_schema_minus_only_input_year() -> None:
    config = load_config(CONFIG)
    expected = tuple(feature for feature in APPROVED_FEATURES if feature != "input_year")
    assert tuple(config["features"]) == expected
    assert "input_year" not in config["features"]
    assert "input_calendar_month" in config["features"]
    assert config["schema_control"]["input_month_timestamp_retained_in_provenance"] is True


def test_frozen_identities_populations_and_deterministic_config_identity() -> None:
    config = load_config(CONFIG)
    assert config["identities"]["comparable_rows"] == "2b27c3e0d376965789abab1b1f7dcf3577a8d15b374c03d0a312e39fb4607c0a"
    assert config["populations"]["training"] == {"F01": 1007523, "F02": 992477, "pooled": 2000000}
    assert config["populations"]["validation"] == {"F01": 278059, "F02": 273906, "pooled": 551965}
    assert _sha256(CONFIG) == _sha256(CONFIG)


def test_residual_target_and_reconstruction_unchanged() -> None:
    target = np.array([2.0, -1.0])
    anchor = np.array([1.25, -0.5])
    np.testing.assert_allclose(reconstruct(anchor, residual_target(target, anchor)), target)
