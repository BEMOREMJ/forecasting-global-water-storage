"""Bounded, reproducible preflight checks for official competition artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import psutil

CHUNK_SIZE = 1024 * 1024
DEFAULT_SAMPLE_ROWS = 10_000
GIB = 1024**3

DEFAULT_INPUTS = {
    "sample_submission": Path("data/raw/SampleSubmission.csv"),
    "starter_notebook": Path("references/official/StarterNotebook.ipynb"),
    "test": Path("data/raw/Test.csv"),
    "train": Path("data/raw/Train.csv"),
    "trustworthiness_pdf": Path("references/official/Trustworthiness_Evaluation.pdf"),
}
CSV_INPUTS = frozenset({"sample_submission", "test", "train"})
DEFAULT_OUTPUT = Path("reports/phase0_data_preflight.json")


class PreflightError(RuntimeError):
    """Raised when a preflight cannot be performed safely."""


def _utc_timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat().replace("+00:00", "Z")


def stream_file_facts(path: Path, chunk_size: int = CHUNK_SIZE) -> dict[str, Any]:
    """Hash and count physical newlines using bounded binary reads."""
    if not path.is_file():
        raise FileNotFoundError(f"Required input is absent: {path}")

    digest = hashlib.sha256()
    newline_count = 0
    last_byte: int | None = None
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
            newline_count += chunk.count(b"\n")
            last_byte = chunk[-1]

    size = path.stat().st_size
    physical_lines = newline_count + (1 if size and last_byte != 10 else 0)
    return {
        "byte_size": size,
        "last_modified_utc": _utc_timestamp(path),
        "physical_newline_characters": newline_count,
        "provisional_data_row_estimate": max(physical_lines - 1, 0),
        "provisional_row_count_note": (
            "Physical-line estimate only; quoted multiline fields can make it inaccurate. "
            "This is not a verified parsed row count."
        ),
        "sha256": digest.hexdigest(),
    }


def read_csv_header(path: Path) -> list[str]:
    """Read only the CSV header record."""
    if not path.is_file():
        raise FileNotFoundError(f"Required input is absent: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        try:
            return next(csv.reader(stream))
        except StopIteration as exc:
            raise PreflightError(f"CSV is empty: {path}") from exc


def inspect_csv(path: Path, provisional_rows: int, row_limit: int) -> dict[str, Any]:
    """Parse no more than ``row_limit`` rows with Polars and return aggregate facts."""
    if row_limit < 1 or row_limit > DEFAULT_SAMPLE_ROWS:
        raise ValueError(f"row_limit must be between 1 and {DEFAULT_SAMPLE_ROWS}")

    header = read_csv_header(path)
    sample = pl.read_csv(path, n_rows=row_limit, infer_schema_length=row_limit)
    sample_rows = sample.height
    sample_bytes = sample.estimated_size()
    if sample_rows:
        rough_full_bytes = round(sample_bytes * provisional_rows / sample_rows)
    else:
        rough_full_bytes = 0

    return {
        "header": header,
        "inferred_sample_dtypes": {
            name: str(dtype) for name, dtype in zip(sample.columns, sample.dtypes, strict=True)
        },
        "rough_full_memory_estimate_bytes": rough_full_bytes,
        "rough_full_memory_estimate_note": (
            "Linear extrapolation from the bounded Polars sample and provisional physical-line "
            "row estimate; allocator, parser, string, and temporary-buffer overhead can differ."
        ),
        "sample_dataframe_estimated_bytes": sample_bytes,
        "sample_missing_counts": {
            name: int(value)
            for name, value in zip(sample.columns, sample.null_count().row(0), strict=True)
        },
        "sample_row_limit": row_limit,
        "sample_rows_parsed": sample_rows,
    }


def validate_headers(headers: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """Validate only relationships documented by the official starter notebook."""
    sample = list(headers["sample_submission"])
    train = list(headers["train"])
    test = list(headers["test"])

    train_ids = [name for name in ("ID", "sample_id") if name in train]
    test_ids = [name for name in ("ID", "sample_id") if name in test]
    train_targets = [name for name in ("target", "Target") if name in train]
    test_targets = [name for name in ("target", "Target") if name in test]

    discrepancies: list[str] = []
    if sample != ["ID", "Target"]:
        discrepancies.append("SampleSubmission header is not exactly ['ID', 'Target'].")
    if len(train_ids) != 1:
        discrepancies.append("Train header does not contain exactly one of ID or sample_id.")
    if len(test_ids) != 1:
        discrepancies.append("Test header does not contain exactly one of ID or sample_id.")
    if len(train_targets) != 1:
        discrepancies.append("Train header does not contain exactly one of target or Target.")
    if test_targets:
        discrepancies.append("Test header unexpectedly contains target or Target.")
    if "TWS_t_masked" not in test:
        discrepancies.append("Test header does not contain TWS_t_masked as documented.")

    return {
        "discrepancies": discrepancies,
        "sample_submission_exact_id_target": sample == ["ID", "Target"],
        "test_identifier_columns": test_ids,
        "test_mask_flag_present": "TWS_t_masked" in test,
        "test_target_columns": test_targets,
        "train_identifier_columns": train_ids,
        "train_target_columns": train_targets,
    }


def classify_later_operation(
    estimated_bytes: int,
    available_bytes: int,
    total_bytes: int,
) -> dict[str, Any]:
    """Classify a possible full parse while preserving the required RAM reserve."""
    reserve = max(4 * GIB, int(total_bytes * 0.30))
    headroom = max(available_bytes - reserve, 0)
    conservative_need = estimated_bytes * 2

    if conservative_need <= headroom:
        classification = "safe locally"
    elif conservative_need <= max(total_bytes - reserve, 0) and available_bytes >= reserve:
        classification = "slow but possible locally"
    elif estimated_bytes > 0:
        classification = "better suited to free Colab"
    else:
        classification = "not currently justified"

    return {
        "classification": classification,
        "conservative_working_memory_bytes": conservative_need,
        "estimated_dataframe_bytes": estimated_bytes,
        "local_headroom_after_required_reserve_bytes": headroom,
        "required_free_memory_reserve_bytes": reserve,
    }


def _display_path(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _validate_output(output: Path, inputs: Mapping[str, Path], raw_directory: Path) -> None:
    resolved_output = output.resolve()
    resolved_inputs = {path.resolve() for path in inputs.values()}
    if resolved_output in resolved_inputs:
        raise PreflightError("Refusing to overwrite an input artifact.")
    try:
        resolved_output.relative_to(raw_directory.resolve())
    except ValueError:
        return
    raise PreflightError("Refusing to write output anywhere under the raw-data directory.")


def build_report(
    project_root: Path,
    inputs: Mapping[str, Path],
    row_limit: int = DEFAULT_SAMPLE_ROWS,
    memory: Any | None = None,
) -> dict[str, Any]:
    """Build a bounded report without writing it."""
    resolved_inputs = {
        name: path if path.is_absolute() else project_root / path for name, path in inputs.items()
    }
    missing = [name for name, path in resolved_inputs.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Required inputs are absent: {', '.join(sorted(missing))}")

    artifacts: dict[str, Any] = {}
    headers: dict[str, list[str]] = {}
    for name in sorted(resolved_inputs):
        path = resolved_inputs[name]
        facts = stream_file_facts(path)
        artifact = {
            "byte_size": facts["byte_size"],
            "last_modified_utc": facts["last_modified_utc"],
            "path": _display_path(path, project_root),
            "sha256": facts["sha256"],
        }
        if name in CSV_INPUTS:
            artifact.update(
                {
                    "physical_newline_characters": facts["physical_newline_characters"],
                    "provisional_data_row_estimate": facts["provisional_data_row_estimate"],
                    "provisional_row_count_note": facts["provisional_row_count_note"],
                }
            )
            csv_facts = inspect_csv(path, facts["provisional_data_row_estimate"], row_limit)
            artifact["bounded_csv_inspection"] = csv_facts
            headers[name] = csv_facts["header"]
        artifacts[name] = artifact

    memory = memory or psutil.virtual_memory()
    total_memory = int(memory.total)
    available_memory = int(memory.available)
    estimates = {
        name: artifacts[name]["bounded_csv_inspection"]["rough_full_memory_estimate_bytes"]
        for name in sorted(CSV_INPUTS)
    }
    later_operations = {
        f"full_parse_{name}": classify_later_operation(
            estimate, available_memory, total_memory
        )
        for name, estimate in estimates.items()
    }
    later_operations["combined_full_csv_parse"] = classify_later_operation(
        sum(estimates.values()), available_memory, total_memory
    )
    later_operations["modelling_or_feature_engineering"] = {
        "classification": "not currently justified",
        "reason": "Outside Phase 0C Step 1 and unsupported by bounded preflight evidence.",
    }

    return {
        "artifacts": artifacts,
        "bounded_sample_row_limit": row_limit,
        "header_validation": validate_headers(headers),
        "later_operation_safety": later_operations,
        "memory_safety": {
            "available_physical_memory_bytes_at_check": available_memory,
            "required_free_memory_reserve_bytes": max(4 * GIB, int(total_memory * 0.30)),
            "rule": "Keep at least 4 GiB and 30% of physical RAM free; use the larger reserve.",
            "total_physical_memory_bytes": total_memory,
        },
        "report_kind": "phase0c_step1_bounded_data_preflight",
        "schema_version": 1,
    }


def write_report(report: Mapping[str, Any], output: Path) -> None:
    """Write deterministic, sorted JSON to an already validated destination."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_preflight(
    project_root: Path,
    output: Path,
    inputs: Mapping[str, Path] | None = None,
    row_limit: int = DEFAULT_SAMPLE_ROWS,
) -> tuple[dict[str, Any], float, int]:
    """Validate destinations, build the report, write it, and return runtime diagnostics."""
    inputs = dict(inputs or DEFAULT_INPUTS)
    resolved_output = output if output.is_absolute() else project_root / output
    _validate_output(resolved_output, inputs, project_root / "data/raw")

    started = time.perf_counter()
    report = build_report(project_root, inputs, row_limit=row_limit)
    write_report(report, resolved_output)
    elapsed = time.perf_counter() - started
    memory_info = psutil.Process(os.getpid()).memory_info()
    peak_rss = int(getattr(memory_info, "peak_wset", memory_info.rss))
    return report, elapsed, peak_rss


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-rows", type=int, default=DEFAULT_SAMPLE_ROWS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        _, elapsed, peak_rss = run_preflight(
            project_root=args.project_root,
            output=args.output,
            row_limit=args.sample_rows,
        )
    except (FileNotFoundError, OSError, PreflightError, ValueError, pl.exceptions.PolarsError) as exc:
        raise SystemExit(f"Preflight failed: {exc}") from exc

    print(f"wall_clock_seconds={elapsed:.6f}")
    print(f"process_peak_rss_bytes={peak_rss}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
