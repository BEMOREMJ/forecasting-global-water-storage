# Phase 1 closeout

## 1. Final decision

**Conditional pass.** `validation-v1` is frozen, deterministic, and fully usable for principal
model comparison under `recursion-disabled-v1`. Organizer uncertainty affects only separately
named recursive policies and operational claims; it does not make the principal comparison
misleading. Phase 2 may proceed without recursion.

## 2. Starting and ending repository state

Phase 1 began from `main` at Phase 0 commit
`a352035b545681ab097dab725c18366e6283e1b4`, with no remote. Phase 1 ends on the same uncommitted
HEAD with reviewed source, tests, configuration, documentation, and compact reports in the
worktree. `implementation_commit` is explicitly `provisional`; the Phase 0 commit is not claimed
to contain Phase 1 code.

## 3. Phase 0 manifest verification

All five official files still match `configs/data_manifest.json`: SampleSubmission.csv
`6,105,524` bytes / `77881bc7...943db22`; Test.csv `34,365,988` /
`314da799...f61c196`; Train.csv `289,126,551` / `97ff1912...d94b1f`;
StarterNotebook.ipynb `1,236,676` / `a9adf72a...b3874b4`; and
Trustworthiness_Evaluation.pdf `94,458` / `217d7da3...e1c792`.

## 4. Exact structural findings

Train has 2,154,021 rows and Test has 280,961 rows. Test and SampleSubmission IDs align exactly
in order. Schemas, null counts, meanings, identifiers, and anomalies are frozen in
`docs/data_dictionary.md` and `docs/phase1a_structural_audit.md`.

## 5. Spatial-grid and temporal coverage

There are 15,715 shared half-degree locations. Exact coordinates, or lossless doubled-integer
coordinates, define locations. Timestamps are monthly but the panel is discontinuous; all joins,
lags, and rolling windows use calendar months. A previous available row is never treated as an
exact lag.

## 6. Empirical target semantics

For every row with an exact same-location next-calendar-month observation, target equals that
next-month TWS exactly: 1,977,398 Train-only and 15,503 Train/Test-boundary rows, with zero
mismatches. The remaining 161,120 rows are unverifiable because the successor is absent:
160,908 gap rows, 180 early-terminal rows, and 32 boundary rows.

## 7. Test mask and streak findings

Test contains 94,048 observed and 186,913 masked TWS inputs. Calendar-consecutive streaks are
the principal interpretation; released-row runs are separately diagnostic. Missing released
months remain absent and do not become masks. Later observations never fill earlier masks.

## 8. Effective-horizon definition and distribution

Horizon is the calendar-month distance from the most recent genuinely observed same-location
TWS to `input_month + 1`. Every observed input has horizon 1; all Test rows have a prior source.
The pooled frozen fold distribution is H1 184,416; H2 122,824; H3 91,956; H4 61,207; H5
30,599; H6 30,500; H7 30,463.

## 9. Prediction-time availability

Supplied current-row SPEI and soil moisture are permitted for competition validation under
matched conditions, while operational publication timing remains unresolved. Observed, masked,
and model-generated TWS provenance is immutable. Future observed TWS is prohibited. Learned
transformations fit only within the fold training partition; deterministic calendar and
coordinate transforms need no fitting.

## 10. Leakage threats and controls

`docs/leakage_threat_register.md` defines stable L/B and T identifiers. Controls enforce target
availability, timestamp cutoffs, exact calendar offsets, observed-only history, fold-local
fitting, target-independent masks, unique validation keys, policy isolation, source identities,
and row-free manifests. Complete-path selection effects are representativeness bias, not
leakage.

## 11. Candidate validation approaches

Candidates were exact Test-mask transplantation, deterministic synthetic masking, and a simple
month block. Exact strict transplantation best preserves location-specific mask paths and
horizons. Synthetic masking remains a named sensitivity. Month blocks remain diagnostic only.

## 12. Selected design and justification

The principal design is fixed-cutoff, fit-once, Test-shaped rolling-origin validation. From 42
eligible origins and 861 pairs, 67 pairs had disjoint target months. A recency-first
lexicographic rule frozen before model results selected F01=`2004-09` and F02=`2008-12`.
Coverage-first would select differently but was rejected. Exact target offsets make three
target-disjoint principal folds impossible.

## 13. Exact folds, counts, boundaries, and horizons

F01 has 359,007 fitting rows, 15,526 retained locations, 278,059 retained rows, and 189 excluded
locations representing 2,902 template rows. F02 has 1,155,158 fitting rows, 15,233 retained
locations, 273,906 retained rows, and 482 excluded locations representing 7,055 template rows.
The pool has 551,965 rows/distinct targets, 671 excluded fold-location instances, and 617 unique
excluded locations. Fold horizon counts and latitude exclusions are canonical in
`configs/validation_protocol.yaml` and `reports/validation_v1_manifest.json`.

Global origin coverage requires all 18 relative input and target months. Location mapping uses
only rows present in each official sparse Test path. A shorter official path is valid when
reproduced completely; missing historical reproduction excludes the whole location. The 1,909
official omitted slots remain absent. No `15,715 x 18` Cartesian expansion is permitted.

## 14. Metrics

The principal value is pooled row-level OOF RMSE computed as
`sqrt(total_SSE / total_row_count)`, never mean fold RMSE. Fold, horizon 1--7, observed/masked,
fixed latitude-band, and per-SPEI-bin metrics are diagnostic. Empty slices retain zero count and
SSE with null RMSE. Scores from different mask, provenance, recursion, or metric policy IDs are
never pooled.

## 15. Infrastructure implemented

`validation_core.py` implements calendar, location, provenance, and horizon semantics.
`validation_folds.py` implements sparse template extraction, transplantation, sequential folds,
and leakage assertions. `validation_metrics.py` implements deterministic metrics and slices.
`validation_audit.py` implements strict configuration, identities, canonical hashing, safe
compact output, and audit orchestration. Tests trace these controls to the threat register.

## 16. Determinism, runtime, and memory

Two frozen-YAML audits produced identical structural content. Hashes: configuration
`bbae77855ff0ec075067abbe404fcfd813dd2fe845343f49c68e43cb98519e0a`, relevant source
`cf05eb04d531b752256f5fc4341660991560e2fa34284f0ddf611614eef67015`, Test template
`78a51b2611a9c02dd0c7960bb25a23eae51d051a3d14dbb4cee18f75858072c8`, and structural audit
`dfafe4ae008ac4180f3f92a54ca825c779ab4768b0ba870e22dd1cd4e14088c9`.

Runs took 11.292 and 7.075 seconds and peaked at 460,423,168 and 451,878,912 bytes RSS. Minimum
available system memory was 2,658,775,040 and 2,728,534,016 bytes. DuckDB remained at two threads
and 2 GB. The older Phase 0 reserve threshold is recorded as a non-blocking amber advisory.

## 17. Files created or changed

Phase 1 adds structural, availability, mask, validation-design, leakage, and closeout documents;
four validation source modules; four corresponding test modules; and the compact validation
manifest. It updates the frozen YAML, evidence matrix, clarification register, validation
protocol, report outline, and concise README status. No protected data is versioned.

## 18. Tests and checks

Phase 1G production YAML parsing and two full audits passed. The focused validation suite passed
158 tests and the full suite passed 192. Compact-manifest validation, Ruff, `git diff --check`,
Markdown/link/path checks, official hashes, ignore checks, protected-path scanning, dry-run
staging, and registry emptiness verification also passed.

## 19. Rejected approaches

Rejected or demoted: random row splitting; shuffled cross-validation; partial row-wise mask
transplantation; universal 18-row Cartesian expansion; coverage-first selection; overlapping
three-fold principal OOF; arbitrary deletion of overlapping targets; synthetic or month-block
masking as principal design; recursion without permission; and mean fold RMSE as principal value.

## 20. Organizer questions and unresolved risks

Recursive prediction permission, AutoML and AI-assistant boundaries, operational publication
latency, external-data release semantics, deadline details, and review-package requirements
remain unresolved. A recursive policy, if authorized, must remain separately named and scored.
Complete-path filtering retains mild spatial-selection bias.

## 21. Recommended Phase 2 inputs

Use `configs/validation_protocol.yaml`, `reports/validation_v1_manifest.json`, the validation
APIs/tests, the availability policy, and the leakage register. Begin with recursion disabled,
calendar-exact features, fold-fitted transformations, pooled SSE/count reporting, and all frozen
diagnostics. Do not change origins or selection rules after observing model results.

## 22. Confirmation of no out-of-scope work

No model was trained or scored. No prediction, submission, external data, row-level validation
artifact, remote, push, or commit was created. Phase 2 was not begun.

## 23. Proposed commit contents excluding protected artifacts

The proposed Phase 1 commit contains only reviewed source, tests, configuration, documentation,
README status, `reports/validation_v1_manifest.json`, and this closeout. It excludes raw and
processed competition data, temporary files, models, predictions, submissions, credentials,
and row-level assignments.
