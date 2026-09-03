"""Validation and explicit atomic appends for the experiment registry."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

FIELDS = [
    "run_id", "run_date_utc", "git_commit", "data_version", "validation_version", "seed",
    "features", "model", "model_parameters", "overall_cv_rmse", "rmse_by_horizon",
    "regional_or_subgroup_metrics", "runtime_seconds", "peak_memory_mb", "model_size_mb",
    "submission_score", "artifact_paths", "decision", "decision_reason", "notes",
]
REQUIRED = {
    "run_id", "run_date_utc", "git_commit", "data_version", "validation_version", "seed",
    "features", "model", "model_parameters", "decision", "decision_reason",
}
JSON_FIELDS = {
    "features": list,
    "model_parameters": dict,
    "rmse_by_horizon": dict,
    "regional_or_subgroup_metrics": dict,
    "artifact_paths": list,
}
NUMERIC_FIELDS = {
    "overall_cv_rmse", "runtime_seconds", "peak_memory_mb", "model_size_mb", "submission_score",
}
DECISIONS = {"keep", "reject", "investigate", "superseded"}
RUN_ID = re.compile(r"^run-\d{8}T\d{6}Z-[a-z0-9][a-z0-9_-]{0,31}$")


class RegistryError(ValueError):
    """Raised when registry content is invalid."""


def _json_value(record: Mapping[str, str], field: str) -> Any:
    value = record[field]
    if not value and field not in REQUIRED:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RegistryError(f"{field} must contain valid JSON text") from exc
    expected = JSON_FIELDS[field]
    if not isinstance(parsed, expected):
        raise RegistryError(f"{field} must encode a JSON {expected.__name__}")
    return parsed


def _validate_artifact_paths(paths: list[Any]) -> None:
    for value in paths:
        if not isinstance(value, str) or not value:
            raise RegistryError("artifact_paths entries must be non-empty strings")
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if path.is_absolute() or re.match(r"^[A-Za-z]:/", normalized) or ".." in path.parts:
            raise RegistryError("artifact paths must be repository-relative")
        lowered = [part.lower() for part in path.parts]
        if len(lowered) >= 2 and lowered[:2] == ["data", "raw"]:
            raise RegistryError("artifact paths must not point under data/raw")


def validate_record(record: Mapping[str, str]) -> None:
    if list(record) != FIELDS:
        missing = sorted(set(FIELDS) - set(record))
        extra = sorted(set(record) - set(FIELDS))
        raise RegistryError(f"invalid fields; missing={missing}, extra={extra}")
    blank = sorted(field for field in REQUIRED if not str(record[field]).strip())
    if blank:
        raise RegistryError(f"required metadata is blank: {blank}")
    if not RUN_ID.fullmatch(record["run_id"]):
        raise RegistryError("invalid run_id format")
    try:
        parsed_date = datetime.fromisoformat(record["run_date_utc"])
        if parsed_date.tzinfo is None or parsed_date.utcoffset() != UTC.utcoffset(parsed_date):
            raise ValueError("timestamp is not UTC")
    except ValueError as exc:
        raise RegistryError("run_date_utc must be a valid UTC timestamp ending in Z") from exc
    try:
        int(record["seed"])
    except ValueError as exc:
        raise RegistryError("seed must be an integer") from exc
    if record["decision"] not in DECISIONS:
        raise RegistryError(f"decision must be one of {sorted(DECISIONS)}")
    parsed_json = {field: _json_value(record, field) for field in JSON_FIELDS}
    _validate_artifact_paths(parsed_json["artifact_paths"] or [])
    for field in NUMERIC_FIELDS:
        if not record[field].strip():
            continue
        try:
            value = float(record[field])
        except ValueError as exc:
            raise RegistryError(f"{field} must be numeric or blank") from exc
        if not math.isfinite(value):
            raise RegistryError(f"{field} must be finite")


def read_registry(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"registry is absent: {path}")
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise RegistryError("registry header does not match the required fields")
        records = list(reader)
    run_ids: set[str] = set()
    for record in records:
        validate_record(record)
        if record["run_id"] in run_ids:
            raise RegistryError(f"duplicate run_id: {record['run_id']}")
        run_ids.add(record["run_id"])
    return records


def add_record(path: Path, record: Mapping[str, Any]) -> None:
    normalized = {field: "" if record.get(field) is None else str(record.get(field, "")) for field in FIELDS}
    if set(record) - set(FIELDS):
        raise RegistryError(f"unknown fields: {sorted(set(record) - set(FIELDS))}")
    validate_record(normalized)
    records = read_registry(path)
    if any(existing["run_id"] == normalized["run_id"] for existing in records):
        raise RegistryError(f"duplicate run_id: {normalized['run_id']}")
    records.append(normalized)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(records)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("experiments/registry.csv"))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--record-json", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.validate_only:
        records = read_registry(args.registry)
        print(f"Registry valid: {len(records)} record(s)")
        return 0
    record = json.loads(args.record_json.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise SystemExit("Record JSON must contain an object.")
    add_record(args.registry, record)
    print("Record added.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
