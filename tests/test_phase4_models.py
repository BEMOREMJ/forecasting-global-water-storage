from pathlib import Path

import numpy as np

from drought_forecasting.phase4_models import (
    BASE_FEATURES,
    cardinal_neighbours,
    catboost_feasibility,
    load_config,
    recency_weights,
    seasonal_fallback,
)


def test_phase4_configuration_is_frozen_and_lean() -> None:
    config = load_config(Path("configs/phase4.yaml"))
    assert tuple(config["features"]) == BASE_FEATURES
    assert config["populations"]["training"]["pooled"] == 2_000_000
    assert config["promotion"]["pooled_rmse_maximum"] == 0.578923


def test_seasonal_fallback_order_and_zero_are_deterministic() -> None:
    values, levels = seasonal_fallback(
        np.array([1.0, np.nan, np.nan, np.nan]),
        np.array([9.0, 2.0, np.nan, np.nan]),
        np.array([8.0, 7.0, 3.0, np.nan]),
    )
    np.testing.assert_array_equal(values, [1.0, 2.0, 3.0, 0.0])
    np.testing.assert_array_equal(levels, [0, 1, 2, 3])


def test_cardinal_neighbours_exclude_diagonals_and_self() -> None:
    assert cardinal_neighbours(10, 20) == ((9, 20), (11, 20), (10, 19), (10, 21))


def test_recency_weight_rule_and_catboost_gate() -> None:
    weights = recency_weights(np.array(["2020-01", "2022-01"], dtype="datetime64[M]"))
    np.testing.assert_allclose(weights, [0.5, 1.0])
    estimate = catboost_feasibility(2_000_000, 13, 1.0)
    assert estimate["safe"] is False
    assert estimate["selected"] == "recency_weighted_lightgbm"
