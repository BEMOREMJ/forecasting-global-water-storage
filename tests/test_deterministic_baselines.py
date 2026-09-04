"""Focused Phase 2B tests for deterministic baseline safety and evaluation."""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from drought_forecasting.deterministic_baselines import (
    _create_fold_output,
    _fallback_expression,
    _metric_report,
)
from drought_forecasting.prediction_contract import load_fallback_chains
from drought_forecasting.validation_core import ValidationError
from drought_forecasting.validation_metrics import build_metric_report


def connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE train_data(
            sample_id VARCHAR, time DATE, lat DOUBLE, lon DOUBLE, TWS_t DOUBLE,
            SPEI_01_t DOUBLE, SPEI_03_t DOUBLE, SPEI_06_t DOUBLE, SPEI_12_t DOUBLE,
            SOIL_MOISTURE_t DOUBLE, month_sin DOUBLE, month_cos DOUBLE, target DOUBLE
        );
        INSERT INTO train_data VALUES
          ('a', DATE '2000-01-01', 0, 0, 10, 0,0,0,0,0,0,1, 11),
          ('b', DATE '2000-02-01', 0, 0, 11, 0,0,0,0,0,0,1, 12),
          ('c', DATE '2000-03-01', 0, 0, 12, 0,0,0,0,0,0,1, 13),
          ('d', DATE '2000-04-01', 0, 0, 13, 0,0,0,0,0,0,1, 14),
          ('future', DATE '2000-05-01', 0, 0, 999, 0,0,0,0,0,0,1, 999);
        CREATE TABLE retained(
          fold_id VARCHAR, template_row_id BIGINT, relative_month INTEGER,
          input_month DATE, target_month DATE, lat2 BIGINT, lon2 BIGINT,
          mask_state BOOLEAN, expected_horizon INTEGER, target_value DOUBLE,
          available_tws DOUBLE, tws_provenance VARCHAR, last_observed_month DATE,
          effective_horizon INTEGER
        );
        INSERT INTO retained VALUES
          ('F01',1,0,DATE '2000-04-01',DATE '2000-05-01',0,0,false,1,14,13,'observed',DATE '2000-04-01',1);
        """
    )
    return con


@pytest.mark.parametrize(
    "baseline",
    [
        "global_mean",
        "location_mean",
        "location_calendar_month_climatology",
        "persistence",
        "seasonal_naive",
        "location_trend_seasonal",
    ],
)
def test_each_baseline_produces_full_output_without_future_target_fit(baseline: str) -> None:
    con = connection()
    chain = load_fallback_chains(__import__("pathlib").Path("configs/phase2a_prediction_contract.yaml"))[baseline]
    _create_fold_output(
        con,
        baseline=baseline,
        chain=chain,
        fold_id="F01",
        origin=date(2000, 4, 1),
        retained_relation="retained",
        train_relation="train_data",
        run_id="run-20260904T120000Z-test",
        configuration_id="a" * 64,
    )
    result = con.execute("SELECT prediction, fallback_stage, count(*) OVER () FROM phase2b_output").fetchone()
    assert result[2] == 1
    assert result[0] != 999
    if baseline == "global_mean":
        assert result[0] == pytest.approx(12.0)


def test_exact_month_seasonal_lookup_does_not_use_nearest_or_later_month() -> None:
    con = connection()
    _create_fold_output(
        con,
        baseline="seasonal_naive",
        chain=("seasonal_naive", "persistence", "global_mean"),
        fold_id="F01",
        origin=date(2000, 4, 1),
        retained_relation="retained",
        train_relation="train_data",
        run_id="run-20260904T120000Z-test",
        configuration_id="a" * 64,
    )
    prediction, stage = con.execute("SELECT prediction, fallback_stage FROM phase2b_output").fetchone()
    assert prediction == 13
    assert stage == "persistence"


def test_every_configured_fallback_transition_has_deterministic_sql() -> None:
    chains = load_fallback_chains(__import__("pathlib").Path("configs/phase2a_prediction_contract.yaml"))
    for chain in chains.values():
        prediction, level, reason = _fallback_expression(chain)
        assert prediction.startswith("coalesce(")
        assert level.count("WHEN") == len(chain)
        assert reason.count("WHEN") == len(chain)


def test_invalid_or_exhausted_output_fails_instead_of_dropping_row() -> None:
    con = connection()
    con.execute("UPDATE train_data SET target=NULL, TWS_t=NULL")
    with pytest.raises(ValidationError, match="exhausted|invalid"):
        _create_fold_output(
            con,
            baseline="persistence",
            chain=("persistence", "global_mean"),
            fold_id="F01",
            origin=date(2000, 4, 1),
            retained_relation="retained",
            train_relation="train_data",
            run_id="run-20260904T120000Z-test",
            configuration_id="a" * 64,
        )


def test_metric_aggregation_preserves_all_diagnostic_counts() -> None:
    rows = []
    for horizon in range(1, 8):
        rows.append(
            {
                "target": 0.0, "prediction": float(horizon), "fold_id": "F01",
                "horizon": horizon, "mask_state": "observed", "latitude": 0.0,
                "SPEI_01_t": 0.0, "SPEI_03_t": 0.0, "SPEI_06_t": 0.0,
                "SPEI_12_t": 0.0, "mask_policy_id": "mask-exact-complete-v1",
                "tws_provenance_policy_id": "tws-observed-only-v1",
                "recursion_policy_id": "recursion-disabled-v1",
                "metric_policy_id": "rmse-row-pooled-v1",
            }
        )
    compact = _metric_report(build_metric_report(rows))
    assert compact["pooled"]["count"] == 7
    assert sum(value["count"] for value in compact["horizon"].values()) == 7
    assert sum(value["count"] for value in compact["mask_state"].values()) == 7
    assert sum(value["count"] for value in compact["latitude_band"].values()) == 7
    assert all(sum(value["count"] for value in bins.values()) == 7 for bins in compact["spei"].values())
