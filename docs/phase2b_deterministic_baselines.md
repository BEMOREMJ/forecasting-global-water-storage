# Phase 2B deterministic baselines

Phase 2B evaluates six fixed, fold-local baselines through
`src/drought_forecasting/deterministic_baselines.py`. Each run reconstructs one validation fold at
a time with the unchanged validation-v1 constructor, fits only targets whose target month is on or
before the fold origin, resolves TWS sources by exact location and calendar month, validates every
row with the Phase 2A contract, and then applies the frozen pooled-RMSE diagnostics.

The trend baseline is an auditable per-location ordinary least-squares trend over permitted target
months plus a per-location calendar-month mean residual. It uses no tuned parameters. All fallback
chains come from `configs/phase2a_prediction_contract.yaml`; output records the selected stage,
zero-based fallback level, and missing-stage reason. Ignored OOF Parquet files and their hashes are
listed in compact committed metrics under `reports/phase2b/`.

`reports/phase2b/comparable_rows.json` is frozen from the first successfully contracted global-mean
row population. Every later run must match its row count and digest before metrics are calculated.
Registry records are appended only after OOF validation and compact metric persistence succeed.
