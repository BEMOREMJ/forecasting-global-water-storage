from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from drought_forecasting.data_benchmark import (
    BenchmarkError,
    benchmark_report_schema,
    cleanup_spill,
    compare_integrity,
    dataframe_integrity,
    duckdb_integrity,
    ensure_processed_output,
    id_sequence_digest,
    memory_gate,
    recommend_dtypes,
)


class Memory:
    def __init__(self, total: int, available: int) -> None:
        self.total = total
        self.available = available


def test_parsed_rows_null_nan_and_duplicate_ids() -> None:
    frame = pl.DataFrame({"ID": ["a", "a", "b"], "value": [1.0, None, float("nan")]})
    result = dataframe_integrity(frame, "ID")
    assert result["row_count"] == 3
    assert result["null_counts"]["value"] == 1
    assert result["nan_counts"]["value"] == 1
    assert result["duplicate_id_count"] == 1


def test_id_sequence_digest_stability_and_mismatch() -> None:
    assert id_sequence_digest(["a", "b"]) == id_sequence_digest(["a", "b"])
    assert id_sequence_digest(["a", "b"]) != id_sequence_digest(["b", "a"])


def test_mismatched_test_submission_ids() -> None:
    test = dataframe_integrity(pl.DataFrame({"ID": ["a", "b"]}), "ID")
    submission = dataframe_integrity(pl.DataFrame({"ID": ["a", "c"]}), "ID")
    assert test["id_sequence_digest"] != submission["id_sequence_digest"]


def test_dtype_recommendations() -> None:
    result = recommend_dtypes(
        {"ID": pl.String, "time": pl.String, "value": pl.Float64, "TWS_t_masked": pl.Boolean},
        date_parse_ok=True,
    )
    assert result["ID"]["recommended"] == "String"
    assert result["time"]["recommended"] == "Date"
    assert result["value"]["recommended"] == "Float64"
    assert "no precision-changing downcast" in result["value"]["assessment"]
    assert result["TWS_t_masked"]["recommended"] == "Boolean"


def test_memory_gate_pass_and_fail() -> None:
    gib = 1024**3
    assert memory_gate(Memory(16 * gib, 8 * gib))["authorized"] is True
    assert memory_gate(Memory(16 * gib, 5 * gib))["authorized"] is False


def test_all_stage_class_gates() -> None:
    gib = 1024**3
    estimate = 250 * 1024**2
    assert memory_gate(Memory(16 * gib, 6 * gib), "A", estimate)["authorized"] is True
    assert memory_gate(Memory(16 * gib, 6 * gib), "B", estimate)["authorized"] is True
    assert memory_gate(Memory(16 * gib, 6 * gib), "C", estimate)["authorized"] is True
    assert memory_gate(Memory(16 * gib, 6 * gib), "D", estimate)["authorized"] is False
    assert memory_gate(Memory(16 * gib, 5 * gib), "A", estimate)["authorized"] is False


def test_spill_cleanup(tmp_path: Path) -> None:
    spill = tmp_path / "tmp/benchmark_spill"
    spill.mkdir(parents=True)
    (spill / "duckdb.tmp").write_bytes(b"temporary")
    cleanup_spill(spill, tmp_path)
    assert not spill.exists()


def test_refuses_raw_output(tmp_path: Path) -> None:
    raw = tmp_path / "data/raw"
    raw.mkdir(parents=True)
    with pytest.raises(BenchmarkError, match="data/raw"):
        ensure_processed_output(raw / "Train.parquet", tmp_path)


def test_csv_parquet_integrity_comparison(tmp_path: Path) -> None:
    csv_path = tmp_path / "tiny.csv"
    parquet_path = tmp_path / "tiny.parquet"
    frame = pl.DataFrame({"ID": ["a", "b"], "value": [1.0, None]})
    frame.write_csv(csv_path)
    frame.write_parquet(parquet_path)
    csv_result = dataframe_integrity(pl.read_csv(csv_path), "ID")
    parquet_result = dataframe_integrity(pl.read_parquet(parquet_path), "ID")
    assert all(compare_integrity(csv_result, parquet_result).values())


def test_duckdb_streaming_integrity(tmp_path: Path) -> None:
    csv_path = tmp_path / "tiny.csv"
    pl.DataFrame({"ID": ["a", "b"], "value": [1.0, float("nan")]}).write_csv(csv_path)
    result = duckdb_integrity(csv_path, "ID", tmp_path / "tmp/benchmark_spill")
    assert result["row_count"] == 2
    assert result["unique_id_count"] == 2


def test_benchmark_report_schema() -> None:
    report = {
        "benchmark": {}, "datasets": {}, "memory_gate": {}, "schema_version": 1,
        "status": "complete", "unfinished": [],
    }
    assert benchmark_report_schema(report)
