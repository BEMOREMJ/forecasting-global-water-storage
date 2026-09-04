"""Canonical Phase 2 prediction rows, fallback policies, and safety validation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from drought_forecasting.validation_core import (
    LocationKey,
    ValidationError,
    target_month,
    validate_month,
)
from drought_forecasting.validation_metrics import HORIZONS, MASK_STATES

PREDICTION_COLUMNS = (
    "run_id",
    "fold_id",
    "location_id",
    "input_month",
    "target_month",
    "effective_horizon",
    "mask_state",
    "prediction",
    "validation_actual",
    "model_name",
    "configuration_id",
    "data_manifest_id",
    "validation_id",
)
PREDICTION_KEY_COLUMNS = ("fold_id", "location_id", "input_month", "target_month")
COMPARABLE_COLUMNS = (
    "fold_id",
    "location_id",
    "input_month",
    "target_month",
    "effective_horizon",
    "mask_state",
    "validation_actual",
)
IDENTITY_COLUMNS = ("configuration_id", "data_manifest_id", "validation_id")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
RUN_ID = re.compile(r"^run-\d{8}T\d{6}Z-[a-z0-9][a-z0-9_-]{0,31}$")


@dataclass(frozen=True, slots=True)
class ComparableRowIdentity:
    """Frozen row count and canonical digest for one comparison population."""

    row_count: int
    sha256: str

    def __post_init__(self) -> None:
        if isinstance(self.row_count, bool) or not isinstance(self.row_count, int) or self.row_count < 1:
            raise ValidationError("comparable row count must be a positive integer")
        if not isinstance(self.sha256, str) or not SHA256.fullmatch(self.sha256):
            raise ValidationError("comparable row identity must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class FallbackResult:
    """The finite prediction selected by an explicit fallback chain."""

    prediction: float
    selected_stage: str
    attempted_stages: tuple[str, ...]


def _finite_number(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ValidationError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValidationError(f"{label} must be a finite number")
    return number


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a nonempty string")
    return value


def _location_id(value: Any) -> str:
    serialized = _nonempty_string(value, "location_id")
    match = re.fullmatch(r"lat2=(-?\d+);lon2=(-?\d+)", serialized)
    if match is None:
        raise ValidationError("location_id must use canonical lat2=<int>;lon2=<int> form")
    key = LocationKey(int(match.group(1)), int(match.group(2)))
    if key.serialize() != serialized:
        raise ValidationError("location_id is not canonically serialized")
    return serialized


def _canonical_value(value: Any) -> Any:
    if isinstance(value, date):
        return validate_month(value).isoformat()
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError("comparable identity contains a nonfinite number")
        return value.hex()
    return value


def comparable_row_identity(rows: Iterable[Mapping[str, Any]]) -> ComparableRowIdentity:
    """Hash ordered row invariants without prediction or model metadata."""
    materialized = tuple(rows)
    if not materialized:
        raise ValidationError("comparable row identity requires at least one row")
    digest = hashlib.sha256()
    previous_key: tuple[Any, ...] | None = None
    for index, row in enumerate(materialized):
        missing = set(COMPARABLE_COLUMNS).difference(row)
        if missing:
            raise ValidationError(f"row {index} is missing comparable columns: {sorted(missing)}")
        key = tuple(_canonical_value(row[column]) for column in PREDICTION_KEY_COLUMNS)
        if previous_key is not None and key <= previous_key:
            raise ValidationError("comparable rows must be strictly ordered by prediction key")
        previous_key = key
        payload = [_canonical_value(row[column]) for column in COMPARABLE_COLUMNS]
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return ComparableRowIdentity(len(materialized), digest.hexdigest())


def validate_prediction_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    expected_rows: ComparableRowIdentity,
    expected_data_manifest_id: str,
    expected_validation_id: str,
) -> tuple[Mapping[str, Any], ...]:
    """Reject any prediction set that violates the canonical comparable-run contract."""
    materialized = tuple(rows)
    if not materialized:
        raise ValidationError("prediction rows must not be empty")
    keys: set[tuple[Any, ...]] = set()
    run_metadata: tuple[str, str, str] | None = None
    for index, row in enumerate(materialized):
        missing = set(PREDICTION_COLUMNS).difference(row)
        if missing:
            raise ValidationError(f"row {index} is missing prediction columns: {sorted(missing)}")
        run_id = _nonempty_string(row["run_id"], "run_id")
        if not RUN_ID.fullmatch(run_id):
            raise ValidationError("run_id does not use the stable registry format")
        fold_id = _nonempty_string(row["fold_id"], "fold_id")
        location_id = _location_id(row["location_id"])
        input_value = validate_month(row["input_month"])
        target_value = validate_month(row["target_month"])
        if target_value != target_month(input_value):
            raise ValidationError("target_month must be exactly one calendar month after input_month")
        horizon = row["effective_horizon"]
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon not in HORIZONS:
            raise ValidationError("effective_horizon must be an integer from 1 through 7")
        if row["mask_state"] not in MASK_STATES:
            raise ValidationError("mask_state is not an approved frozen value")
        _finite_number(row["prediction"], f"prediction at row {index}")
        _finite_number(row["validation_actual"], f"validation_actual at row {index}")
        model_name = _nonempty_string(row["model_name"], "model_name")
        configuration_id = _nonempty_string(row["configuration_id"], "configuration_id")
        data_id = _nonempty_string(row["data_manifest_id"], "data_manifest_id")
        validation_id = _nonempty_string(row["validation_id"], "validation_id")
        for label, value in zip(IDENTITY_COLUMNS, (configuration_id, data_id, validation_id), strict=True):
            if not SHA256.fullmatch(value):
                raise ValidationError(f"{label} must be a lowercase SHA-256 digest")
        if data_id != expected_data_manifest_id:
            raise ValidationError("data-manifest identity mismatch")
        if validation_id != expected_validation_id:
            raise ValidationError("validation identity mismatch")
        metadata = (run_id, model_name, configuration_id)
        if run_metadata is None:
            run_metadata = metadata
        elif metadata != run_metadata:
            raise ValidationError("run, model, and configuration metadata must be uniform")
        key = (fold_id, location_id, input_value, target_value)
        if key in keys:
            raise ValidationError("duplicate prediction key")
        keys.add(key)
    actual_identity = comparable_row_identity(materialized)
    if actual_identity != expected_rows:
        raise ValidationError("prediction rows differ from the frozen comparable-row identity")
    return materialized


def load_fallback_chains(path: Path) -> dict[str, tuple[str, ...]]:
    """Load and validate explicit baseline fallback chains from YAML."""
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValidationError(f"could not load fallback configuration: {path}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != "phase2a-contract-v1":
        raise ValidationError("unknown fallback configuration schema")
    raw = value.get("fallback_chains")
    if not isinstance(raw, dict) or not raw:
        raise ValidationError("fallback_chains must be a nonempty mapping")
    chains: dict[str, tuple[str, ...]] = {}
    for baseline, stages in raw.items():
        if not isinstance(baseline, str) or not baseline or not isinstance(stages, list) or not stages:
            raise ValidationError("each fallback chain requires a baseline name and stages")
        if any(not isinstance(stage, str) or not stage for stage in stages):
            raise ValidationError(f"fallback chain {baseline!r} contains an invalid stage")
        chain = tuple(stages)
        if len(set(chain)) != len(chain):
            raise ValidationError(f"fallback chain {baseline!r} repeats a stage")
        if chain[-1] != "global_mean":
            raise ValidationError(f"fallback chain {baseline!r} must terminate in global_mean")
        chains[baseline] = chain
    return chains


def resolve_fallback(chain: Sequence[str], candidates: Mapping[str, Any]) -> FallbackResult:
    """Select the first available finite candidate or fail loudly on exhaustion."""
    if not chain or chain[-1] != "global_mean" or len(set(chain)) != len(chain):
        raise ValidationError("fallback chain must be unique, nonempty, and terminate in global_mean")
    attempted: list[str] = []
    for stage in chain:
        if not isinstance(stage, str) or not stage:
            raise ValidationError("fallback stages must be nonempty strings")
        attempted.append(stage)
        value = candidates.get(stage)
        if value is None:
            continue
        prediction = _finite_number(value, f"fallback candidate {stage!r}")
        return FallbackResult(prediction, stage, tuple(attempted))
    raise ValidationError(f"fallback chain exhausted without a prediction: {tuple(attempted)!r}")


def validate_official_id_order(
    test_ids: Sequence[Any], sample_submission_ids: Sequence[Any]
) -> tuple[str, ...]:
    """Prove official Test and SampleSubmission IDs are unique and identically ordered."""
    test = tuple(_nonempty_string(value, "Test ID") for value in test_ids)
    sample = tuple(_nonempty_string(value, "SampleSubmission ID") for value in sample_submission_ids)
    if not test or not sample:
        raise ValidationError("official ID sequences must not be empty")
    if len(set(test)) != len(test):
        raise ValidationError("Test IDs contain duplicates")
    if len(set(sample)) != len(sample):
        raise ValidationError("SampleSubmission IDs contain duplicates")
    if test != sample:
        raise ValidationError("Test and SampleSubmission ID order differs")
    return test


def validate_submission_id_order(candidate_ids: Sequence[Any], official_ids: Sequence[str]) -> None:
    """Reject a candidate that omits, adds, duplicates, or reorders official IDs."""
    candidate = tuple(_nonempty_string(value, "candidate ID") for value in candidate_ids)
    official = tuple(official_ids)
    if len(set(candidate)) != len(candidate):
        raise ValidationError("candidate IDs contain duplicates")
    if candidate != official:
        raise ValidationError("candidate IDs do not exactly preserve official order")
