# Phase 2C horizon-aware training examples

Phase 2C constructs direct, nonrecursive supervised examples for horizons 1--7. For target month
`y`, current covariates come only from `y-1`, and observed TWS comes only from exact month `y-h`
at the same canonical half-degree location. An absent exact source excludes that candidate; adjacent
rows are never substituted. Targets are limited to `y <= fold_cutoff`, independently for F01 and
F02, so validation targets and later observations cannot enter training.

The exact eligible expansion contains 9,470,789 rows. Its estimated 1.31 GiB logical footprint is
unsafe for downstream in-memory learning with only 4.60 GiB RAM available and observed Phase 2B
validation peaks above 2.2 GiB. The single frozen choice is therefore a 2,000,000-row sample using
seed 20260904. Fixed fold/horizon quotas reproduce the validation-v1 distribution. Within each
stratum, examples are ranked by SHA-256 of seed, fold, target month, location, and horizon; ties use
the canonical target key. `sample_weight` records population/retained count per stratum.

The materialized Parquet remains ignored under `artifacts/phase2c/`. Its compact manifest records
configuration/source/artifact/retained-target identities, schema, distributions, date ranges,
runtime, peak memory, and provenance results. Limitations: repeated target histories occur across
folds by design, the capped artifact is not the full eligible population, and no feature or cap was
selected using model performance.
