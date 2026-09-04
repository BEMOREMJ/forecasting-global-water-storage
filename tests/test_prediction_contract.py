"""Focused Phase 2A tests for prediction and fallback safety controls."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from drought_forecasting.prediction_contract import (
    ComparableRowIdentity,
    comparable_row_identity,
    load_fallback_chains,
    resolve_fallback,
    validate_official_id_order,
    validate_prediction_rows,
    validate_submission_id_order,
)
from drought_forecasting.validation_core import ValidationError

DATA_ID = "4" * 64
VALIDATION_ID = "5" * 64
CONFIG_ID = "6" * 64


def row(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "run_id": "run-20260904T120000Z-persistence",
        "fold_id": "F01",
        "location_id": "lat2=0;lon2=1",
        "input_month": date(2004, 9, 1),
        "target_month": date(2004, 10, 1),
        "effective_horizon": 1,
        "mask_state": "observed",
        "prediction": 1.5,
        "validation_actual": 2.0,
        "model_name": "persistence",
        "configuration_id": CONFIG_ID,
        "data_manifest_id": DATA_ID,
        "validation_id": VALIDATION_ID,
    }
    value.update(updates)
    return value


def valid_rows() -> list[dict[str, object]]:
    return [
        row(),
        row(
            location_id="lat2=0;lon2=2",
            effective_horizon=2,
            mask_state="masked/unavailable",
            prediction=-1.0,
        ),
    ]


def validate(rows: list[dict[str, object]], expected: ComparableRowIdentity | None = None):
    return validate_prediction_rows(
        rows,
        expected_rows=expected or comparable_row_identity(rows),
        expected_data_manifest_id=DATA_ID,
        expected_validation_id=VALIDATION_ID,
    )


def test_valid_contract_and_comparable_identity_are_deterministic() -> None:
    rows = valid_rows()
    identity = comparable_row_identity(rows)
    assert identity == comparable_row_identity(rows)
    assert validate(rows, identity) == tuple(rows)


@pytest.mark.parametrize("prediction", [None, float("nan"), float("inf"), float("-inf")])
def test_missing_or_nonfinite_prediction_is_rejected(prediction: object) -> None:
    rows = [row(prediction=prediction)]
    with pytest.raises(ValidationError, match="prediction.*finite"):
        validate(rows, ComparableRowIdentity(1, "0" * 64))


def test_duplicate_prediction_key_is_rejected() -> None:
    rows = [row(), row(prediction=9.0)]
    with pytest.raises(ValidationError, match="duplicate prediction key"):
        validate(rows, ComparableRowIdentity(2, "0" * 64))


@pytest.mark.parametrize("horizon", [0, 8, 1.0, True, None])
def test_invalid_horizon_is_rejected(horizon: object) -> None:
    rows = [row(effective_horizon=horizon)]
    with pytest.raises(ValidationError, match="effective_horizon"):
        validate(rows, ComparableRowIdentity(1, "0" * 64))


@pytest.mark.parametrize(
    ("input_value", "target_value"),
    [
        (date(2004, 9, 2), date(2004, 10, 1)),
        (date(2004, 9, 1), date(2004, 11, 1)),
        (date(2004, 9, 1), date(2004, 10, 2)),
    ],
)
def test_inconsistent_calendar_relationship_is_rejected(input_value: date, target_value: date) -> None:
    rows = [row(input_month=input_value, target_month=target_value)]
    with pytest.raises(ValidationError, match="month|target_month"):
        validate(rows, ComparableRowIdentity(1, "0" * 64))


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"data_manifest_id": "7" * 64}, "data-manifest identity mismatch"),
        ({"validation_id": "8" * 64}, "validation identity mismatch"),
    ],
)
def test_mismatched_frozen_identity_is_rejected(updates: dict[str, object], message: str) -> None:
    rows = [row(**updates)]
    with pytest.raises(ValidationError, match=message):
        validate(rows, ComparableRowIdentity(1, "0" * 64))


def test_missing_unexpected_and_reordered_comparable_rows_are_rejected() -> None:
    rows = valid_rows()
    frozen = comparable_row_identity(rows)
    with pytest.raises(ValidationError, match="frozen comparable-row identity"):
        validate(rows[:1], frozen)
    extra = rows + [
        row(location_id="lat2=0;lon2=3", prediction=0.0, validation_actual=0.0)
    ]
    with pytest.raises(ValidationError, match="frozen comparable-row identity"):
        validate(extra, frozen)
    with pytest.raises(ValidationError, match="strictly ordered"):
        validate(list(reversed(rows)), frozen)


def test_changed_comparable_field_is_rejected_but_prediction_is_not_hashed() -> None:
    rows = valid_rows()
    frozen = comparable_row_identity(rows)
    changed_prediction = [dict(item) for item in rows]
    changed_prediction[0]["prediction"] = 999.0
    validate(changed_prediction, frozen)
    changed_actual = [dict(item) for item in rows]
    changed_actual[0]["validation_actual"] = 999.0
    with pytest.raises(ValidationError, match="frozen comparable-row identity"):
        validate(changed_actual, frozen)


def test_configuration_loads_all_planned_terminating_chains() -> None:
    chains = load_fallback_chains(Path("configs/phase2a_prediction_contract.yaml"))
    assert set(chains) == {
        "global_mean",
        "location_mean",
        "location_calendar_month_climatology",
        "persistence",
        "seasonal_naive",
        "location_trend_seasonal",
    }
    assert all(chain[-1] == "global_mean" for chain in chains.values())


def test_fallback_resolution_is_deterministic_and_reports_path() -> None:
    chain = ("seasonal_naive", "persistence", "location_mean", "global_mean")
    candidates = {"seasonal_naive": None, "persistence": 2, "global_mean": -5}
    first = resolve_fallback(chain, candidates)
    second = resolve_fallback(chain, candidates)
    assert first == second
    assert first.prediction == 2.0
    assert first.selected_stage == "persistence"
    assert first.attempted_stages == ("seasonal_naive", "persistence")


def test_fallback_exhaustion_and_nonfinite_candidate_are_rejected() -> None:
    chain = ("persistence", "global_mean")
    with pytest.raises(ValidationError, match="exhausted"):
        resolve_fallback(chain, {})
    with pytest.raises(ValidationError, match="finite"):
        resolve_fallback(chain, {"persistence": float("nan"), "global_mean": 1.0})


@pytest.mark.parametrize(
    "chain", [(), ("persistence",), ("global_mean", "global_mean")]
)
def test_malformed_fallback_chain_is_rejected(chain: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError, match="fallback chain"):
        resolve_fallback(chain, {"global_mean": 1.0})


def test_official_and_candidate_order_are_preserved_exactly() -> None:
    official = validate_official_id_order(["a", "b", "c"], ["a", "b", "c"])
    validate_submission_id_order(["a", "b", "c"], official)


@pytest.mark.parametrize(
    ("test_ids", "sample_ids", "message"),
    [
        (["a", "a"], ["a", "a"], "Test IDs contain duplicates"),
        (["a", "b"], ["b", "a"], "order differs"),
        (["a", "b"], ["a"], "order differs"),
    ],
)
def test_official_id_discrepancies_are_rejected(
    test_ids: list[str], sample_ids: list[str], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        validate_official_id_order(test_ids, sample_ids)


@pytest.mark.parametrize("candidate", [["b", "a"], ["a"], ["a", "a"]])
def test_candidate_reordering_omission_and_duplication_are_rejected(candidate: list[str]) -> None:
    with pytest.raises(ValidationError, match="candidate IDs"):
        validate_submission_id_order(candidate, ("a", "b"))
