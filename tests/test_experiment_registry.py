from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from drought_forecasting.experiment_registry import (
    FIELDS,
    RegistryError,
    add_record,
    read_registry,
    validate_record,
)


def empty_registry(path: Path) -> Path:
    with path.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream, lineterminator="\n").writerow(FIELDS)
    return path


def valid_record() -> dict[str, str]:
    record = {field: "" for field in FIELDS}
    record.update({
        "run_id": "run-20260902T120000Z-baseline",
        "run_date_utc": "2026-09-02T12:00:00Z",
        "git_commit": "abc1234",
        "data_version": "manifest-v1",
        "validation_version": "draft-v1",
        "seed": "42",
        "features": json.dumps(["feature_a"]),
        "model": "synthetic-test-model",
        "model_parameters": json.dumps({"parameter": 1}),
        "rmse_by_horizon": json.dumps({}),
        "regional_or_subgroup_metrics": json.dumps({}),
        "artifact_paths": json.dumps(["artifacts/test/run.json"]),
        "decision": "investigate",
        "decision_reason": "Synthetic registry test only.",
    })
    return record


def test_empty_registry_is_valid(tmp_path: Path) -> None:
    assert read_registry(empty_registry(tmp_path / "registry.csv")) == []


def test_atomic_explicit_add(tmp_path: Path) -> None:
    path = empty_registry(tmp_path / "registry.csv")
    add_record(path, valid_record())
    assert [row["run_id"] for row in read_registry(path)] == [valid_record()["run_id"]]
    assert not list(tmp_path.glob("*.tmp"))


def test_duplicate_run_id_rejected(tmp_path: Path) -> None:
    path = empty_registry(tmp_path / "registry.csv")
    add_record(path, valid_record())
    with pytest.raises(RegistryError, match="duplicate"):
        add_record(path, valid_record())


@pytest.mark.parametrize("field", ["run_id", "git_commit", "data_version", "validation_version", "model"])
def test_required_metadata_rejected(field: str) -> None:
    record = valid_record()
    record[field] = ""
    with pytest.raises(RegistryError):
        validate_record(record)


def test_invalid_utc_and_run_id_rejected() -> None:
    record = valid_record()
    record["run_date_utc"] = "2026-09-02 12:00:00"
    with pytest.raises(RegistryError, match="UTC"):
        validate_record(record)
    record = valid_record()
    record["run_id"] = "bad id"
    with pytest.raises(RegistryError, match="run_id"):
        validate_record(record)


def test_json_fields_are_validated() -> None:
    record = valid_record()
    record["features"] = "not-json"
    with pytest.raises(RegistryError, match="JSON"):
        validate_record(record)


def test_raw_and_absolute_artifact_paths_rejected() -> None:
    for value in (["data/raw/Train.csv"], ["C:/private/output.json"]):
        record = valid_record()
        record["artifact_paths"] = json.dumps(value)
        with pytest.raises(RegistryError, match="artifact"):
            validate_record(record)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_metrics_rejected(value: str) -> None:
    record = valid_record()
    record["overall_cv_rmse"] = value
    with pytest.raises(RegistryError, match="finite"):
        validate_record(record)


def test_header_mismatch_rejected(tmp_path: Path) -> None:
    path = tmp_path / "registry.csv"
    path.write_text("wrong,header\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="header"):
        read_registry(path)
