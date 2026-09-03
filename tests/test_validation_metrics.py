"""Phase 1F.3A tests for deterministic validation metrics and slices."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from math import sqrt

import pytest

from drought_forecasting.validation_core import ValidationError
from drought_forecasting.validation_metrics import (
    HORIZONS,
    LATITUDE_BANDS,
    MASK_STATES,
    POLICY_COLUMNS,
    SPEI_BINS,
    SPEI_COLUMNS,
    MetricReport,
    MetricResult,
    build_metric_report,
    combine_metric_results,
    latitude_band,
    metric_result,
    spei_bin,
)


def row(**updates: object) -> dict[str, object]:
    result: dict[str, object] = {
        "target": 1.0,
        "prediction": 2.0,
        "fold_id": "F01",
        "horizon": 1,
        "mask_state": "observed",
        "latitude": 0.0,
        "SPEI_01_t": 0.0,
        "SPEI_03_t": 0.0,
        "SPEI_06_t": 0.0,
        "SPEI_12_t": 0.0,
        "mask_policy_id": "mask-v1",
        "tws_provenance_policy_id": "tws-observed-only-v1",
        "recursion_policy_id": "recursion-disabled-v1",
        "metric_policy_id": "metrics-v1",
    }
    result.update(updates)
    return result


def as_dict(items: tuple[tuple[object, MetricResult], ...]) -> dict[object, MetricResult]:
    return dict(items)


def test_metric_result_matches_hand_calculation_and_handles_signed_values() -> None:
    result = metric_result([-2.0, 2.0], [-1.0, -1.0])
    assert result == MetricResult(row_count=2, sse=10.0, rmse=sqrt(5.0))


def test_zero_error_and_empty_accumulators() -> None:
    assert metric_result([1.0, -3.0], [1.0, -3.0]) == MetricResult(2, 0.0, 0.0)
    assert metric_result([], []) == MetricResult(0, 0.0, None)
    assert combine_metric_results([]) == MetricResult(0, 0.0, None)


def test_t013_unequal_folds_pool_sse_and_count_instead_of_rmse() -> None:
    small = metric_result([0.0], [3.0])
    large = metric_result([0.0, 0.0, 0.0], [1.0, 1.0, 1.0])
    pooled = combine_metric_results([small, large])
    assert pooled == MetricResult(4, 12.0, sqrt(3.0))
    assert pooled.rmse != pytest.approx((small.rmse + large.rmse) / 2)  # type: ignore[operator]


@pytest.mark.parametrize("invalid", [None, float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("column", ["target", "prediction"])
def test_invalid_target_or_prediction_is_rejected(invalid: object, column: str) -> None:
    values = {"target": [0.0], "prediction": [0.0]}
    values[column] = [invalid]
    with pytest.raises(ValidationError, match="finite"):
        metric_result(values["target"], values["prediction"])


def test_length_mismatch_and_squared_error_overflow_are_rejected() -> None:
    with pytest.raises(ValidationError, match="lengths differ"):
        metric_result([1.0], [])
    with pytest.raises(ValidationError, match="squared error"):
        metric_result([1e308], [-1e308])


def test_combined_sse_overflow_is_rejected() -> None:
    first = MetricResult(1, 1e308, sqrt(1e308))
    with pytest.raises(ValidationError, match="combined SSE"):
        combine_metric_results([first, first])


def test_metric_objects_are_immutable() -> None:
    result = metric_result([0.0], [1.0])
    with pytest.raises(FrozenInstanceError):
        result.row_count = 2  # type: ignore[misc]
    report = build_metric_report([row()])
    with pytest.raises(FrozenInstanceError):
        report.pooled = result  # type: ignore[misc]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-90, "[-90,-60)"),
        (-60.0001, "[-90,-60)"),
        (-60, "[-60,-30)"),
        (-30, "[-30,0)"),
        (0, "[0,30)"),
        (30, "[30,60)"),
        (60, "[60,90]"),
        (90, "[60,90]"),
    ],
)
def test_b022_t020_every_latitude_boundary(value: float, expected: str) -> None:
    assert latitude_band(value) == expected


@pytest.mark.parametrize("value", [-90.1, 90.1, None, float("nan"), float("inf")])
def test_invalid_latitude_is_rejected(value: object) -> None:
    with pytest.raises(ValidationError, match="latitude"):
        latitude_band(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-3, "(-inf,-2)"),
        (-2, "[-2,-1.5)"),
        (-1.5, "[-1.5,-1)"),
        (-1, "[-1,1)"),
        (1, "[1,1.5)"),
        (1.5, "[1.5,2)"),
        (2, "[2,inf)"),
    ],
)
def test_every_spei_boundary(value: float, expected: str) -> None:
    assert spei_bin(value) == expected


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), float("-inf")])
def test_invalid_spei_is_rejected(value: object) -> None:
    with pytest.raises(ValidationError, match="SPEI"):
        spei_bin(value)


def test_all_horizons_masks_and_predefined_empty_slices_are_present() -> None:
    rows = [row(horizon=horizon, mask_state=MASK_STATES[horizon % 2]) for horizon in HORIZONS]
    report = build_metric_report(rows)
    assert tuple(label for label, _ in report.per_horizon) == HORIZONS
    assert tuple(label for label, _ in report.per_mask_state) == MASK_STATES
    assert tuple(label for label, _ in report.per_latitude_band) == LATITUDE_BANDS
    assert tuple(column for column, _ in report.per_spei) == SPEI_COLUMNS
    assert all(tuple(label for label, _ in bins) == SPEI_BINS for _, bins in report.per_spei)
    empty = as_dict(report.per_latitude_band)["[-90,-60)"]
    assert empty == MetricResult(0, 0.0, None)


@pytest.mark.parametrize("horizon", [0, 8, 1.0, True, None])
def test_invalid_horizon_is_rejected(horizon: object) -> None:
    with pytest.raises(ValidationError, match="horizon"):
        build_metric_report([row(horizon=horizon)])


def test_both_mask_states_and_unknown_state() -> None:
    report = build_metric_report([row(mask_state=state) for state in MASK_STATES])
    assert [result.row_count for _, result in report.per_mask_state] == [1, 1]
    with pytest.raises(ValidationError, match="unknown mask state"):
        build_metric_report([row(mask_state="generated")])


@pytest.mark.parametrize("column", POLICY_COLUMNS)
def test_l017_t015_each_policy_dimension_rejects_mixing(column: str) -> None:
    changed = row()
    changed[column] = "different-policy"
    with pytest.raises(ValidationError, match=column):
        build_metric_report([row(), changed])


def test_missing_required_column_is_rejected() -> None:
    incomplete = row()
    del incomplete["SPEI_12_t"]
    with pytest.raises(ValidationError, match="missing required columns"):
        build_metric_report([incomplete])


def test_l018_l019_t013_t020_determinism_and_row_count_conservation() -> None:
    rows = []
    spei_values = (-3.0, -2.0, -1.5, -1.0, 1.0, 1.5, 2.0)
    latitudes = (-90.0, -60.0, -30.0, 0.0, 30.0, 60.0, 90.0)
    for index in range(14):
        rows.append(
            row(
                target=float(index - 5),
                prediction=float(index - 4),
                fold_id="F02" if index % 2 else "F01",
                horizon=index % 7 + 1,
                mask_state=MASK_STATES[index % 2],
                latitude=latitudes[index % len(latitudes)],
                **{column: spei_values[(index + offset) % 7] for offset, column in enumerate(SPEI_COLUMNS)},
            )
        )
    first = build_metric_report(rows)
    second = build_metric_report(reversed(rows))
    assert first == second
    assert isinstance(first, MetricReport)
    assert tuple(label for label, _ in first.per_fold) == ("F01", "F02")
    families = (
        first.per_fold,
        first.per_horizon,
        first.per_mask_state,
        first.per_latitude_band,
    )
    assert all(sum(result.row_count for _, result in family) == 14 for family in families)
    assert all(sum(result.row_count for _, result in bins) == 14 for _, bins in first.per_spei)


def test_report_rejects_invalid_values_without_dropping_rows() -> None:
    for column in ("target", "prediction", *SPEI_COLUMNS):
        invalid = row()
        invalid[column] = float("nan")
        with pytest.raises(ValidationError):
            build_metric_report([row(), invalid])
