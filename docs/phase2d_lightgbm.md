# Phase 2D basic LightGBM benchmark

Phase 2D uses one fixed native LightGBM GBDT configuration from
`configs/phase2d_lightgbm.yaml`. F01 and F02 train independently and sequentially from their
approved Phase 2C rows. Validation features reuse validation-v1 folds and exact observed-TWS
source months. No early stopping, tuning, imputation, recursive values, external data, or
validation-derived preprocessing is allowed.

All 13 present approved features are numeric float32 with no missing values in Phase 2C. The
optional TWS availability/mask indicator is absent and therefore omitted without rematerializing
Phase 2C. Phase 2C population/retained sample weights are used as recorded. Models and OOF
predictions remain ignored; compact metrics record their hashes and all frozen Phase 2B diagnostic
slices.
