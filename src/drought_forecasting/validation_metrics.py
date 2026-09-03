"""Deterministic, policy-isolated validation metrics and diagnostic slices."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from math import fsum, isfinite, sqrt
from typing import Any

from drought_forecasting.validation_core import ValidationError

SPEI_COLUMNS = ("SPEI_01_t", "SPEI_03_t", "SPEI_06_t", "SPEI_12_t")
POLICY_COLUMNS = (
    "mask_policy_id",
    "tws_provenance_policy_id",
    "recursion_policy_id",
    "metric_policy_id",
)
MASK_STATES = ("observed", "masked/unavailable")
HORIZONS = tuple(range(1, 8))
LATITUDE_BANDS = (
    "[-90,-60)",
    "[-60,-30)",
    "[-30,0)",
    "[0,30)",
    "[30,60)",
    "[60,90]",
)
SPEI_BINS = (
    "(-inf,-2)",
    "[-2,-1.5)",
    "[-1.5,-1)",
    "[-1,1)",
    "[1,1.5)",
    "[1.5,2)",
    "[2,inf)",
)

REQUIRED_COLUMNS = frozenset(
    {
        "target",
        "prediction",
        "fold_id",
        "horizon",
        "mask_state",
        "latitude",
        *SPEI_COLUMNS,
        *POLICY_COLUMNS,
    }
)


@dataclass(frozen=True, slots=True)
class MetricResult:
    """An immutable SSE/count accumulator with its derived RMSE."""

    row_count: int
    sse: float
    rmse: float | None

    def __post_init__(self) -> None:
        if (
            isinstance(self.row_count, bool)
            or not isinstance(self.row_count, int)
            or self.row_count < 0
        ):
            raise ValidationError("metric row_count must be a nonnegative integer")
        if not isfinite(self.sse) or self.sse < 0:
            raise ValidationError("metric SSE must be finite and nonnegative")
        expected = None if self.row_count == 0 else sqrt(self.sse / self.row_count)
        if self.rmse is None:
            if expected is not None:
                raise ValidationError("nonempty metric result requires RMSE")
        elif not isfinite(self.rmse) or expected is None or self.rmse != expected:
            raise ValidationError("metric RMSE must equal sqrt(SSE / row_count)")


@dataclass(frozen=True, slots=True, order=True)
class PolicyIds:
    """The four policy identities that must remain uniform within one report."""

    mask: str
    tws_provenance: str
    recursion: str
    metric: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in self):
            raise ValidationError("policy IDs must be nonempty strings")

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter((self.mask, self.tws_provenance, self.recursion, self.metric))


@dataclass(frozen=True, slots=True)
class MetricReport:
    """A deterministically ordered complete validation metric report."""

    policy_ids: PolicyIds
    pooled: MetricResult
    per_fold: tuple[tuple[str, MetricResult], ...]
    per_horizon: tuple[tuple[int, MetricResult], ...]
    per_mask_state: tuple[tuple[str, MetricResult], ...]
    per_latitude_band: tuple[tuple[str, MetricResult], ...]
    per_spei: tuple[tuple[str, tuple[tuple[str, MetricResult], ...]], ...]


def _empty_result() -> MetricResult:
    return MetricResult(row_count=0, sse=0.0, rmse=None)


def _finite_number(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ValidationError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{label} must be a finite number") from error
    if not isfinite(number):
        raise ValidationError(f"{label} must be a finite number")
    return number


def metric_result(targets: Sequence[Any], predictions: Sequence[Any]) -> MetricResult:
    """Calculate SSE, count, and RMSE without dropping invalid rows."""
    if len(targets) != len(predictions):
        raise ValidationError("target and prediction lengths differ")
    squared_errors: list[float] = []
    for index, (target, prediction) in enumerate(zip(targets, predictions, strict=True)):
        target_value = _finite_number(target, f"target at row {index}")
        prediction_value = _finite_number(prediction, f"prediction at row {index}")
        error = prediction_value - target_value
        squared_error = error * error
        if not isfinite(squared_error):
            raise ValidationError(f"squared error at row {index} is not finite")
        squared_errors.append(squared_error)
    try:
        sse = fsum(squared_errors)
    except OverflowError as error:
        raise ValidationError("SSE overflowed to a nonfinite value") from error
    if not isfinite(sse):
        raise ValidationError("SSE overflowed to a nonfinite value")
    count = len(squared_errors)
    return _empty_result() if count == 0 else MetricResult(count, sse, sqrt(sse / count))


def combine_metric_results(results: Iterable[MetricResult]) -> MetricResult:
    """Combine accumulators by summing SSE and counts, never by averaging RMSE."""
    materialized = tuple(results)
    count = sum(result.row_count for result in materialized)
    try:
        sse = fsum(result.sse for result in materialized)
    except OverflowError as error:
        raise ValidationError("combined SSE overflowed to a nonfinite value") from error
    if not isfinite(sse):
        raise ValidationError("combined SSE overflowed to a nonfinite value")
    return _empty_result() if count == 0 else MetricResult(count, sse, sqrt(sse / count))


def latitude_band(latitude: Any) -> str:
    """Assign a finite latitude to one frozen diagnostic band."""
    value = _finite_number(latitude, "latitude")
    if not -90 <= value <= 90:
        raise ValidationError("latitude must be between -90 and 90")
    if value < -60:
        return LATITUDE_BANDS[0]
    if value < -30:
        return LATITUDE_BANDS[1]
    if value < 0:
        return LATITUDE_BANDS[2]
    if value < 30:
        return LATITUDE_BANDS[3]
    if value < 60:
        return LATITUDE_BANDS[4]
    return LATITUDE_BANDS[5]


def spei_bin(value: Any) -> str:
    """Assign a finite SPEI value to one approved fixed bin."""
    number = _finite_number(value, "SPEI value")
    if number < -2:
        return SPEI_BINS[0]
    if number < -1.5:
        return SPEI_BINS[1]
    if number < -1:
        return SPEI_BINS[2]
    if number < 1:
        return SPEI_BINS[3]
    if number < 1.5:
        return SPEI_BINS[4]
    if number < 2:
        return SPEI_BINS[5]
    return SPEI_BINS[6]


def _result_for_indices(
    targets: Sequence[float], predictions: Sequence[float], indices: Sequence[int]
) -> MetricResult:
    return metric_result([targets[index] for index in indices], [predictions[index] for index in indices])


def _policy_ids(row: Mapping[str, Any]) -> PolicyIds:
    return PolicyIds(*(row[column] for column in POLICY_COLUMNS))


def build_metric_report(rows: Iterable[Mapping[str, Any]]) -> MetricReport:
    """Validate rows and build all frozen, row-count-preserving diagnostic slices."""
    materialized = tuple(rows)
    if not materialized:
        raise ValidationError("a metric report requires at least one row")

    targets: list[float] = []
    predictions: list[float] = []
    folds: list[str] = []
    horizons: list[int] = []
    masks: list[str] = []
    latitudes: list[str] = []
    spei_groups: dict[str, list[str]] = {column: [] for column in SPEI_COLUMNS}
    policies: list[PolicyIds] = []

    for index, row in enumerate(materialized):
        missing = REQUIRED_COLUMNS.difference(row)
        if missing:
            raise ValidationError(f"row {index} is missing required columns: {sorted(missing)}")
        targets.append(_finite_number(row["target"], f"target at row {index}"))
        predictions.append(_finite_number(row["prediction"], f"prediction at row {index}"))
        fold_id = row["fold_id"]
        if not isinstance(fold_id, str) or not fold_id.strip():
            raise ValidationError(f"fold_id at row {index} must be a nonempty string")
        folds.append(fold_id)
        horizon = row["horizon"]
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon not in HORIZONS:
            raise ValidationError(f"horizon at row {index} must be an integer from 1 through 7")
        horizons.append(horizon)
        mask = row["mask_state"]
        if mask not in MASK_STATES:
            raise ValidationError(f"unknown mask state at row {index}: {mask!r}")
        masks.append(mask)
        latitudes.append(latitude_band(row["latitude"]))
        for column in SPEI_COLUMNS:
            spei_groups[column].append(spei_bin(row[column]))
        policies.append(_policy_ids(row))

    expected_policy = policies[0]
    for column_index, column in enumerate(POLICY_COLUMNS):
        if any(tuple(policy)[column_index] != tuple(expected_policy)[column_index] for policy in policies):
            raise ValidationError(f"mixed {column} values are prohibited")

    # This also performs squared-error and overflow validation before any report is returned.
    pooled = metric_result(targets, predictions)
    all_indices = range(len(materialized))

    def sliced(values: Sequence[Any], labels: Sequence[Any]) -> tuple[tuple[Any, MetricResult], ...]:
        return tuple(
            (label, _result_for_indices(targets, predictions, [i for i in all_indices if values[i] == label]))
            for label in labels
        )

    per_fold = sliced(folds, sorted(set(folds)))
    per_horizon = sliced(horizons, HORIZONS)
    per_mask = sliced(masks, MASK_STATES)
    per_latitude = sliced(latitudes, LATITUDE_BANDS)
    per_spei = tuple(
        (column, sliced(spei_groups[column], SPEI_BINS)) for column in SPEI_COLUMNS
    )

    expected_count = pooled.row_count
    families = (per_fold, per_horizon, per_mask, per_latitude)
    if any(sum(result.row_count for _, result in family) != expected_count for family in families):
        raise ValidationError("diagnostic slice row counts do not conserve pooled rows")
    if any(
        sum(result.row_count for _, result in bins) != expected_count for _, bins in per_spei
    ):
        raise ValidationError("SPEI slice row counts do not conserve pooled rows")

    return MetricReport(
        policy_ids=expected_policy,
        pooled=pooled,
        per_fold=per_fold,
        per_horizon=per_horizon,
        per_mask_state=per_mask,
        per_latitude_band=per_latitude,
        per_spei=per_spei,
    )
