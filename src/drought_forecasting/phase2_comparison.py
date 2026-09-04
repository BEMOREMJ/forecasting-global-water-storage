"""Validate Phase 2 registry evidence and build one deterministic comparison artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from drought_forecasting.experiment_registry import FIELDS, RUN_ID, read_registry

EXPECTED_MODELS = (
    "global_mean",
    "location_mean",
    "location_calendar_month_climatology",
    "persistence",
    "seasonal_naive",
    "location_trend_seasonal",
    "lightgbm_basic",
)
COMPARABLE_ID = "2b27c3e0d376965789abab1b1f7dcf3577a8d15b374c03d0a312e39fb4607c0a"
VALIDATION_ID = "dfafe4ae008ac4180f3f92a54ca825c779ab4768b0ba870e22dd1cd4e14088c9"
DATA_ID = "445ce8f92d21abe7e103ad77f38091a4f55e0466d31515d33fbd40c06fb8e533"
EXPECTED_ROWS = 551_965


class ComparisonError(ValueError):
    """Raised when accepted experiment evidence is incomplete or contradictory."""


def _finite(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ComparisonError(f"{label} must be finite") from exc
    if not math.isfinite(result):
        raise ComparisonError(f"{label} must be finite")
    return result


def _metrics_path(record: Mapping[str, str]) -> Path:
    paths = json.loads(record["artifact_paths"])
    matches = [Path(path) for path in paths if path.endswith("-metrics.json")]
    if len(matches) != 1:
        raise ComparisonError(f"{record['run_id']} must reference exactly one compact metrics file")
    if not matches[0].is_file():
        raise ComparisonError(f"referenced metrics artifact is missing: {matches[0]}")
    return matches[0]


def _identity(artifact: Mapping[str, Any], key: str) -> Any:
    if key == "comparable_rows":
        value = artifact.get("comparable_rows")
        return value.get("sha256") if isinstance(value, dict) else artifact.get("identities", {}).get(key)
    return artifact.get(key, artifact.get("identities", {}).get(key.removesuffix("_id")))


def _check_metric_family(run_id: str, metrics: Mapping[str, Any]) -> None:
    for family in ("pooled", "fold", "horizon", "mask_state", "latitude_band", "spei"):
        if family not in metrics:
            raise ComparisonError(f"{run_id} is missing {family} diagnostics")
    if set(metrics["fold"]) != {"F01", "F02"}:
        raise ComparisonError(f"{run_id} requires exactly F01 and F02 metrics")
    if set(metrics["horizon"]) != {str(value) for value in range(1, 8)}:
        raise ComparisonError(f"{run_id} does not preserve horizons 1 through 7")
    for family in (metrics["pooled"], *metrics["fold"].values(), *metrics["horizon"].values()):
        if family["count"] and not math.isfinite(float(family["rmse"])):
            raise ComparisonError(f"{run_id} contains a nonfinite metric")


def validate_and_load(registry_path: Path) -> list[tuple[dict[str, str], dict[str, Any], Path]]:
    records = read_registry(registry_path)
    if len(records) != 7 or tuple(record["model"] for record in records) != EXPECTED_MODELS:
        raise ComparisonError("registry must contain the deterministic seven-run Phase 2 order")
    if len({record["run_id"] for record in records}) != len(records):
        raise ComparisonError("duplicate run ID")
    if [record["run_date_utc"] for record in records] != sorted(record["run_date_utc"] for record in records):
        raise ComparisonError("registry order is not deterministic chronological order")
    loaded = []
    for record in records:
        if list(record) != FIELDS or not RUN_ID.fullmatch(record["run_id"]):
            raise ComparisonError("registry fields or stable run ID are invalid")
        for field in ("seed", "model", "model_parameters", "decision", "decision_reason"):
            if not record[field].strip():
                raise ComparisonError(f"{record['run_id']} has blank required value: {field}")
        if record["data_version"] != DATA_ID or record["validation_version"] != "validation-v1":
            raise ComparisonError("mixed data-manifest or validation version identities")
        path = _metrics_path(record)
        artifact = json.loads(path.read_text(encoding="utf-8"))
        if artifact.get("run_id") != record["run_id"]:
            raise ComparisonError("registry-to-artifact run ID mismatch")
        if artifact.get("configuration_id") is None:
            raise ComparisonError(f"{record['run_id']} is missing configuration identity")
        if _identity(artifact, "comparable_rows") != COMPARABLE_ID:
            raise ComparisonError("mixed comparable-row identities")
        artifact_validation = artifact.get("validation_id", artifact.get("identities", {}).get("validation"))
        artifact_data = artifact.get("data_manifest_id", artifact.get("identities", {}).get("data_manifest"))
        if artifact_validation != VALIDATION_ID or artifact_data != DATA_ID:
            raise ComparisonError("mixed compact-artifact validation or data identities")
        coverage = artifact.get("coverage", {})
        if coverage.get("predicted") != EXPECTED_ROWS or coverage.get("expected") != EXPECTED_ROWS or coverage.get("fraction") != 1.0:
            raise ComparisonError(f"{record['run_id']} has incomplete coverage")
        metrics = artifact.get("metrics", {})
        _check_metric_family(record["run_id"], metrics)
        if _finite(record["overall_cv_rmse"], "registry RMSE") != metrics["pooled"]["rmse"]:
            raise ComparisonError("registry-to-artifact pooled RMSE mismatch")
        if _finite(record["runtime_seconds"], "runtime") != artifact["runtime_seconds"]:
            raise ComparisonError("registry-to-artifact runtime mismatch")
        if _finite(record["peak_memory_mb"], "peak memory") != artifact["peak_memory_mb"]:
            raise ComparisonError("registry-to-artifact memory mismatch")
        if record["decision"] != artifact["decision"] or record["decision_reason"] != artifact["decision_reason"]:
            raise ComparisonError("registry-to-artifact decision mismatch")
        oof = artifact.get("oof_artifact", artifact.get("oof", {}))
        if not oof.get("sha256") or not oof.get("size_bytes"):
            raise ComparisonError(f"{record['run_id']} lacks recorded OOF identity")
        if record["model"] == "lightgbm_basic" and any(
            not value.get("sha256") or not value.get("size_bytes")
            for value in artifact.get("models", {}).values()
        ):
            raise ComparisonError("LightGBM model identities are incomplete")
        loaded.append((record, artifact, path))
    return loaded


def _interpretation(model: str) -> tuple[str, str]:
    values = {
        "global_mean": ("stable global reference", "ignores location and temporal state"),
        "location_mean": ("fold-local spatial level", "large fold shift and no current-state response"),
        "location_calendar_month_climatology": ("explicit seasonal fallback evidence", "weaker than global and persistence"),
        "persistence": ("strongest deterministic baseline and full coverage", "degrades steadily with horizon"),
        "seasonal_naive": ("exact-calendar seasonal reference", "weak overall; 777 persistence fallbacks"),
        "location_trend_seasonal": ("auditable trend stress test", "worst RMSE and unstable folds"),
        "lightgbm_basic": ("best pooled and both-fold RMSE", "masked and long-horizon errors remain higher"),
    }
    return values[model]


def build_comparison(loaded: Sequence[tuple[Mapping[str, str], Mapping[str, Any], Path]]) -> dict[str, Any]:
    runs = []
    for record, artifact, path in loaded:
        metrics = artifact["metrics"]
        primary = record["model"]
        fallbacks = artifact.get("fallback_counts", {})
        fallback_count = sum(int(value) for key, value in fallbacks.items() if key != primary)
        models_size = sum(value["size_bytes"] for value in artifact.get("models", {}).values())
        oof = artifact.get("oof_artifact", artifact.get("oof", {}))
        strengths, weaknesses = _interpretation(primary)
        f01, f02 = metrics["fold"]["F01"], metrics["fold"]["F02"]
        runs.append(
            {
                "run_id": record["run_id"], "model": primary,
                "pooled_rmse": metrics["pooled"]["rmse"],
                "folds": {"F01": f01, "F02": f02},
                "absolute_fold_gap": abs(f01["rmse"] - f02["rmse"]),
                "horizon_rmse": {key: value["rmse"] for key, value in metrics["horizon"].items()},
                "mask_state": metrics["mask_state"],
                "runtime_seconds": artifact["runtime_seconds"],
                "peak_memory_mb": artifact["peak_memory_mb"],
                "coverage": artifact["coverage"],
                "fallback_count": fallback_count,
                "fallback_rate": fallback_count / EXPECTED_ROWS,
                "model_size_bytes": models_size,
                "oof_size_bytes": oof["size_bytes"],
                "decision": record["decision"], "strengths": strengths,
                "weaknesses": weaknesses, "metrics_path": path.as_posix(),
            }
        )
    ranked = sorted(runs, key=lambda value: (value["pooled_rmse"], value["run_id"]))
    for rank, run in enumerate(ranked, 1):
        run["rank"] = rank
    persistence = next(run for run in ranked if run["model"] == "persistence")
    preferred = ranked[0]
    improvement = persistence["pooled_rmse"] - preferred["pooled_rmse"]
    return {
        "schema_version": "phase2e-comparison-v1",
        "validation_version": "validation-v1",
        "validation_id": VALIDATION_ID,
        "comparable_row_sha256": COMPARABLE_ID,
        "row_count_per_run": EXPECTED_ROWS,
        "ranking_policy": "pooled-oof-rmse-ascending-with-robustness-context-v1",
        "runs": ranked,
        "preferred": {
            "run_id": preferred["run_id"], "model": preferred["model"],
            "persistence_absolute_improvement": improvement,
            "persistence_percentage_improvement": improvement / persistence["pooled_rmse"] * 100,
            "improves_each_fold": all(
                preferred["folds"][fold]["rmse"] < persistence["folds"][fold]["rmse"]
                for fold in ("F01", "F02")
            ),
        },
    }


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True); raise


def _documentation(comparison: Mapping[str, Any], digest: str) -> str:
    lines = [
        "# Phase 2E frozen comparison", "",
        f"Comparison JSON SHA-256: `{digest}`.", "",
        "| Rank | Model | Pooled | F01 | F02 | Fold gap | H1 | H2 | H3 | H4 | H5 | H6 | H7 | Runtime s | Peak MiB | Coverage | Fallback rate |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for run in comparison["runs"]:
        h = run["horizon_rmse"]
        lines.append(
            f"| {run['rank']} | {run['model']} | {run['pooled_rmse']:.6f} | "
            f"{run['folds']['F01']['rmse']:.6f} | {run['folds']['F02']['rmse']:.6f} | "
            f"{run['absolute_fold_gap']:.6f} | " + " | ".join(f"{h[str(i)]:.6f}" for i in range(1, 8))
            + f" | {run['runtime_seconds']:.2f} | {run['peak_memory_mb']:.2f} | 100% | {run['fallback_rate']:.6%} |"
        )
    preferred = comparison["preferred"]
    lines += [
        "", "## Decision", "",
        (
            f"`{preferred['model']}` is preferred. It improves pooled RMSE over persistence by "
            f"{preferred['persistence_absolute_improvement']:.6f} "
            f"({preferred['persistence_percentage_improvement']:.2f}%) and improves both folds. "
            "It has the smallest fold gap and full coverage. Persistence remains the strongest "
            "deterministic baseline, fallback/reference method, and mandatory future comparison."
        ),
        "",
        (
            "Measured weaknesses: error rises from horizon 1 to horizon 7; masked inputs are "
            "weaker than observed inputs; the [-60,-30) and [-30,0) latitude bands are weakest. "
            "Detailed SPEI bins remain in the referenced run metrics. All production evaluators "
            "used roughly 2.2 GiB peak RSS, so memory remains a binding laptop constraint."
        ),
        "",
        (
            "Possible Phase 3 hypotheses, not findings: horizon-specific calibration and carefully "
            "bounded feature improvements may address long-horizon and masked-row degradation. No "
            "extra tuning or rerun is justified in Phase 2 because its objective is a trustworthy floor."
        ),
    ]
    return "\n".join(lines) + "\n"


def consolidate(registry: Path, output: Path, documentation: Path) -> tuple[dict[str, Any], str]:
    if output.exists() or documentation.exists():
        raise ComparisonError("refusing to overwrite Phase 2E evidence")
    comparison = build_comparison(validate_and_load(registry))
    encoded = json.dumps(comparison, sort_keys=True, separators=(",", ":")) + "\n"
    _write_atomic(output, encoded)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    _write_atomic(documentation, _documentation(comparison, digest))
    return comparison, digest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("experiments/registry.csv"))
    parser.add_argument("--output", type=Path, default=Path("reports/phase2e_comparison.json"))
    parser.add_argument("--documentation", type=Path, default=Path("docs/phase2e_comparison.md"))
    args = parser.parse_args(argv)
    comparison, digest = consolidate(args.registry, args.output, args.documentation)
    print(json.dumps({"runs": len(comparison["runs"]), "preferred": comparison["preferred"], "sha256": digest, "size_bytes": args.output.stat().st_size}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
