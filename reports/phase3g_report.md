# Phase 3G — P3-E1 guarded cross-fitted ensemble

## Final decision

**FAIL (valid artifact-only evidence).** Cross-fitted pooled RMSE was 0.571686, but horizon 6 exceeded its frozen Phase 2+0.005 protection limit. No production fit or submission is authorized.

## Readiness, pool, and optimizer

The expensive-run ledger remains exhausted at five: P3-D1, M1, M2, M3B, and M4. P3-E1 trained no model. The frozen pool was persistence, Phase 2 raw LightGBM, P3-M1, P3-M2, P3-M3B, and P3-M4. All saved OOF artifacts passed stored SHA-256, finite prediction, exact 551,965-row/F01 278,059/F02 273,906 count, unique-key, target/fold/horizon equality, ordering, validation identity, and comparable identity `2b27c3e0d376965789abab1b1f7dcf3577a8d15b374c03d0a312e39fb4607c0a` checks. Applicable provenance remains recursion-disabled.

Optimizer was frozen before execution: SciPy SLSQP, MSE objective, uniform 1/6 initialization, nonnegative simplex, no intercept/stabilizer/post-processing, tolerance 1e-12, maximum 1,000 iterations, feasibility tolerance 1e-8. All six fits succeeded in 14–27 iterations; sums differed from 1 by at most 2.2e-16 and minimum weights were >=0 within numerical precision.

## Directional weights

Order is persistence / Phase2 / M1 / M2 / M3B / M4.

| Learned on | G1 | G23 | G47 |
|---|---|---|---|
| F01 → F02 | .422852/.025650/.000000/.344271/.127636/.079592 | .160861/.000000/.000000/.517899/.281630/.039610 | .042582/.000000/.000000/.337981/.332738/.286699 |
| F02 → F01 | .321540/.000000/.000000/.508809/.000000/.169651 | .044344/.000000/.000000/.719627/.000000/.236029 | .000000/.007537/.242134/.530260/.008090/.211980 |

G1 consistently weighted persistence, M2 and M4, though M3B/Phase2 differed by direction. G23 consistently emphasized M2 but directional concentration differed materially. G47 consistently emphasized M2/M4, while F02 additionally assigned substantial M1 weight. Thus weights are directionally related but not stable enough to treat either direction as a production vector.

## Cross-fitting audit and results

Every F01 row used only F02-learned weights and vice versa; group membership used only effective horizon. Each row received one prediction with no fallback. A deliberate same-fold/swapped-direction test was rejected. In-fold optimizer objectives are diagnostics only and are not reported as validation performance.

| Slice | Rows | RMSE | Δ vs P3-M3B |
|---|---:|---:|---:|
| Pooled | 551,965 | 0.571686 | -0.012237 |
| F01 | 278,059 | 0.572481 | -0.010630 |
| F02 | 273,906 | 0.570878 | -0.013868 |
| G1 / h1 / observed | 184,416 | 0.500958 | -0.020356 |
| G23 | 214,780 | 0.586059 | -0.015206 |
| G47 | 152,769 | 0.628499 | -0.009279 |
| h2 | 122,824 | 0.578990 | -0.012415 |
| h3 | 91,956 | 0.595370 | -0.014096 |
| h4 | 61,207 | 0.587530 | -0.012588 |
| h5 | 30,599 | 0.617967 | -0.009614 |
| h6 | 30,500 | 0.655841 | +0.016620 |
| h7 | 30,463 | 0.687850 | +0.000086 |
| All masked | 367,549 | 0.604061 | -0.008870 |

Latitude RMSE: `[-60,-30)` .668214; `[-30,0)` .645183; `[0,30)` .568895; `[30,60)` .534430; `[60,90]` .560542; zero rows at `[-90,-60)`.

SPEI-bin RMSE in standard order `(-inf,-2),[-2,-1.5),[-1.5,-1),[-1,1),[1,1.5),[1.5,2),[2,inf)`: SPEI-01 .567883/.574884/.561203/.565236/.598666/.612691/.616199; SPEI-03 .616509/.558487/.549330/.566337/.598595/.636542/.637570; SPEI-06 .607197/.552758/.551585/.565885/.601611/.643744/.656703; SPEI-12 .606440/.576576/.568650/.568788/.581348/.598471/.553291. Counts match the frozen validation population documented in Phase 3E.

Context pooled RMSE: P3-E1 .571686; P3-M2 .581353; P3-M4 .583524; P3-M3B .583923; P3-M1 .589296; Phase 2 .592987; persistence .673722. Improvements were broad through G1/G23 and much of G47, but horizon 6 regressed sharply.

## Gates, production proposal, and artifacts

Pooled, both folds, exact coverage/identity, cross-fold leakage, deterministic routing, and no-fallback gates passed. Masked protection failed only at h6: .655841 > .648339. Therefore P3-E1 is not promotion-eligible.

If later approved, production group weights should be the arithmetic mean of the two directional vectors within each group, renormalized to one and frozen. Pooled OOF must not be re-optimized. This proposal was not executed and requires explicit approval.

Runtime was 85.15 seconds; peak RSS 4,375.61 MB. Configuration SHA-256: `1701fb02971d27f0a9e01bcca9638bdf5a192049b6e23a0c7b5e8bc94aa4eac5`. OOF: 33,573,412 bytes, SHA-256 `70ff16535490efe7e82f4788771fac854839c9a08b2cc132f13f1c4b942838e1`. Weight record: 3,750 bytes, SHA-256 `d9717dbb3ac5201db3d02f130dafe653cef64515369b33a677d6c94a2c850044`. Component identities and full optimizer diagnostics are in `reports/phase3e1_weights.json`.

Seven focused pre-run tests passed, including feasibility/determinism, mapping, and deliberate direction rejection. Optimization ran once with no failure or resume. Files created/changed: P3-E1 config, implementation, tests, weights, metrics, ignored OOF artifact, this report, and Phase 3 ledger. No LightGBM model trained; no prior prediction, feature, example, validation, or fold was regenerated. Validation-v1 remained unchanged. No production fit, submission, commit, push, upload, or remote change occurred.
