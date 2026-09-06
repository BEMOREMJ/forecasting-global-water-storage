# Phase 3 reproduction

Phase 3 validation artifacts are frozen and should not be rerun merely to reproduce reporting. Execute `notebooks/02_core_modeling.ipynb` from its directory to load compact JSON evidence only. Production configuration and identities are in `configs/phase3h_production.yaml` and `reports/phase3h_production_manifest.json`. The production runner refuses to overwrite a completed fit. Raw data, models, predictions, provenance-heavy Parquet, and candidate CSV files remain Git-ignored. No Phase 3 candidate has been uploaded.

The owner-requested post-closeout diagnostic is frozen by `configs/phase3_p3e1_production.yaml` and `reports/phase3_p3e1_production_manifest.json`. Do not rerun its validation optimizer, alter h6, or replace the locally preferred P3-M3B candidate.
