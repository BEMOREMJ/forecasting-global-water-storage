"""Sequential, memory-gated integrity and storage benchmark for competition CSVs."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import polars as pl
import psutil

GIB = 1024**3
MIB = 1024**2
STAGE_HEADROOM = {"A": 512 * MIB, "B": 768 * MIB}
STAGE_RSS_CAP = {"A": 512 * MIB, "B": 768 * MIB}
STEP1_ESTIMATES = {
    "sample_submission": 7_490_673,
    "test": 30_564_651,
    "train": 251_277_104,
}
RAW_FILES = {
    "sample_submission": Path("data/raw/SampleSubmission.csv"),
    "test": Path("data/raw/Test.csv"),
    "train": Path("data/raw/Train.csv"),
}
PARQUET_FILES = {
    "sample_submission": Path("data/processed/SampleSubmission.parquet"),
    "test": Path("data/processed/Test.parquet"),
    "train": Path("data/processed/Train.parquet"),
}
IDENTIFIERS = {"sample_submission": "ID", "test": "ID", "train": "sample_id"}
EXPECTED_HEADERS = {
    "sample_submission": ["ID", "Target"],
    "test": [
        "ID", "time", "lat", "lon", "TWS_t", "SPEI_01_t", "SPEI_03_t",
        "SPEI_06_t", "SPEI_12_t", "SOIL_MOISTURE_t", "month_sin", "month_cos",
        "TWS_t_masked",
    ],
    "train": [
        "sample_id", "time", "lat", "lon", "TWS_t", "SPEI_01_t", "SPEI_03_t",
        "SPEI_06_t", "SPEI_12_t", "SOIL_MOISTURE_t", "month_sin", "month_cos",
        "target",
    ],
}
AGGREGATION_COLUMNS = {"sample_submission": "Target", "test": "month_sin", "train": "month_sin"}


class BenchmarkError(RuntimeError):
    """Raised when the benchmark cannot proceed safely."""


def memory_gate(
    snapshot: Any | None = None,
    stage_class: str = "A",
    estimated_dataframe_bytes: int = 0,
) -> dict[str, Any]:
    snapshot = snapshot or psutil.virtual_memory()
    reserve = max(4 * GIB, int(snapshot.total * 0.30))
    headroom = int(snapshot.available) - reserve
    if stage_class in STAGE_HEADROOM:
        required_headroom = STAGE_HEADROOM[stage_class]
        rss_cap = STAGE_RSS_CAP[stage_class]
    elif stage_class == "C":
        required_headroom = max(GIB, 2 * estimated_dataframe_bytes)
        rss_cap = min(GIB, max(headroom, 0))
    elif stage_class == "D":
        required_headroom = max(int(1.5 * GIB), 3 * estimated_dataframe_bytes)
        rss_cap = min(int(1.5 * GIB), max(headroom, 0))
    else:
        raise ValueError(f"Unknown stage class: {stage_class}")
    headroom_ok = headroom >= required_headroom
    return {
        "authorized": headroom_ok,
        "available_bytes": int(snapshot.available),
        "headroom_after_reserve_bytes": headroom,
        "headroom_threshold_met": headroom_ok,
        "required_headroom_bytes": required_headroom,
        "required_reserve_bytes": reserve,
        "rss_cap_bytes": rss_cap,
        "stage_class": stage_class,
        "total_physical_bytes": int(snapshot.total),
    }


def ensure_processed_output(output: Path, project_root: Path) -> None:
    raw = (project_root / "data/raw").resolve()
    resolved = output.resolve()
    try:
        resolved.relative_to(raw)
    except ValueError:
        pass
    else:
        raise BenchmarkError("Refusing to write benchmark output under data/raw.")
    processed = (project_root / "data/processed").resolve()
    if output.suffix == ".parquet":
        try:
            resolved.relative_to(processed)
        except ValueError as exc:
            raise BenchmarkError("Parquet output must remain under data/processed.") from exc


def id_sequence_digest(values: Sequence[Any]) -> str:
    digest = hashlib.sha256()
    for value in values:
        encoded = str(value).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _polars_dtype(name: str) -> pl.DataType:
    mapping = {
        "Boolean": pl.Boolean,
        "Date": pl.Date,
        "Float64": pl.Float64,
        "Int64": pl.Int64,
        "String": pl.String,
    }
    return mapping[name]


def recommend_dtypes(schema: Mapping[str, pl.DataType], date_parse_ok: bool) -> dict[str, Any]:
    decisions: dict[str, Any] = {}
    for name, dtype in schema.items():
        inferred = str(dtype)
        if name in {"ID", "sample_id"}:
            recommended, assessment = "String", "lossless logical retention"
        elif name == "time" and date_parse_ok:
            recommended, assessment = "Date", "lossless after complete parse validation"
        elif dtype in {pl.Float32, pl.Float64}:
            recommended, assessment = "Float64", "retained; no precision-changing downcast"
        elif name == "TWS_t_masked":
            recommended, assessment = "Boolean", "lossless logical retention"
        else:
            recommended, assessment = inferred, "lossless logical retention"
        decisions[name] = {
            "assessment": assessment,
            "inferred": inferred,
            "recommended": recommended,
        }
    return decisions


def dataframe_integrity(frame: pl.DataFrame, identifier: str) -> dict[str, Any]:
    nulls = {name: int(value) for name, value in zip(frame.columns, frame.null_count().row(0), strict=True)}
    nans = {
        name: int(frame[name].is_nan().sum())
        for name, dtype in frame.schema.items()
        if dtype in {pl.Float32, pl.Float64}
    }
    identifiers = frame[identifier]
    unique_ids = int(identifiers.n_unique())
    return {
        "column_count": frame.width,
        "columns": frame.columns,
        "duplicate_id_count": frame.height - unique_ids,
        "id_all_non_null": identifiers.null_count() == 0,
        "id_sequence_digest": id_sequence_digest(identifiers.to_list()),
        "null_counts": nulls,
        "nan_counts": nans,
        "row_count": frame.height,
        "schema": {name: str(dtype) for name, dtype in frame.schema.items()},
        "unique_id_count": unique_ids,
    }


def compare_integrity(csv_result: Mapping[str, Any], parquet_result: Mapping[str, Any]) -> dict[str, bool]:
    keys = (
        "column_count", "columns", "duplicate_id_count", "id_all_non_null",
        "id_sequence_digest", "null_counts", "nan_counts", "row_count", "unique_id_count",
    )
    return {key: csv_result[key] == parquet_result[key] for key in keys}


def benchmark_report_schema(report: Mapping[str, Any]) -> bool:
    required = {"benchmark", "datasets", "memory_gate", "schema_version", "status", "unfinished"}
    return required.issubset(report) and report.get("schema_version") == 1


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _duckdb_connection(spill: Path, memory_mb: int) -> duckdb.DuckDBPyConnection:
    spill.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(":memory:")
    connection.execute(f"SET memory_limit='{memory_mb}MB'")
    connection.execute("SET threads=2")
    connection.execute("SET preserve_insertion_order=true")
    connection.execute("SET temp_directory=?", [str(spill)])
    return connection


def _csv_sql(path: Path) -> str:
    escaped = str(path.resolve()).replace("'", "''")
    return f"read_csv_auto('{escaped}', header=true, sample_size=-1)"


def _parquet_sql(path: Path) -> str:
    escaped = str(path.resolve()).replace("'", "''")
    return f"read_parquet('{escaped}')"


def _stream_id_digest(connection: duckdb.DuckDBPyConnection, relation: str, identifier: str) -> str:
    cursor = connection.execute(f"SELECT {_quoted(identifier)} FROM {relation}")
    digest = hashlib.sha256()
    while rows := cursor.fetchmany(10_000):
        for (value,) in rows:
            encoded = str(value).encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return digest.hexdigest()


def duckdb_integrity(path: Path, identifier: str, spill: Path, parquet: bool = False) -> dict[str, Any]:
    connection = _duckdb_connection(spill, 384 if not parquet else 512)
    try:
        relation = _parquet_sql(path) if parquet else _csv_sql(path)
        described = connection.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
        columns = [row[0] for row in described]
        schema = {row[0]: row[1] for row in described}
        expressions = ["count(*) AS row_count"]
        for column in columns:
            quoted = _quoted(column)
            expressions.append(f"count(*) FILTER (WHERE {quoted} IS NULL) AS {_quoted('null__' + column)}")
            if schema[column] in {"DOUBLE", "FLOAT", "REAL"}:
                expressions.append(f"count(*) FILTER (WHERE isnan({quoted})) AS {_quoted('nan__' + column)}")
        quoted_id = _quoted(identifier)
        expressions.extend([
            f"count(DISTINCT {quoted_id}) AS unique_ids",
            f"count({quoted_id}) AS non_null_ids",
        ])
        cursor = connection.execute(f"SELECT {', '.join(expressions)} FROM {relation}")
        row = cursor.fetchone()
        names = [item[0] for item in cursor.description]
        values = dict(zip(names, row, strict=True))
        row_count = int(values["row_count"])
        unique_ids = int(values["unique_ids"])
        return {
            "column_count": len(columns),
            "columns": columns,
            "duplicate_id_count": row_count - unique_ids,
            "id_all_non_null": int(values["non_null_ids"]) == row_count,
            "id_sequence_digest": _stream_id_digest(connection, relation, identifier),
            "nan_counts": {column: int(values.get("nan__" + column, 0)) for column in columns if schema[column] in {"DOUBLE", "FLOAT", "REAL"}},
            "null_counts": {column: int(values["null__" + column]) for column in columns},
            "row_count": row_count,
            "schema": schema,
            "unique_id_count": unique_ids,
        }
    finally:
        connection.close()


def cleanup_spill(spill: Path, project_root: Path) -> None:
    resolved = spill.resolve()
    allowed = (project_root / "tmp").resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as exc:
        raise BenchmarkError("Refusing to clean spill directory outside project tmp.") from exc
    if spill.exists():
        shutil.rmtree(spill)


def _read_csv(name: str, path: Path, optimized: bool) -> pl.DataFrame | pd.DataFrame:
    if not optimized:
        return pd.read_csv(path)
    schema = pl.scan_csv(path).collect_schema()
    date_probe = pl.scan_csv(path).select(
        pl.col("time").str.to_date(strict=False).is_null().sum().alias("invalid")
    ).collect(engine="streaming")[0, 0] if "time" in schema else 0
    decisions = recommend_dtypes(schema, date_probe == 0)
    overrides = {column: _polars_dtype(item["recommended"]) for column, item in decisions.items()}
    return pl.read_csv(path, schema_overrides=overrides, try_parse_dates=False)


def child_stage(stage: str, name: str, source: Path, destination: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    identifier = IDENTIFIERS[name]
    project_root = source.resolve().parents[2]
    spill = project_root / "tmp/benchmark_spill"
    if stage == "integrity_csv":
        result = duckdb_integrity(source, identifier, spill)
        result["dtype_decisions"] = {
            column: {
                "assessment": "retained; no precision-changing downcast" if dtype in {"DOUBLE", "FLOAT", "REAL"} else "lossless logical retention",
                "inferred": dtype,
                "recommended": "Float64" if dtype in {"DOUBLE", "FLOAT", "REAL"} else ("String" if column in {"ID", "sample_id"} else dtype),
            }
            for column, dtype in result["schema"].items()
        }
        result["header_expected"] = result["columns"] == EXPECTED_HEADERS[name]
    elif stage == "pandas_load":
        frame = pd.read_csv(source)
        result = {
            "column_count": int(frame.shape[1]),
            "dataframe_memory_bytes": int(frame.memory_usage(index=True, deep=True).sum()),
            "row_count": int(frame.shape[0]),
        }
    elif stage == "polars_load":
        frame = _read_csv(name, source, optimized=True)
        result = {
            "column_count": frame.width,
            "dataframe_memory_bytes": frame.estimated_size(),
            "row_count": frame.height,
        }
    elif stage == "convert":
        if destination is None:
            raise BenchmarkError("Conversion requires a destination.")
        connection = _duckdb_connection(spill, 512)
        try:
            escaped_destination = str(destination.resolve()).replace("'", "''")
            connection.execute(
                f"COPY (SELECT * FROM {_csv_sql(source)}) TO '{escaped_destination}' "
                "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 122880)"
            )
        finally:
            connection.close()
        result = {"compression": "Zstandard; deterministic row group size 122880", "parquet_bytes": destination.stat().st_size}
    elif stage == "integrity_parquet":
        result = duckdb_integrity(source, identifier, spill, parquet=True)
    elif stage == "parquet_load":
        frame = pl.read_parquet(source)
        result = {
            "column_count": frame.width,
            "dataframe_memory_bytes": frame.estimated_size(),
            "row_count": frame.height,
        }
    elif stage == "aggregation":
        if destination is None:
            raise BenchmarkError("Aggregation requires the Parquet path.")
        column = _quoted(AGGREGATION_COLUMNS[name])
        connection = _duckdb_connection(spill, 384)
        csv_started = time.perf_counter()
        csv_value = connection.execute(f"SELECT sum({column}) FROM {_csv_sql(source)}").fetchone()[0]
        csv_seconds = time.perf_counter() - csv_started
        parquet_started = time.perf_counter()
        parquet_value = connection.execute(f"SELECT sum({column}) FROM {_parquet_sql(destination)}").fetchone()[0]
        parquet_seconds = time.perf_counter() - parquet_started
        tolerance = 1e-10
        equal = abs(float(csv_value) - float(parquet_value)) <= tolerance * max(1.0, abs(float(csv_value)))
        connection.close()
        result = {
            "csv_seconds": csv_seconds,
            "equal_within_tolerance": equal,
            "numeric_tolerance": tolerance,
            "parquet_seconds": parquet_seconds,
        }
    else:
        raise BenchmarkError(f"Unknown child stage: {stage}")

    result["wall_seconds"] = time.perf_counter() - started
    memory_info = psutil.Process().memory_info()
    result["child_peak_rss_bytes"] = int(getattr(memory_info, "peak_wset", memory_info.rss))
    if "frame" in locals():
        del frame
    gc.collect()
    return result


def run_isolated(
    stage: str,
    stage_class: str,
    name: str,
    source: Path,
    project_root: Path,
    destination: Path | None = None,
) -> dict[str, Any]:
    spill = project_root / "tmp/benchmark_spill"
    cleanup_spill(spill, project_root)
    gate = memory_gate(stage_class=stage_class, estimated_dataframe_bytes=STEP1_ESTIMATES[name])
    if not gate["authorized"]:
        raise BenchmarkError(f"Memory gate failed before {stage}/{name}: {json.dumps(gate, sort_keys=True)}")
    command = [sys.executable, __file__, "--child", stage, "--name", name, "--source", str(source)]
    if destination is not None:
        command.extend(["--destination", str(destination)])
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    peak_rss = 0
    aborted_reason: str | None = None
    child = psutil.Process(process.pid)
    while process.poll() is None:
        try:
            peak_rss = max(peak_rss, child.memory_info().rss)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        available = psutil.virtual_memory().available
        if peak_rss > gate["rss_cap_bytes"]:
            aborted_reason = f"child exceeded Class {stage_class} RSS cap"
        elif available < gate["required_reserve_bytes"]:
            aborted_reason = "system available RAM fell below the required reserve"
        if aborted_reason:
            process.terminate()
            break
        time.sleep(0.05)
    stdout, stderr = process.communicate()
    try:
        if aborted_reason:
            raise BenchmarkError(f"Aborted {stage}/{name}: {aborted_reason}")
        if process.returncode:
            raise BenchmarkError(f"Child {stage}/{name} failed: {stderr.strip()}")
        result = json.loads(stdout)
        result["gate"] = gate
        result["monitored_peak_rss_bytes"] = max(peak_rss, int(result.get("child_peak_rss_bytes", 0)))
        recovery = memory_gate(stage_class="A")
        result["post_stage_available_bytes"] = recovery["available_bytes"]
        result["post_stage_above_reserve"] = recovery["available_bytes"] >= recovery["required_reserve_bytes"]
        if not result["post_stage_above_reserve"]:
            raise BenchmarkError(f"RAM did not recover above reserve after {stage}/{name}")
        return result
    finally:
        cleanup_spill(spill, project_root)


def build_initial_report(gate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "benchmark": {
            "class_A": {"required_headroom_bytes": 512 * MIB, "rss_cap_bytes": 512 * MIB, "duckdb_memory_limit": "384MB", "threads": 2},
            "class_B": {"required_headroom_bytes": 768 * MIB, "rss_cap_bytes": 768 * MIB, "duckdb_memory_limit": "512MB", "threads": 2},
            "class_C_formula": "headroom >= max(1 GiB, 2 * Step 1 dataframe estimate); cap=min(1 GiB, headroom)",
            "class_D_formula": "headroom >= max(1.5 GiB, 3 * Step 1 dataframe estimate); cap=min(1.5 GiB, headroom)",
            "reserve_formula": "max(4 GiB, 30% of physical RAM)",
            "spill_directory": "tmp/benchmark_spill",
        },
        "datasets": {},
        "memory_gate": dict(gate),
        "schema_version": 1,
        "status": "aborted_before_class_A" if not gate["authorized"] else "running",
        "test_submission_relationship": {},
        "unfinished": [],
    }


def enrich_from_preflight(report: dict[str, Any], project_root: Path) -> None:
    preflight_path = project_root / "reports/phase0_data_preflight.json"
    if not preflight_path.is_file():
        return
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    report["protected_artifacts"] = {
        name: {
            "byte_size": artifact["byte_size"],
            "path": artifact["path"],
            "sha256": artifact["sha256"],
        }
        for name, artifact in preflight["artifacts"].items()
    }
    for name, dataset in report.get("datasets", {}).items():
        artifact = preflight["artifacts"][name]
        dataset["physical_newline_characters"] = artifact["physical_newline_characters"]
        dataset["provisional_data_row_estimate"] = artifact["provisional_data_row_estimate"]
        dataset["physical_line_matches_parsed_rows"] = (
            artifact["provisional_data_row_estimate"]
            == dataset.get("integrity_csv", {}).get("row_count")
        )
    report["total_processed_cache_bytes"] = sum(
        dataset.get("convert", {}).get("parquet_bytes", 0)
        for dataset in report.get("datasets", {}).values()
    )


def orchestrate(project_root: Path, output: Path) -> dict[str, Any]:
    ensure_processed_output(output, project_root)
    gate = memory_gate(stage_class="A")
    report = build_initial_report(gate)
    if not gate["authorized"]:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report

    for name in ("train", "test", "sample_submission"):
        raw = project_root / RAW_FILES[name]
        parquet = project_root / PARQUET_FILES[name]
        ensure_processed_output(parquet, project_root)
        dataset: dict[str, Any] = {"csv_bytes": raw.stat().st_size, "stages": {}}
        report["datasets"][name] = dataset
        stages = (
            ("integrity_csv", "A", raw, None),
            ("convert", "B", raw, parquet),
            ("integrity_parquet", "B", parquet, None),
            ("aggregation", "B", raw, parquet),
            ("polars_load", "C", raw, None),
            ("parquet_load", "C", parquet, None),
            ("pandas_load", "D", raw, None),
        )
        for stage, stage_class, source, destination in stages:
            if source == parquet and not parquet.exists():
                dataset["stages"][stage] = {"status": "safely_skipped", "reason": "Parquet prerequisite absent."}
                continue
            stage_gate = memory_gate(stage_class=stage_class, estimated_dataframe_bytes=STEP1_ESTIMATES[name])
            if not stage_gate["authorized"]:
                dataset["stages"][stage] = {"status": "safely_skipped", "gate": stage_gate, "reason": "Operation-specific memory gate failed."}
                continue
            try:
                measurement = run_isolated(stage, stage_class, name, source, project_root, destination)
                dataset[stage] = measurement
                dataset["stages"][stage] = {"status": "completed"}
            except BenchmarkError as exc:
                status = "aborted_for_safety" if "Aborted" in str(exc) or "RAM" in str(exc) else "failed"
                dataset["stages"][stage] = {"status": status, "reason": str(exc)}
                if status == "aborted_for_safety":
                    continue
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if "integrity_csv" in dataset and "integrity_parquet" in dataset:
            dataset["integrity_comparison"] = compare_integrity(dataset["integrity_csv"], dataset["integrity_parquet"])
        if "convert" in dataset:
            dataset["csv_to_parquet_size_ratio"] = dataset["csv_bytes"] / dataset["convert"]["parquet_bytes"]
        if "polars_load" in dataset and "parquet_load" in dataset:
            dataset["csv_to_parquet_load_time_ratio"] = dataset["polars_load"]["wall_seconds"] / dataset["parquet_load"]["wall_seconds"]
        if "pandas_load" in dataset and "polars_load" in dataset:
            dataset["pandas_to_polars_memory_ratio"] = dataset["pandas_load"]["dataframe_memory_bytes"] / dataset["polars_load"]["dataframe_memory_bytes"]
    if "test" in report["datasets"] and "sample_submission" in report["datasets"]:
        test = report["datasets"]["test"].get("integrity_csv", {})
        submission = report["datasets"]["sample_submission"].get("integrity_csv", {})
        if test and submission:
            report["test_submission_relationship"] = {
                "same_row_count": test["row_count"] == submission["row_count"],
                "same_id_sequence_digest": test["id_sequence_digest"] == submission["id_sequence_digest"],
                "every_test_id_exactly_once": test["duplicate_id_count"] == 0 and submission["duplicate_id_count"] == 0 and test["id_sequence_digest"] == submission["id_sequence_digest"],
                "sample_submission_exact_header": submission["columns"] == ["ID", "Target"],
            }
    statuses = [value["status"] for dataset in report["datasets"].values() for value in dataset["stages"].values()]
    if "failed" in statuses:
        report["status"] = "complete_with_failures"
    elif "aborted_for_safety" in statuses:
        report["status"] = "complete_with_safety_aborts"
    elif "safely_skipped" in statuses:
        report["status"] = "complete_with_safe_skips"
    else:
        report["status"] = "complete"
    enrich_from_preflight(report, project_root)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("reports/phase0_data_benchmark.json"))
    parser.add_argument("--child", choices=("integrity_csv", "pandas_load", "polars_load", "convert", "integrity_parquet", "parquet_load", "aggregation"))
    parser.add_argument("--name", choices=tuple(RAW_FILES))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--enrich-existing", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.child:
        if args.name is None or args.source is None:
            raise SystemExit("Child mode requires --name and --source.")
        print(json.dumps(child_stage(args.child, args.name, args.source, args.destination), sort_keys=True))
        return 0
    output = args.output if args.output.is_absolute() else args.project_root / args.output
    if args.enrich_existing:
        report = json.loads(output.read_text(encoding="utf-8"))
        enrich_from_preflight(report, args.project_root)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "enriched": True}, sort_keys=True))
        return 0
    report = orchestrate(args.project_root, output)
    print(json.dumps({"status": report["status"], "unfinished_count": len(report["unfinished"])}, sort_keys=True))
    return 0 if report["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
