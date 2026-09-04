# Phase 2G first-submission candidate

Phase 2E selected `lightgbm_basic` because its frozen validation-v1 pooled RMSE was best and it improved both folds. Phase 2G uses the exact Phase 2D feature order, parameters, 200 rounds, seed, and two CPU threads; it performs no tuning.

The final-fit population is reconstructed once at the Test origin rather than concatenating F01/F02. Historical validation months are ordinary Train observations at production time, so examples whose targets are available through 2015-09-01 are eligible. Exact-calendar input covariates come from target minus one month and observed TWS comes from target minus horizon. A deterministic 2,000,000-row SHA-256-ranked sample is stratified to the official Test horizon distribution and weighted by population/retained counts.

Test features use each official row's supplied covariates and only an exact, genuinely observed Test TWS source at the required calendar month. They never use hidden targets, masked values, predictions, recursion, adjacent-row substitution, or later backfill. This production fit does not reconstruct or modify validation-v1.

Reproduce exactly once with:

```powershell
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m drought_forecasting.submission_candidate --config configs/phase2g_submission.yaml
```

The recorded production process encountered a DuckDB prepared-parameter error only when creating the Test view, after materialization and fitting succeeded. Those upstream artifacts were preserved. The audited recovery command `--resume-after-fit` ran only the incomplete prediction, write, validation, and manifest stages; it is not a general reproduction path.

Expected resources are about 4 minutes and 2.2 GB peak process memory for spill-backed materialization, a 104 MB float32 model matrix, roughly 125 seconds for fitting/prediction, and under 1 GB permanent artifacts. The ignored CSV is `submissions/phase2g_lightgbm_basic.csv`; the compact evidence is `reports/phase2g_submission_manifest.json`. The candidate is not uploaded. The seven-row experiment registry remains unchanged because it records validation experiments and this production run has no OOF metric.
