# Phase 5 closeout

1. **Starting checkpoint:** clean synchronized `main` (`0/0`) at Phase 4 commit
   `773d335e594ca63537aa5ae23b98386737a6d823`; validation-v1 was unchanged.
2. **Persistence public result:** diagnostic SHA-256
   `edf8a40f74ab227e0485b02a4cf489893a3118dda2eafc896a8ffd063b9de9c7` scored
   0.886420231 on 2026-09-07 (user-reported Zindi interface), was rejected, and has no supplied
   rank. P3-M3B improves on it by 0.120011702. Leaderboard observations are provisional.
3. **CatBoost configuration:** pinned open-source `catboost==1.2.8`; persistence-residual target;
   P3-M3B's 12 no-year features plus canonical location ID categorical; full deterministic
   2,000,000-row population; 200 iterations, learning rate 0.05, depth 8, seed 20260907, CPU and
   two threads; recursion and early stopping disabled; no sweep. Feasibility observed 16.3 GB
   total/4.9 GB available RAM and 51.0 GB free disk; projected peak 2.86 GB, so no cap was used.
4. **CatBoost results:** pooled 0.609267883; F01 0.619263310; F02 0.598950309; horizons 1--7:
   0.552914878, 0.617548684, 0.630971890, 0.615721325, 0.658132163, 0.668989072,
   0.700675044. Observed/masked: 0.552914878/0.635663359. Recent: 0.602517579 versus P3-M3B
   0.562831897. Coverage was 551,965/551,965 (100%).
5. **Promotion decision:** rejected. It failed the pooled <=0.578923, fold-stability, horizons
   6/7, and recent-period gates; coverage, memory, leakage, and safe-fallback checks passed.
6. **Candidate:** none; no production fit, submission file, validation, or upload was performed.
7. **Runtime and memory:** 413.00 seconds total; 2,442.94 MB measured peak RSS. Fold runtimes were
   186.48 and 199.80 seconds.
8. **Files changed:** `configs/phase5.yaml`, `src/drought_forecasting/phase5_catboost.py`,
   `tests/test_phase5_catboost.py`, `reports/phase5_results.json`, persistence result JSON,
   this closeout, `experiments/registry.csv`, `reports/final_report_outline.md`, `pyproject.toml`,
   and `uv.lock`. Model and OOF evidence remains under ignored `artifacts/phase5/`.
9. **No unnecessary reruns:** no Phase 0--4 model or prior submission was rerun. CatBoost fitted
   exactly once across two folds. One initial command failed before import or fitting and was
   corrected by setting the source-layout import path; no experiment was repeated.
10. **Final recommended model:** retain P3-M3B as the production reference.
11. **Inputs required for finalization:** official report template/rubric and page/word limits;
    confirmed competition submission deadline and operational covariate-availability statement;
    any final public rank snapshots explicitly intended for time-stamped reporting; and approval
    to create the final notebook/report artifacts in the separate finalization phase.
