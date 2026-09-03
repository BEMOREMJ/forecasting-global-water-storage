from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from drought_forecasting.data_preflight import (
    PreflightError,
    build_report,
    inspect_csv,
    run_preflight,
    stream_file_facts,
    validate_headers,
)


class FixedMemory:
    total = 16 * 1024**3
    available = 12 * 1024**3


def write_csv(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8", newline="")
    return path


def synthetic_inputs(tmp_path: Path) -> dict[str, Path]:
    return {
        "train": write_csv(
            tmp_path / "train.csv",
            "ID,time,TWS_t,target\ntrain-secret,2020-01-01,1.0,2.0\n",
        ),
        "test": write_csv(
            tmp_path / "test.csv",
            "ID,time,TWS_t,TWS_t_masked\ntest-secret,2020-02-01,,true\n",
        ),
        "sample_submission": write_csv(
            tmp_path / "submission.csv", "ID,Target\nsubmission-secret,0.0\n"
        ),
        "starter_notebook": (tmp_path / "starter.ipynb"),
        "trustworthiness_pdf": (tmp_path / "trust.pdf"),
    }


def complete_synthetic_inputs(tmp_path: Path) -> dict[str, Path]:
    inputs = synthetic_inputs(tmp_path)
    inputs["starter_notebook"].write_bytes(b"notebook-secret")
    inputs["trustworthiness_pdf"].write_bytes(b"pdf-secret")
    return inputs


def test_sha256_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    payload = b"bounded-content\nsecond-line\n"
    path.write_bytes(payload)

    first = stream_file_facts(path)
    second = stream_file_facts(path)

    assert first["sha256"] == second["sha256"] == hashlib.sha256(payload).hexdigest()


def test_file_metadata_structure(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"abc")

    facts = stream_file_facts(path)

    assert facts["byte_size"] == 3
    assert facts["last_modified_utc"].endswith("Z")
    assert len(facts["sha256"]) == 64


def test_csv_header_and_bounded_inspection(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "bounded.csv", "ID,value\na,1\nb,\nc,3\n")

    result = inspect_csv(path, provisional_rows=3, row_limit=2)

    assert result["header"] == ["ID", "value"]
    assert result["sample_rows_parsed"] == 2
    assert result["sample_row_limit"] == 2
    assert result["sample_missing_counts"]["value"] == 1


def test_report_contains_no_raw_values(tmp_path: Path) -> None:
    report = build_report(
        tmp_path,
        complete_synthetic_inputs(tmp_path),
        row_limit=10,
        memory=FixedMemory(),
    )
    serialized = json.dumps(report, sort_keys=True)

    assert "train-secret" not in serialized
    assert "test-secret" not in serialized
    assert "submission-secret" not in serialized
    assert "notebook-secret" not in serialized
    assert "pdf-secret" not in serialized


def test_physical_line_count_is_provisional(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "lines.csv", 'ID,text\n1,"line one\nline two"\n')

    facts = stream_file_facts(path)

    assert facts["physical_newline_characters"] == 3
    assert facts["provisional_data_row_estimate"] == 2
    assert "not a verified parsed row count" in facts["provisional_row_count_note"]


def test_sample_submission_schema_validation() -> None:
    valid = validate_headers(
        {
            "sample_submission": ["ID", "Target"],
            "train": ["ID", "TWS_t", "target"],
            "test": ["ID", "TWS_t", "TWS_t_masked"],
        }
    )
    invalid = validate_headers(
        {
            "sample_submission": ["Target", "ID"],
            "train": ["ID", "TWS_t", "target"],
            "test": ["ID", "TWS_t", "TWS_t_masked"],
        }
    )

    assert valid["sample_submission_exact_id_target"] is True
    assert invalid["sample_submission_exact_id_target"] is False
    assert invalid["discrepancies"]


def test_missing_file_fails(tmp_path: Path) -> None:
    inputs = complete_synthetic_inputs(tmp_path)
    inputs["train"] = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError, match="train"):
        build_report(tmp_path, inputs, memory=FixedMemory())


def test_refuses_raw_output_path(tmp_path: Path) -> None:
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    inputs = complete_synthetic_inputs(tmp_path)

    with pytest.raises(PreflightError, match="raw-data"):
        run_preflight(tmp_path, raw / "report.json", inputs=inputs)

