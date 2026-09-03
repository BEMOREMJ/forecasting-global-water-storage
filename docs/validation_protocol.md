# Validation protocol

**Status:** Frozen after deterministic Phase 1F/1G implementation audit
**Version:** `validation-v1`

The design evidence is in `docs/phase1e_validation_design.md`; the machine-readable freeze is
`configs/validation_protocol.yaml`, and `reports/validation_v1_manifest.json` records the
deterministic audit. Phase 1G reproduced every configured count and invariant twice.

The principal design uses fixed-cutoff, fit-once simulations at F01=`2004-09` and
F02=`2008-12`. Training requires `target_month <= fold_origin`; each complete
40-calendar-month Test-shaped window is then evaluated without learning from validation
targets. The two folds contain 551,965 pooled rows and have zero shared input or target keys.

Prediction-time controls are defined in `docs/prediction_time_availability.md`. Exact calendar
lags are mandatory, all learned transformations must fit inside each training fold, and the
principal policy keeps recursive TWS disabled. Any later-supported recursive policy must be
named and scored separately.

Phase 1C evidence is recorded in `docs/phase1c_test_mask_and_horizons.md`. The principal mask
policy is `mask-exact-complete-v1`: strict complete-location transplantation by relative calendar
offset and location. “Complete-location” means reproducing 100% of each location's own actual,
potentially sparse Test template path—not requiring all 18 global months. Official omitted rows
remain absent and are never labelled as masked. A shorter official path is not an exclusion
reason, but failure to reproduce any row in that path excludes the whole location. Partial
row-wise transplantation is rejected because missing anchors changed horizons. Synthetic
masking remains a named sensitivity and month-block masking is diagnostic only.

Fold selection used 42 eligible origins, 861 pairs, and 67 target-disjoint pairs. The
recency-first lexicographic rule was fixed before model results and selected `2004-09 + 2008-12`.
All 12 calendar months of the year must occur in pre-origin history. The location history gate
uses only pre-origin observations. Across the selected folds there are 671 excluded
fold-location instances representing 617 unique excluded locations.

Of 15,715 Test locations, 15,226 have all 18 rows and 489 have sparse paths; there are 1,909
official omitted location-month slots. F01 retains 15,526 locations and 278,059 template rows,
with 2,902 template rows belonging to excluded locations. F02 retains 15,233 locations and
273,906 template rows, with 7,055 belonging to excluded locations. Each retained location
reproduces every row in its own path, so both folds have zero incomplete-transplant rows among
retained locations. Fold origins, ranking, horizons, overlaps, and pooled total are unchanged.

Phase 1F.2 must map actual Test rows and must never synthesize a `15,715 × 18` row grid. Global
coverage of the 18 distinct relative input and target months is a separate origin-level check.

The principal comparison is row-weighted pooled OOF RMSE recomputed from SSE and count across
disjoint targets. Required diagnostics cover folds, horizons 1--7, observed/masked inputs,
predefined SPEI bins, and the fixed latitude bands `[-90,-60)`, `[-60,-30)`, `[-30,0)`,
`[0,30)`, `[30,60)`, and `[60,90]`. Longitude or coordinate-cell diagnostics are optional
Phase 2 additions only if defined before model comparison.

The Phase 1D threat model and stable test traceability IDs are defined in
`docs/leakage_threat_register.md`. Implementation must satisfy availability-aware target
separation, event cutoff, immutable provenance, fold-local fitting, mask independence,
validation uniqueness, policy isolation, and artifact compatibility. Documented Test structure
may inform validation; hidden outcomes and leaderboard feedback may not.

Fold origins and structural selection rules are frozen before model results and cannot be
changed in response to Phase 2 scores. The principal comparison is pooled row-level OOF RMSE;
fold RMSE and all horizon, mask-state, latitude-band, and SPEI-bin slices are diagnostic.
Scores from different policy IDs cannot be pooled. Every learned transform is fitted inside its
training fold. Future TWS, later-value backfill, and recursive TWS are prohibited under the
principal policy.
