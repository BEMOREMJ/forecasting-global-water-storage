"""Focused Phase 2C provenance and deterministic-sampling tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from drought_forecasting.horizon_examples import (
    append_stratified_sample,
    create_fold_candidates,
    load_config,
    retained_target_identity,
    validate_examples,
)
from drought_forecasting.validation_core import ValidationError


def fixture_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE phase2c_train(
          lat2 INTEGER, lon2 INTEGER, time DATE, lat DOUBLE, lon DOUBLE, TWS_t DOUBLE,
          SPEI_01_t DOUBLE, SPEI_03_t DOUBLE, SPEI_06_t DOUBLE, SPEI_12_t DOUBLE,
          SOIL_MOISTURE_t DOUBLE, month_sin DOUBLE, month_cos DOUBLE, target DOUBLE
        );
        INSERT INTO phase2c_train VALUES
          (0,0,DATE '2000-01-01',0,0,1,0,0,0,0,0,0,1,2),
          (0,0,DATE '2000-02-01',0,0,2,0,0,0,0,0,0,1,3),
          (0,0,DATE '2000-03-01',0,0,3,0,0,0,0,0,0,1,4),
          (0,0,DATE '2000-04-01',0,0,4,0,0,0,0,0,0,1,5),
          (0,0,DATE '2000-05-01',0,0,999,0,0,0,0,0,0,1,999),
          (2,2,DATE '2000-04-01',1,1,8,0,0,0,0,0,0,1,9);
        """
    )
    return con


def test_configuration_freezes_cap_seed_horizons_and_quotas() -> None:
    config = load_config(Path("configs/phase2c_horizon_examples.yaml"))
    assert config["sampling"]["seed"] == 20260904
    assert config["sampling"]["cap"] == 2_000_000
    assert config["horizons"] == list(range(1, 8))


def test_exact_calendar_sources_cutoff_and_location_are_enforced() -> None:
    con = fixture_connection()
    create_fold_candidates(
        con, fold_id="F01", cutoff=date(2000, 4, 1), output_relation="candidates"
    )
    rows = con.execute(
        """
        SELECT target_month,effective_horizon,tws_source_month,last_observed_tws,
               location_id,covariate_location_id,tws_source_location_id
        FROM candidates ORDER BY target_month,effective_horizon
        """
    ).fetchall()
    assert rows
    assert all(row[0] <= date(2000, 4, 1) for row in rows)
    assert all((row[0].year-row[2].year)*12+row[0].month-row[2].month == row[1] for row in rows)
    assert all(row[4] == row[5] == row[6] for row in rows)
    assert all(row[3] != 999 for row in rows)


def test_missing_exact_month_is_not_replaced_by_adjacent_row() -> None:
    con = fixture_connection()
    con.execute("DELETE FROM phase2c_train WHERE time=DATE '2000-02-01'")
    create_fold_candidates(
        con, fold_id="F01", cutoff=date(2000, 4, 1), output_relation="candidates"
    )
    assert con.execute(
        "SELECT count(*) FROM candidates WHERE tws_source_month=DATE '2000-02-01'"
    ).fetchone()[0] == 0
    assert con.execute(
        "SELECT count(*) FROM candidates WHERE target_month=DATE '2000-04-01' AND effective_horizon=2"
    ).fetchone()[0] == 0


def test_validation_targets_and_later_tws_cannot_enter_training() -> None:
    con = fixture_connection()
    create_fold_candidates(
        con, fold_id="F01", cutoff=date(2000, 4, 1), output_relation="candidates"
    )
    assert con.execute("SELECT max(target_month) FROM candidates").fetchone()[0] == date(2000, 4, 1)
    assert con.execute("SELECT max(tws_source_month <= input_month) FROM candidates").fetchone()[0]
    assert con.execute("SELECT count(*) FROM candidates WHERE last_observed_tws=999").fetchone()[0] == 0


def _sample_identity() -> str:
    con = fixture_connection()
    create_fold_candidates(
        con, fold_id="F01", cutoff=date(2000, 4, 1), output_relation="candidates"
    )
    con.execute(
        """
        CREATE TABLE output AS SELECT *, 0::BIGINT population_count, 0::BIGINT retained_count,
          0.0::DOUBLE sample_weight, ''::VARCHAR example_key FROM candidates WHERE false
        """
    )
    append_stratified_sample(con, candidates="candidates", output="output", quotas={1: 2, 2: 1, 3: 1})
    validate_examples(con, "output")
    return retained_target_identity(con, "output")


def test_repeated_fixture_construction_selects_identical_target_identity() -> None:
    assert _sample_identity() == _sample_identity()


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE output SET target_month=input_month",
        "UPDATE output SET tws_source_month=input_month WHERE effective_horizon>1",
        "UPDATE output SET effective_horizon=8",
        "UPDATE output SET tws_source_location_id='lat2=2;lon2=2'",
        "UPDATE output SET fold_cutoff=DATE '1999-01-01'",
        "UPDATE output SET target='NaN'::DOUBLE",
        "UPDATE output SET example_key=(SELECT min(example_key) FROM output)",
    ],
)
def test_provenance_duplicate_and_finite_violations_are_rejected(mutation: str) -> None:
    con = fixture_connection()
    create_fold_candidates(
        con, fold_id="F01", cutoff=date(2000, 4, 1), output_relation="candidates"
    )
    con.execute(
        """
        CREATE TABLE output AS SELECT *, 0::BIGINT population_count, 0::BIGINT retained_count,
          0.0::DOUBLE sample_weight, ''::VARCHAR example_key FROM candidates WHERE false
        """
    )
    append_stratified_sample(con, candidates="candidates", output="output", quotas={1: 2, 2: 1, 3: 1})
    con.execute(mutation)
    with pytest.raises(ValidationError):
        validate_examples(con, "output")
