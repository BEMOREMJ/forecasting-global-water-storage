# Phase 2A prediction contract and safety controls

**Status:** implemented for review; no baseline has been executed.

`configs/phase2a_prediction_contract.yaml` is the compact authoritative configuration and
`src/drought_forecasting/prediction_contract.py` enforces it. The contract reuses the frozen
calendar, location, horizon, mask-state, and error semantics from the Phase 1 validation modules.

## Canonical rows and identities

Every prediction row contains the thirteen configured columns. A prediction key is
`(fold_id, location_id, input_month, target_month)`. Locations use the lossless
`lat2=<integer>;lon2=<integer>` representation. Input and target dates must be month starts and
the target must be exactly the next calendar month. Horizons are integers 1--7; predictions and
validation actuals must be finite. Run, model, and configuration metadata are uniform in a run.

Configuration, data-manifest, and validation identities are lowercase SHA-256 digests. The
approved data-manifest and frozen structural-audit identities are recorded in configuration.
The comparable-row identity hashes the strictly key-ordered prediction keys, horizon, mask state,
and validation actual. Prediction values and model metadata are intentionally excluded. Each run
must match a previously frozen row count and digest, preventing missing, unexpected, reordered,
or altered validation rows. The digest will be materialized once from validation-v1 when Phase 2B
constructs prediction rows; Phase 2A does not rerun or materialize the folds.

## Fallbacks and invariants

All planned baseline chains are explicit in YAML. They end at fold-local `global_mean`, the only
mandatory prediction-producing terminal. Missing candidates advance deterministically; a present
nonfinite candidate is rejected, and exhaustion raises an error. Rows are never dropped.

Validators reject absent/nonfinite values, duplicate keys, missing or unexpected comparable rows,
invalid horizons or mask states, calendar inconsistencies, mixed run metadata, and mismatched data
or validation identities. Official Test and SampleSubmission IDs must be nonempty, unique, and
identical in order; a candidate must preserve that sequence exactly. These checks accept ID
sequences and never write either official file.

## Rejected alternatives

- Row-position month arithmetic: rejected because sparse months make it unsafe.
- Implicit `fill_null` chains: rejected because they hide fallback use and exhaustion.
- Dropping unresolved or nonfinite rows: rejected because coverage must remain exact.
- Hashing predictions into comparable-row identity: rejected because models must share row identity.
- Sorting submission IDs before comparison: rejected because official order is contractual.
- Using model-generated TWS as history or recursive predictions: rejected by frozen policy.
