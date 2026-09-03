"""Strict configuration, canonical hashing, and compact validation audit orchestration."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb
import yaml

from drought_forecasting.validation_core import ValidationError, validate_month
from drought_forecasting.validation_folds import (
    FoldSpec,
    HistoryGate,
    MultiFoldSummary,
    configure_connection,
    construct_folds_sequentially,
    drop_temporary_relations,
    extract_mask_template,
)
from drought_forecasting.validation_metrics import LATITUDE_BANDS, SPEI_BINS

SUPPORTED_SCHEMA_VERSION = "validation-audit-v1"
SUPPORTED_VALIDATION_VERSION = "validation-v1"
SUPPORTED_POLICIES = {
    "mask": "mask-exact-complete-v1",
    "tws_provenance": "tws-observed-only-v1",
    "recursion": "recursion-disabled-v1",
    "metric": "rmse-row-pooled-v1",
}
TOP_LEVEL_FIELDS = {
    "schema",
    "validation_version",
    "folds",
    "offsets",
    "history_gate",
    "horizons",
    "diagnostics",
    "policies",
    "seeds",
    "expected",
    "sources",
    "output",
}
NESTED_FIELDS = {
    "schema": {"version", "status", "implementation_commit"},
    "offsets": {"inputs", "targets"},
    "history_gate": {"minimum_observations", "minimum_span_months"},
    "horizons": {"minimum", "maximum", "expected_counts"},
    "diagnostics": {"latitude_bands", "spei_bins"},
    "policies": set(SUPPORTED_POLICIES),
    "seeds": {"exact_mask", "synthetic"},
    "expected": {
        "folds",
        "pooled_retained_rows",
        "distinct_pooled_target_keys",
        "excluded_fold_location_instances",
        "unique_excluded_locations",
        "latitude_band_exclusions",
    },
    "sources": {
        "official_manifest",
        "train_cache",
        "test_cache",
        "sample_submission_cache",
        "test_mask_template",
        "validation_core_source",
        "validation_folds_source",
        "validation_audit_source",
    },
    "output": {"root", "overwrite"},
}
FOLD_FIELDS = {"fold_id", "origin"}
FOLD_EXPECTED_FIELDS = {
    "fitting_rows",
    "retained_rows",
    "retained_locations",
    "excluded_locations",
    "excluded_template_rows",
    "path_incomplete_locations",
    "history_excluded_locations",
    "horizon_counts",
}
IDENTITY_FIELDS = {"name", "path", "size", "sha256"}
FORBIDDEN_MANIFEST_FIELDS = {
    "row_id",
    "row_ids",
    "coordinates",
    "lat",
    "lon",
    "latitude",
    "longitude",
    "target",
    "targets",
    "feature",
    "features",
    "prediction",
    "predictions",
}


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    name: str
    path: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ExpectedFold:
    fitting_rows: int
    retained_rows: int
    retained_locations: int
    excluded_locations: int
    excluded_template_rows: int
    path_incomplete_locations: int
    history_excluded_locations: int
    horizon_counts: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class ExpectedCounts:
    folds: tuple[tuple[str, ExpectedFold], ...]
    pooled_retained_rows: int
    distinct_pooled_target_keys: int
    excluded_fold_location_instances: int
    unique_excluded_locations: int
    latitude_band_exclusions: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]


@dataclass(frozen=True, slots=True)
class AuditConfig:
    schema_version: str
    schema_status: str
    implementation_commit: str | None
    validation_version: str
    folds: tuple[FoldSpec, ...]
    input_offsets: tuple[int, ...]
    target_offsets: tuple[int, ...]
    history_gate: HistoryGate
    horizon_minimum: int
    horizon_maximum: int
    expected_horizon_counts: tuple[tuple[int, int], ...]
    latitude_bands: tuple[str, ...]
    spei_bins: tuple[str, ...]
    policies: tuple[tuple[str, str], ...]
    exact_mask_seed: None
    synthetic_seed: int
    expected: ExpectedCounts
    sources: tuple[tuple[str, SourceIdentity], ...]
    output_root: str
    overwrite: bool


@dataclass(frozen=True, slots=True)
class VolatileMetadata:
    generated_at: str
    runtime_seconds: float
    peak_memory_mb: float | None


@dataclass(frozen=True, slots=True)
class AuditResult:
    summary: MultiFoldSummary
    manifest: Mapping[str, Any]
    structural_hash: str


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValidationError(f"duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _mapping(value: Any, label: str, fields: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{label} must be a mapping")
    actual = set(value)
    unknown = actual - fields
    missing = fields - actual
    if unknown or missing:
        raise ValidationError(f"{label} fields invalid; missing={sorted(missing)}, unknown={sorted(unknown)}")
    if not all(isinstance(key, str) for key in value):
        raise ValidationError(f"{label} keys must be strings")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValidationError(f"{label} must be an integer >= {minimum}")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a nonempty string")
    return value


def _date(value: Any, label: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValidationError(f"{label} must be a YAML date")
    validate_month(value)
    return value


def _identity(value: Any, label: str) -> SourceIdentity:
    item = _mapping(value, label, IDENTITY_FIELDS)
    digest = _string(item["sha256"], f"{label}.sha256")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValidationError(f"{label}.sha256 must be a lowercase SHA-256 digest")
    return SourceIdentity(
        _string(item["name"], f"{label}.name"),
        _string(item["path"], f"{label}.path"),
        _integer(item["size"], f"{label}.size"),
        digest,
    )


def _counts(value: Any, label: str) -> tuple[tuple[int, int], ...]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{label} must be a mapping")
    parsed: list[tuple[int, int]] = []
    for key, count in value.items():
        horizon = _integer(key, f"{label} horizon", minimum=1)
        parsed.append((horizon, _integer(count, f"{label}[{horizon}]")))
    return tuple(sorted(parsed))


def parse_config_mapping(value: Any, *, official_audit: bool = False) -> AuditConfig:
    """Strictly parse a configuration mapping without scalar coercion."""
    root = _mapping(value, "configuration", TOP_LEVEL_FIELDS)
    sections = {name: _mapping(root[name], name, fields) for name, fields in NESTED_FIELDS.items()}
    schema = sections["schema"]
    schema_version = _string(schema["version"], "schema.version")
    status = _string(schema["status"], "schema.status")
    implementation_commit = schema["implementation_commit"]
    if implementation_commit is not None:
        implementation_commit = _string(implementation_commit, "schema.implementation_commit")
        if implementation_commit != "provisional":
            raise ValidationError("uncommitted implementation identity must be null or provisional")
    validation_version = _string(root["validation_version"], "validation_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION or validation_version != SUPPORTED_VALIDATION_VERSION:
        raise ValidationError("unsupported schema or validation version")
    if official_audit and status != "approved":
        raise ValidationError("official audit requires approved, non-placeholder configuration")

    raw_folds = root["folds"]
    if not isinstance(raw_folds, list) or not raw_folds:
        raise ValidationError("folds must be a nonempty list")
    folds = tuple(
        FoldSpec(
            _string(item["fold_id"], f"folds[{index}].fold_id"),
            _date(item["origin"], f"folds[{index}].origin"),
        )
        for index, raw in enumerate(raw_folds)
        for item in [_mapping(raw, f"folds[{index}]", FOLD_FIELDS)]
    )
    if len({fold.fold_id for fold in folds}) != len(folds) or len({fold.origin for fold in folds}) != len(folds):
        raise ValidationError("fold IDs and origins must be unique")
    if tuple(fold.origin for fold in folds) != tuple(sorted(fold.origin for fold in folds)):
        raise ValidationError("fold origins must be chronologically ordered")

    offsets = sections["offsets"]
    inputs = offsets["inputs"]
    targets = offsets["targets"]
    if not isinstance(inputs, list) or not isinstance(targets, list):
        raise ValidationError("offset lists must be lists")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in (*inputs, *targets)):
        raise ValidationError("offsets must contain integers without coercion")
    input_offsets = tuple(inputs)
    target_offsets = tuple(targets)
    if len(input_offsets) != 18 or len(set(input_offsets)) != 18 or input_offsets != tuple(sorted(input_offsets)):
        raise ValidationError("exactly 18 unique ascending input offsets are required")
    if target_offsets != tuple(offset + 1 for offset in input_offsets):
        raise ValidationError("target offsets must equal input offsets plus one")

    gate = sections["history_gate"]
    history_gate = HistoryGate(
        _integer(gate["minimum_observations"], "history_gate.minimum_observations", minimum=1),
        _integer(gate["minimum_span_months"], "history_gate.minimum_span_months"),
    )
    horizons = sections["horizons"]
    horizon_minimum = _integer(horizons["minimum"], "horizons.minimum", minimum=1)
    horizon_maximum = _integer(horizons["maximum"], "horizons.maximum", minimum=1)
    if (horizon_minimum, horizon_maximum) != (1, 7):
        raise ValidationError("approved horizon boundaries are 1 through 7")
    expected_horizons = _counts(horizons["expected_counts"], "horizons.expected_counts")
    if tuple(key for key, _ in expected_horizons) != tuple(range(1, 8)):
        raise ValidationError("expected horizon counts must contain horizons 1 through 7")

    diagnostics = sections["diagnostics"]
    if diagnostics["latitude_bands"] != list(LATITUDE_BANDS) or diagnostics["spei_bins"] != list(SPEI_BINS):
        raise ValidationError("diagnostic boundaries differ from the frozen definitions")
    policies_section = sections["policies"]
    policies = tuple((name, _string(policies_section[name], f"policies.{name}")) for name in SUPPORTED_POLICIES)
    if dict(policies) != SUPPORTED_POLICIES:
        raise ValidationError("unsupported principal policy ID")
    if policies_section["recursion"] != "recursion-disabled-v1":
        raise ValidationError("principal recursion must remain disabled")
    seeds = sections["seeds"]
    if seeds["exact_mask"] is not None:
        raise ValidationError("exact-mask seed must be null")
    synthetic_seed = _integer(seeds["synthetic"], "seeds.synthetic")

    expected_section = sections["expected"]
    raw_expected_folds = expected_section["folds"]
    if not isinstance(raw_expected_folds, Mapping) or set(raw_expected_folds) != {fold.fold_id for fold in folds}:
        raise ValidationError("expected fold keys must exactly match configured fold IDs")
    expected_folds: list[tuple[str, ExpectedFold]] = []
    for fold in folds:
        item = _mapping(raw_expected_folds[fold.fold_id], f"expected.folds.{fold.fold_id}", FOLD_EXPECTED_FIELDS)
        expected_folds.append(
            (
                fold.fold_id,
                ExpectedFold(
                    _integer(item["fitting_rows"], "fitting_rows", minimum=1),
                    _integer(item["retained_rows"], "retained_rows", minimum=1),
                    _integer(item["retained_locations"], "retained_locations", minimum=1),
                    _integer(item["excluded_locations"], "excluded_locations"),
                    _integer(item["excluded_template_rows"], "excluded_template_rows"),
                    _integer(item["path_incomplete_locations"], "path_incomplete_locations"),
                    _integer(item["history_excluded_locations"], "history_excluded_locations"),
                    _counts(item["horizon_counts"], "fold horizon_counts"),
                ),
            )
        )
    latitude_exclusions = _mapping(
        expected_section["latitude_band_exclusions"],
        "expected.latitude_band_exclusions",
        {fold.fold_id for fold in folds},
    )
    parsed_latitude_exclusions: list[tuple[str, tuple[tuple[str, int], ...]]] = []
    for fold in folds:
        bands = _mapping(
            latitude_exclusions[fold.fold_id],
            f"expected.latitude_band_exclusions.{fold.fold_id}",
            set(LATITUDE_BANDS),
        )
        parsed_latitude_exclusions.append(
            (
                fold.fold_id,
                tuple(
                    (
                        band,
                        _integer(
                            bands[band], f"latitude exclusions {fold.fold_id} {band}"
                        ),
                    )
                    for band in LATITUDE_BANDS
                ),
            )
        )
    expected = ExpectedCounts(
        tuple(expected_folds),
        _integer(expected_section["pooled_retained_rows"], "pooled_retained_rows", minimum=1),
        _integer(expected_section["distinct_pooled_target_keys"], "distinct_pooled_target_keys", minimum=1),
        _integer(expected_section["excluded_fold_location_instances"], "excluded instances"),
        _integer(expected_section["unique_excluded_locations"], "unique exclusions"),
        tuple(parsed_latitude_exclusions),
    )
    if expected.pooled_retained_rows != sum(item.retained_rows for _, item in expected.folds):
        raise ValidationError("expected pooled rows do not equal fold retained rows")
    if expected.distinct_pooled_target_keys != expected.pooled_retained_rows:
        raise ValidationError("expected pooled rows and distinct target keys differ")
    if expected.excluded_fold_location_instances != sum(item.excluded_locations for _, item in expected.folds):
        raise ValidationError("expected excluded fold-location instances are inconsistent")
    if expected.unique_excluded_locations > expected.excluded_fold_location_instances:
        raise ValidationError("unique excluded locations exceed excluded instances")

    sources_section = sections["sources"]
    sources = tuple((name, _identity(sources_section[name], f"sources.{name}")) for name in sorted(sources_section))
    output = sections["output"]
    if not isinstance(output["overwrite"], bool):
        raise ValidationError("output.overwrite must be Boolean")
    return AuditConfig(
        schema_version,
        status,
        implementation_commit,
        validation_version,
        folds,
        input_offsets,
        target_offsets,
        history_gate,
        horizon_minimum,
        horizon_maximum,
        expected_horizons,
        tuple(diagnostics["latitude_bands"]),
        tuple(diagnostics["spei_bins"]),
        policies,
        None,
        synthetic_seed,
        expected,
        sources,
        _string(output["root"], "output.root"),
        output["overwrite"],
    )


def load_audit_config(path: Path, *, official_audit: bool = False) -> AuditConfig:
    """Load strict YAML with duplicate-key detection at every nesting level."""
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise ValidationError("invalid audit YAML") from error
    return parse_config_mapping(value, official_audit=official_audit)


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError("canonical content cannot contain nonfinite numbers")
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValidationError("canonical mapping keys must be strings")
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    raise ValidationError(f"unsupported canonical value type: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    """Serialize supported structural content as canonical UTF-8 JSON."""
    normalized = _canonical_value(value)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def file_identity(path: Path, *, name: str) -> SourceIdentity:
    """Calculate the byte size and streaming SHA-256 identity of one file."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return SourceIdentity(name, path.as_posix(), size, digest.hexdigest())


def verify_source_identity(expected: SourceIdentity, path: Path) -> None:
    actual = file_identity(path, name=expected.name)
    if actual.size != expected.size or actual.sha256 != expected.sha256:
        raise ValidationError(f"source identity mismatch: {expected.name}")


def _assert_no_row_content(value: Any, path: str = "manifest") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValidationError("manifest keys must be strings")
            if key.lower() in FORBIDDEN_MANIFEST_FIELDS:
                raise ValidationError(f"forbidden row-level manifest field: {path}.{key}")
            _assert_no_row_content(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_no_row_content(child, f"{path}[{index}]")


def validate_summary(config: AuditConfig, summary: MultiFoldSummary) -> None:
    """Match constructed compact results to all configured count expectations."""
    actual = {fold.fold_id: fold for fold in summary.folds}
    expected = dict(config.expected.folds)
    if set(actual) != set(expected):
        raise ValidationError("actual fold IDs differ from expected fold IDs")
    for fold_id, wanted in expected.items():
        fold = actual[fold_id]
        if (
            fold.eligible_fitting_rows != wanted.fitting_rows
            or fold.actual_retained_rows != wanted.retained_rows
            or fold.retained_locations != wanted.retained_locations
            or fold.excluded_locations != wanted.excluded_locations
            or fold.template_rows_for_excluded_locations != wanted.excluded_template_rows
            or fold.path_incomplete_locations != wanted.path_incomplete_locations
            or fold.history_excluded_locations != wanted.history_excluded_locations
            or fold.horizon_counts != wanted.horizon_counts
        ):
            raise ValidationError(f"configured fold expectations failed: {fold_id}")
        actual_latitude = dict(fold.latitude_band_exclusions)
        normalized_latitude = {band: actual_latitude.get(band, 0) for band in LATITUDE_BANDS}
        expected_latitude = dict(dict(config.expected.latitude_band_exclusions)[fold_id])
        if normalized_latitude != expected_latitude:
            raise ValidationError(f"configured latitude exclusions failed: {fold_id}")
        if any(
            (
                fold.missing_prior_sources,
                fold.future_source_uses,
                fold.location_source_mismatches,
                fold.horizon_mismatches,
                fold.incomplete_transplant_rows_among_retained,
                fold.duplicate_input_keys,
                fold.duplicate_target_keys,
            )
        ):
            raise ValidationError(f"configured zero-invariant expectations failed: {fold_id}")
    if (
        summary.pooled_retained_rows != config.expected.pooled_retained_rows
        or summary.distinct_pooled_target_keys != config.expected.distinct_pooled_target_keys
        or summary.excluded_fold_location_instances != config.expected.excluded_fold_location_instances
        or summary.unique_excluded_locations != config.expected.unique_excluded_locations
        or summary.aggregate_horizon_counts != config.expected_horizon_counts
    ):
        raise ValidationError("configured pooled expectations failed")
    if any(overlap.input_keys or overlap.target_keys for overlap in summary.pairwise_overlaps):
        raise ValidationError("validation-v1 requires zero cross-fold key overlap")


def build_compact_manifest(
    config: AuditConfig,
    summary: MultiFoldSummary,
    *,
    test_mask_template_hash: str,
    volatile: VolatileMetadata,
) -> tuple[dict[str, Any], str]:
    """Build a row-free manifest whose structural hash excludes volatile metadata."""
    validate_summary(config, summary)
    structural = {
        "schema_version": config.schema_version,
        "validation_version": config.validation_version,
        "implementation_commit": config.implementation_commit,
        "folds": [asdict(fold) for fold in summary.folds],
        "policies": dict(config.policies),
        "seeds": {"exact_mask": config.exact_mask_seed, "synthetic": config.synthetic_seed},
        "pooled": {
            "retained_rows": summary.pooled_retained_rows,
            "distinct_target_keys": summary.distinct_pooled_target_keys,
            "excluded_fold_location_instances": summary.excluded_fold_location_instances,
            "unique_excluded_locations": summary.unique_excluded_locations,
            "horizon_counts": summary.aggregate_horizon_counts,
        },
        "overlaps": [asdict(item) for item in summary.pairwise_overlaps],
        "latitude_band_exclusions": {
            fold_id: dict(counts) for fold_id, counts in config.expected.latitude_band_exclusions
        },
        "invariants": {"configured_expectations": True, "pooled_target_keys_unique": True},
        "sources": {name: asdict(identity) for name, identity in config.sources},
        "test_mask_template_hash": test_mask_template_hash,
    }
    structural["relevant_source_hash"] = canonical_sha256(
        {
            name: identity.sha256
            for name, identity in config.sources
            if name.endswith("_source")
        }
    )
    structural["configuration_hash"] = canonical_sha256(asdict(config))
    structural_hash = canonical_sha256(structural)
    manifest = {
        "structural": structural,
        "structural_audit_hash": structural_hash,
        "volatile": asdict(volatile),
    }
    _assert_no_row_content(manifest)
    return manifest, structural_hash


def write_compact_manifest(
    path: Path,
    manifest: Mapping[str, Any],
    *,
    overwrite: bool = False,
    allowed_roots: Sequence[Path] | None = None,
    allow_frozen_report: bool = False,
) -> None:
    """Atomically write compact JSON only beneath explicitly allowed output roots."""
    roots = tuple(allowed_roots or (Path("tmp"), Path("artifacts/validation")))
    resolved = path.resolve()
    frozen_report = Path("reports/validation_v1_manifest.json").resolve()
    allowed_frozen_report = allow_frozen_report and resolved == frozen_report
    if not allowed_frozen_report and not any(
        resolved.is_relative_to(root.resolve()) for root in roots
    ):
        raise ValidationError("manifest output must be under tmp/ or artifacts/validation/")
    _assert_no_row_content(manifest)
    if path.exists() and not overwrite:
        raise ValidationError("refusing to overwrite existing manifest")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json(manifest) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists() and not overwrite:
            raise ValidationError("refusing to overwrite existing manifest")
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def run_validation_audit(
    config_value: Any,
    connection: duckdb.DuckDBPyConnection,
    *,
    train_relation: str,
    test_relation: str,
    test_origin: date,
    volatile: VolatileMetadata,
    source_paths: Mapping[str, Path],
) -> AuditResult:
    """Validate first, then construct and summarize folds without model or prediction access."""
    config = parse_config_mapping(config_value, official_audit=True)
    configured_sources = dict(config.sources)
    if set(source_paths) != set(configured_sources):
        raise ValidationError("source path keys must exactly match configured source identities")
    for name, identity in config.sources:
        verify_source_identity(identity, source_paths[name])
    configure_connection(connection, threads=2, memory_limit="2GB")
    template = extract_mask_template(
        connection, test_relation, test_origin, output_relation="audit_mask_template"
    )
    try:
        summary = construct_folds_sequentially(
            connection,
            train_relation,
            template.relation,
            config.folds,
            history_gate=config.history_gate,
            relation_prefix="validation_audit",
            required_relative_months=18,
        )
        template_hash = canonical_sha256(
            {
                "rows": template.rows,
                "locations": template.locations,
                "relative_months": template.distinct_relative_months,
                "omitted_slots": template.omitted_location_month_slots,
            }
        )
        manifest, structural_hash = build_compact_manifest(
            config, summary, test_mask_template_hash=template_hash, volatile=volatile
        )
        return AuditResult(summary, manifest, structural_hash)
    finally:
        drop_temporary_relations(connection, (template.relation,))
