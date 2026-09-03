"""Phase 1F.3B tests for strict audit configuration and compact manifests."""

from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

import duckdb
import pytest
import yaml

import drought_forecasting.validation_audit as audit_module
from drought_forecasting.validation_audit import (
    AuditConfig,
    SourceIdentity,
    VolatileMetadata,
    build_compact_manifest,
    canonical_json,
    canonical_sha256,
    file_identity,
    load_audit_config,
    parse_config_mapping,
    run_validation_audit,
    verify_source_identity,
    write_compact_manifest,
)
from drought_forecasting.validation_core import ValidationError
from drought_forecasting.validation_folds import (
    FoldSummary,
    MultiFoldSummary,
    PairwiseOverlap,
)
from drought_forecasting.validation_metrics import LATITUDE_BANDS, SPEI_BINS

ZERO_HASH = "0" * 64


def identity(name: str) -> dict[str, object]:
    return {"name": name, "path": f"tmp/{name}", "size": 1, "sha256": ZERO_HASH}


def valid_mapping() -> dict[str, object]:
    horizon_counts = {horizon: 2 if horizon == 1 else 0 for horizon in range(1, 8)}
    fold_counts = {horizon: 1 if horizon == 1 else 0 for horizon in range(1, 8)}
    return {
        "schema": {
            "version": "validation-audit-v1",
            "status": "approved",
            "implementation_commit": None,
        },
        "validation_version": "validation-v1",
        "folds": [
            {"fold_id": "F01", "origin": date(2004, 9, 1)},
            {"fold_id": "F02", "origin": date(2008, 12, 1)},
        ],
        "offsets": {"inputs": list(range(18)), "targets": list(range(1, 19))},
        "history_gate": {"minimum_observations": 12, "minimum_span_months": 12},
        "horizons": {"minimum": 1, "maximum": 7, "expected_counts": horizon_counts},
        "diagnostics": {"latitude_bands": list(LATITUDE_BANDS), "spei_bins": list(SPEI_BINS)},
        "policies": {
            "mask": "mask-exact-complete-v1",
            "tws_provenance": "tws-observed-only-v1",
            "recursion": "recursion-disabled-v1",
            "metric": "rmse-row-pooled-v1",
        },
        "seeds": {"exact_mask": None, "synthetic": 20260903},
        "expected": {
            "folds": {
                "F01": {
                    "fitting_rows": 1,
                    "retained_rows": 1,
                    "retained_locations": 1,
                    "excluded_locations": 1,
                    "excluded_template_rows": 1,
                    "path_incomplete_locations": 1,
                    "history_excluded_locations": 0,
                    "horizon_counts": fold_counts,
                },
                "F02": {
                    "fitting_rows": 1,
                    "retained_rows": 1,
                    "retained_locations": 1,
                    "excluded_locations": 1,
                    "excluded_template_rows": 1,
                    "path_incomplete_locations": 1,
                    "history_excluded_locations": 0,
                    "horizon_counts": fold_counts,
                },
            },
            "pooled_retained_rows": 2,
            "distinct_pooled_target_keys": 2,
            "excluded_fold_location_instances": 2,
            "unique_excluded_locations": 1,
            "latitude_band_exclusions": {
                "F01": {band: (1 if band == "[0,30)" else 0) for band in LATITUDE_BANDS},
                "F02": {band: (1 if band == "[0,30)" else 0) for band in LATITUDE_BANDS},
            },
        },
        "sources": {
            "official_manifest": identity("manifest"),
            "train_cache": identity("train"),
            "test_cache": identity("test"),
            "sample_submission_cache": identity("sample-submission"),
            "test_mask_template": identity("mask"),
            "validation_core_source": identity("core-source"),
            "validation_folds_source": identity("folds-source"),
            "validation_audit_source": identity("audit-source"),
        },
        "output": {"root": "artifacts/validation", "overwrite": False},
    }


def fold_summary(fold_id: str, origin: date) -> FoldSummary:
    return FoldSummary(
        fold_id,
        origin,
        2,
        1,
        1,
        1,
        1,
        1,
        0,
        1,
        0,
        0,
        0,
        ((1, 1), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0), (7, 0)),
        eligible_fitting_rows=1,
        latitude_band_exclusions=(("[0,30)", 1),),
    )


def valid_summary() -> MultiFoldSummary:
    folds = (fold_summary("F01", date(2004, 9, 1)), fold_summary("F02", date(2008, 12, 1)))
    overlap = PairwiseOverlap("F01", "F02", 0, 0, 0, 0)
    return MultiFoldSummary(folds, (overlap,), 2, 2, 2, 1, ((1, 2), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0), (7, 0)))


def volatile(timestamp: str = "2026-09-03T00:00:00Z") -> VolatileMetadata:
    return VolatileMetadata(timestamp, 1.25, 512.0)


def test_t010_valid_mapping_and_yaml_are_typed_and_immutable(tmp_path: Path) -> None:
    config = parse_config_mapping(valid_mapping(), official_audit=True)
    assert isinstance(config, AuditConfig)
    assert config.folds[0].origin == date(2004, 9, 1)
    with pytest.raises(FrozenInstanceError):
        config.validation_version = "changed"  # type: ignore[misc]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(valid_mapping(), sort_keys=False), encoding="utf-8")
    assert load_audit_config(path, official_audit=True) == config


@pytest.mark.parametrize(
    ("section", "field"),
    [
        (None, "unexpected"),
        ("schema", "unexpected"),
        ("history_gate", "unexpected"),
        ("policies", "unexpected"),
        ("expected", "unexpected"),
        ("output", "unexpected"),
    ],
)
def test_t010_recursive_unknown_fields_are_rejected(section: str | None, field: str) -> None:
    value = valid_mapping()
    target = value if section is None else value[section]
    assert isinstance(target, dict)
    target[field] = 1
    with pytest.raises(ValidationError, match="unknown"):
        parse_config_mapping(value)


@pytest.mark.parametrize("section", ["schema", "history_gate", "policies", "sources", "output"])
def test_t010_missing_nested_fields_are_rejected(section: str) -> None:
    value = valid_mapping()
    target = value[section]
    assert isinstance(target, dict)
    del target[next(iter(target))]
    with pytest.raises(ValidationError, match="missing"):
        parse_config_mapping(value)


def test_t010_duplicate_yaml_keys_at_nested_depth_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text("schema:\n  version: one\n  version: two\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="duplicate YAML key"):
        load_audit_config(path)


@pytest.mark.parametrize(
    ("path", "bad"),
    [
        (("history_gate", "minimum_observations"), True),
        (("seeds", "synthetic"), True),
        (("folds", 0, "origin"), "2004-09-01"),
        (("output", "overwrite"), 1),
        (("offsets", "inputs"), [True, *range(1, 18)]),
    ],
)
def test_t010_scalar_types_are_not_coerced(path: tuple[object, ...], bad: object) -> None:
    value: object = valid_mapping()
    for key in path[:-1]:
        value = value[key]  # type: ignore[index]
    value[path[-1]] = bad  # type: ignore[index]
    with pytest.raises(ValidationError):
        parse_config_mapping(value if isinstance(value, dict) and not path[:-1] else _root_from_path(path, bad))


def _root_from_path(path: tuple[object, ...], bad: object) -> dict[str, object]:
    root = valid_mapping()
    target: object = root
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = bad  # type: ignore[index]
    return root


def test_t013_duplicate_reversed_folds_and_bad_offsets_are_rejected() -> None:
    for mutation in ("duplicate", "reversed", "inputs", "targets"):
        value = valid_mapping()
        folds = value["folds"]
        offsets = value["offsets"]
        assert isinstance(folds, list) and isinstance(offsets, dict)
        if mutation == "duplicate":
            folds[1]["fold_id"] = "F01"
        elif mutation == "reversed":
            folds.reverse()
        elif mutation == "inputs":
            offsets["inputs"] = list(range(17))
        else:
            offsets["targets"] = list(range(2, 20))
        with pytest.raises(ValidationError):
            parse_config_mapping(value)


@pytest.mark.parametrize(
    ("section", "field", "bad"),
    [
        ("policies", "mask", "unknown"),
        ("policies", "recursion", "recursion-enabled-v1"),
        ("seeds", "exact_mask", 0),
        ("horizons", "maximum", 8),
        ("history_gate", "minimum_span_months", -1),
    ],
)
def test_t015_invalid_policy_seed_counts_and_boundaries_are_rejected(section: str, field: str, bad: object) -> None:
    value = valid_mapping()
    target = value[section]
    assert isinstance(target, dict)
    target[field] = bad
    with pytest.raises(ValidationError):
        parse_config_mapping(value)


def test_t016_official_audit_rejects_placeholder_status_and_commit_identity() -> None:
    value = valid_mapping()
    schema = value["schema"]
    assert isinstance(schema, dict)
    schema["status"] = "draft_not_approved"
    with pytest.raises(ValidationError, match="official audit"):
        parse_config_mapping(value, official_audit=True)
    schema["status"] = "approved"
    schema["implementation_commit"] = "a35203"
    with pytest.raises(ValidationError, match="null or provisional"):
        parse_config_mapping(value)


def test_repository_frozen_yaml_is_accepted_for_official_audit() -> None:
    config = load_audit_config(Path("configs/validation_protocol.yaml"), official_audit=True)
    assert config.validation_version == "validation-v1"
    assert [fold.fold_id for fold in config.folds] == ["F01", "F02"]


def test_t018_canonical_hash_ignores_mapping_and_yaml_order_but_detects_changes(tmp_path: Path) -> None:
    first = {"b": [date(2020, 1, 1), 2], "a": {"y": True, "x": None}}
    second = {"a": {"x": None, "y": True}, "b": [date(2020, 1, 1), 2]}
    assert canonical_json(first) == canonical_json(second)
    assert canonical_sha256(first) == canonical_sha256(second)
    assert canonical_sha256(first) != canonical_sha256({**first, "c": 3})
    path = tmp_path / "ordered.yaml"
    path.write_text(yaml.safe_dump(second), encoding="utf-8")
    assert canonical_sha256(yaml.safe_load(path.read_text(encoding="utf-8"))) == canonical_sha256(first)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {1: "bad"}, {"x": {1, 2}}])
def test_t018_canonical_content_rejects_nonfinite_or_unsupported_values(value: object) -> None:
    with pytest.raises(ValidationError):
        canonical_json(value)


def test_l026_source_identity_verification(tmp_path: Path) -> None:
    path = tmp_path / "source.bin"
    path.write_bytes(b"verified")
    actual = file_identity(path, name="source")
    verify_source_identity(actual, path)
    wrong = SourceIdentity("source", path.as_posix(), actual.size, ZERO_HASH)
    with pytest.raises(ValidationError, match="identity mismatch"):
        verify_source_identity(wrong, path)


def test_l017_l019_t013_manifest_hash_excludes_volatile_metadata() -> None:
    config = parse_config_mapping(valid_mapping())
    first, first_hash = build_compact_manifest(config, valid_summary(), test_mask_template_hash=ZERO_HASH, volatile=volatile())
    second, second_hash = build_compact_manifest(
        config,
        valid_summary(),
        test_mask_template_hash=ZERO_HASH,
        volatile=VolatileMetadata("2030-01-01T00:00:00Z", 99.0, None),
    )
    assert first_hash == second_hash
    assert first["volatile"] != second["volatile"]
    assert first["structural"]["implementation_commit"] is None


def test_t013_manifest_rejects_count_and_overlap_inconsistency() -> None:
    config = parse_config_mapping(valid_mapping())
    wrong_count = copy.copy(valid_summary())
    object.__setattr__(wrong_count, "pooled_retained_rows", 3)
    with pytest.raises(ValidationError, match="pooled expectations"):
        build_compact_manifest(config, wrong_count, test_mask_template_hash=ZERO_HASH, volatile=volatile())
    overlap = copy.copy(valid_summary())
    object.__setattr__(overlap, "pairwise_overlaps", (PairwiseOverlap("F01", "F02", 1, 1, 1, 1),))
    with pytest.raises(ValidationError, match="overlap"):
        build_compact_manifest(config, overlap, test_mask_template_hash=ZERO_HASH, volatile=volatile())


def test_l026_forbidden_row_content_is_rejected_recursively(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    with pytest.raises(ValidationError, match="forbidden"):
        write_compact_manifest(
            path,
            {"safe": {"predictions": [1.0]}},
            allowed_roots=[tmp_path],
        )


def test_l026_l027_atomic_output_root_and_overwrite_safety(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    path = allowed / "manifest.json"
    manifest = {"structural": {"count": 1}, "volatile": {"runtime_seconds": 1.0}}
    write_compact_manifest(path, manifest, allowed_roots=[allowed])
    assert json.loads(path.read_text(encoding="utf-8")) == manifest
    assert not list(allowed.glob("*.tmp"))
    with pytest.raises(ValidationError, match="overwrite"):
        write_compact_manifest(path, manifest, allowed_roots=[allowed])
    outside = tmp_path / "outside.json"
    with pytest.raises(ValidationError, match="under tmp"):
        write_compact_manifest(outside, manifest, allowed_roots=[allowed])
    write_compact_manifest(path, {"structural": {"count": 2}}, overwrite=True, allowed_roots=[allowed])
    assert json.loads(path.read_text(encoding="utf-8"))["structural"]["count"] == 2


def test_l026_only_exact_frozen_tracked_report_can_be_authorized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest = {"structural": {"count": 1}}
    frozen = Path("reports/validation_v1_manifest.json")
    write_compact_manifest(frozen, manifest, allow_frozen_report=True)
    assert frozen.is_file()
    with pytest.raises(ValidationError, match="under tmp"):
        write_compact_manifest(
            Path("reports/another.json"), manifest, allow_frozen_report=True
        )


def test_t010_configuration_is_validated_before_data_access() -> None:
    value = valid_mapping()
    value["unexpected"] = True
    with pytest.raises(ValidationError, match="unknown"):
        run_validation_audit(
            value,
            None,  # type: ignore[arg-type]
            train_relation="train",
            test_relation="test",
            test_origin=date(2015, 8, 1),
            volatile=volatile(),
            source_paths={},
        )


def orchestration_connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE test_data(
            ID VARCHAR, time DATE, lat DOUBLE, lon DOUBLE, TWS_t DOUBLE,
            SPEI_01_t DOUBLE, SPEI_03_t DOUBLE, SPEI_06_t DOUBLE,
            SPEI_12_t DOUBLE, SOIL_MOISTURE_t DOUBLE, month_sin DOUBLE,
            month_cos DOUBLE, TWS_t_masked BOOLEAN
        )
        """
    )
    connection.execute(
        "INSERT INTO test_data VALUES ('safe-id', DATE '2015-08-01', 0, 0, NULL, 1, 1, 1, 1, 1, 0, 1, TRUE)"
    )
    return connection


def test_t014_t019_orchestration_accepts_only_test_structure_and_cleans_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = orchestration_connection()
    monkeypatch.setattr(audit_module, "construct_folds_sequentially", lambda *args, **kwargs: valid_summary())
    checked: list[str] = []
    monkeypatch.setattr(
        audit_module,
        "verify_source_identity",
        lambda identity, path: checked.append(identity.name),
    )
    result = run_validation_audit(
        valid_mapping(),
        connection,
        train_relation="unused_train",
        test_relation="test_data",
        test_origin=date(2015, 8, 1),
        volatile=volatile(),
        source_paths={name: Path(identity.path) for name, identity in parse_config_mapping(valid_mapping()).sources},
    )
    assert result.summary == valid_summary()
    assert connection.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='audit_mask_template'").fetchone()[0] == 0
    assert not hasattr(audit_module, "train_model")
    assert not hasattr(audit_module, "predict")
    assert sorted(checked) == [
        "audit-source",
        "core-source",
        "folds-source",
        "manifest",
        "mask",
        "sample-submission",
        "test",
        "train",
    ]


def test_t019_orchestration_cleans_template_after_deliberate_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = orchestration_connection()

    def fail(*args: object, **kwargs: object) -> MultiFoldSummary:
        raise ValidationError("deliberate invariant failure")

    monkeypatch.setattr(audit_module, "construct_folds_sequentially", fail)
    monkeypatch.setattr(audit_module, "verify_source_identity", lambda identity, path: None)
    with pytest.raises(ValidationError, match="deliberate"):
        run_validation_audit(
            valid_mapping(),
            connection,
            train_relation="unused_train",
            test_relation="test_data",
            test_origin=date(2015, 8, 1),
            volatile=volatile(),
            source_paths={name: Path(identity.path) for name, identity in parse_config_mapping(valid_mapping()).sources},
        )
    assert connection.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='audit_mask_template'").fetchone()[0] == 0
