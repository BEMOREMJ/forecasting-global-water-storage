# Leakage threat register

**Phase 1G implementation status:** the structural controls and test mappings required for
`validation-v1` are implemented and passed the deterministic full-data audit. Organizer-policy
and operational-data uncertainties remain separate; recursion stays disabled. Phase 2 feature
implementations must continue to satisfy fold-local fitting and timestamp/provenance controls.

**Status:** Phase 1D approved analysis
**Scope:** structural leakage controls and traceable Phase 1F test requirements. This register
does not select deferred Phase 2 feature families.

The fold implementation and exact structural expectations are defined in
`docs/phase1e_validation_design.md`. F01=`2004-09` and F02=`2008-12` are frozen after two
matching full-data audits reproduced their counts and invariants.

Here, “complete-location” always means complete relative to the location's own actual Test
template path. Test has 15,715 locations: 15,226 have 18 rows, 489 have shorter official paths,
and 1,909 location-month slots are officially omitted. Those omissions remain absent. F01
retains 15,526 locations/278,059 template rows and excludes 2,902 template rows; F02 retains
15,233 locations/273,906 template rows and excludes 7,055. Both retained cohorts have zero
incomplete-transplant rows. Phase 1F.2 must map actual Test rows, never a synthetic
`15,715 × 18` Cartesian grid.

Dispositions are `controlled now`, `requires Phase 1F implementation`, `requires organizer
clarification`, or `deferred beyond Phase 1`. Operational publication evidence is tracked
separately from organizer-controlled competition policy.

## Threat register

| ID | Stage | Failure mechanism and consequence | Severity | Preventive control | Automated assertion or test | Residual risk | Disposition |
|---|---|---|---|---|---|---|---|
| L001 | Fold construction | Random row splitting interleaves future months and repeated locations, producing optimistic RMSE. | Critical | Implement the fixed-cutoff, fit-once `validation-v1` origins and Test-shaped windows. | Reproduce documented boundaries and reject interleaved or non-monotonic partitions. | Configuration remains unfrozen until Phase 1G. | Requires Phase 1F implementation |
| L002 | Fold construction | Future-dated fitting rows or outcomes enter a validation event. Earlier target month alone is insufficient if the outcome was not genuinely released by the event. | Critical | Require input, target, and availability timestamps; every fitted outcome must be available by the simulated event. | Assert all fitted source and release timestamps are within the event cutoff. | Historical release metadata may be incomplete. | Requires Phase 1F implementation |
| L003 | Fold construction | Training and validation share a `(target_month, location)` key, directly duplicating an outcome. | Critical | Disjoint target keys. | Set-intersection assertion. | None when keys are correct. | Requires Phase 1F implementation |
| L004 | Feature construction | An adjacent later input exposes `TWS_t` equal to an earlier validation target. | Critical | Exclude sources after the event and embargo revealing rows where needed. | Adjacent-month fixture must detect exposure. | Incorrect timestamp metadata. | Requires Phase 1F implementation |
| L005 | TWS history | Future observed TWS enters lags, rolls, neighbours, or imputation. | Critical | Same-location provenance and source timestamp at or before the event. TWS at validation input month `t` is allowed only when explicitly supplied or historically simulated as observed. | Assert feature lineage and event cutoff. | Derived features may omit lineage. | Requires Phase 1F implementation |
| L006 | Missing-value handling | Later observed TWS backfills an earlier mask. | Critical | Prohibit backward fill; keep masked provenance immutable. | Masked-then-later-observed fixture remains unavailable at the earlier event. | Unsafe library defaults. | Requires Phase 1F implementation |
| L007 | Temporal features | Previous available row is mislabeled as the previous calendar month. | High | Exact calendar offsets only. | Gap fixture returns missing for absent `t-1`. | Shared utility can be bypassed. | Requires Phase 1F implementation |
| L008 | Lag/rolling features | A temporal window crosses the event or fold boundary. | Critical | Declare window bounds and audit every source member. | Reject any member after the event or outside the permitted partition. | Third-party transforms may hide membership. | Requires Phase 1F implementation |
| L009 | Learned transforms | Full-data climatology, encoder, scaler, imputer, spatial smoother, or trend model incorporates validation information. | High | Fit learned state inside each training fold. | Spy transformer records fit keys. | Hidden estimator state. | Requires Phase 1F implementation |
| L010 | Target transform | Global target normalization uses validation outcomes. | Critical | Fit target statistics on available fold-training outcomes only. | Assert normalization input keys and availability times. | Inverse-transform bookkeeping. | Requires Phase 1F implementation |
| L011 | Spatial features | Neighbour TWS comes from an unavailable date or location-unsafe join. | Critical | Fixed topology plus timestamp and provenance checks per value. | Safe/future/masked-neighbour fixture. | Learned topology may encode targets. | Requires Phase 1F implementation |
| L012 | Target aggregates | Spatial or temporal aggregates include same-row, validation, unreleased, or future targets. | Critical | Use only outcomes genuinely available by the event; out-of-fold construction for training rows. | Audit aggregate member keys and release times. | Sparse fallback may use global targets. | Requires Phase 1F implementation |
| L013 | Pipeline execution | Preprocessing is fit before fold splitting. | Critical | Split first and fit one pipeline state per fold. | Fit-call audit rejects validation IDs. | Manual preprocessing outside pipeline. | Requires Phase 1F implementation |
| L014 | Design and selection | Approved Test structure is incorrectly conflated with leakage, or prohibited evidence influences choices. IDs, dates, locations, supplied covariates, mask geometry, missingness, and effective-horizon distributions may inform competition-aligned validation. Hidden targets, leaderboard feedback, and post-submission outcomes may not inform validation or feature selection. | Critical | Record allowed structural inputs; freeze validation before modelling; prohibit outcome feedback in design and selection. | Manifest records design inputs and rejects hidden-target or submission-result fields. | Human judgment and undocumented feedback are not fully automatable. | Deferred beyond Phase 1 |
| L015 | Model selection | Repeated public-leaderboard feedback substitutes for frozen validation. | High | Select using the approved OOF protocol; cap and document submissions. | Registry requires validation evidence for selection decisions. | Informal human experimentation. | Deferred beyond Phase 1 |
| L016A | TWS provenance | Model-generated TWS is silently relabeled as genuinely observed, hiding error propagation and changing availability. | Critical | Implement immutable `observed`, `masked/unavailable`, and `model-generated` states regardless of organizer response. | Reject illegal provenance transitions and observed-only consumption of generated values. | External/manual artifacts may lack provenance. | Requires Phase 1F implementation |
| L016B | Recursive activation | Recursive predictions feed later Test events without confirmed permission or a distinct policy. | Critical | Keep recursion disabled by default. Activate only after organizer clarification, with a separately named sequential policy. | Configuration rejects recursive mode unless explicitly authorized and policy-labeled. | Organizer response may leave implementation details ambiguous. | Requires organizer clarification |
| L017 | Metric reporting | Recursive and observed-only predictions are pooled into one score. | High | Separate policy IDs, manifests, predictions, and scores. | Reject mixed-policy aggregation. | Readers may compare separate scores incorrectly. | Requires Phase 1F implementation |
| L018 | Validation manifest | Duplicate validation row IDs give some rows excess weight. | High | Unique row and target keys within each fold. | Count equals distinct-key count. | Join aliases can create duplicates. | Requires Phase 1F implementation |
| L019 | Cross-fold design | Validation rows or targets overlap across folds without an explicit diagnostic policy. | High | Principal OOF keys must be disjoint; proposed F01/F02 expectations are zero input-key and target-key overlap. | Pairwise intersections must reproduce zero shared keys and 551,965 distinct pooled targets. | Repeated diagnostics may legitimately overlap but cannot enter principal score. | Requires Phase 1F implementation |
| L020 | Historical masks | Validation outcome values influence mask generation or row retention. | Critical | Generate masks only from structural keys, approved Test template, configuration, and seed. | Target permutation leaves mask manifest and hash unchanged. | Origin choice could indirectly follow results. | Requires Phase 1F implementation |
| L021 | Mask transplantation | Partial reproduction of a location's actual Test path drops observed anchors but retains later masks, changing horizons; the best raw origin produced 87 mismatches and maximum 13. Expanding sparse official paths to 18 synthetic rows would also alter the task. | High | Reproduce 100% of each retained location's own actual Test path; keep official omissions absent. | Expected and matched path-row counts and intended/generated horizons must agree for every retained location and row. | Fewer retained locations. | Controlled now |
| B022 | Validation sampling | Complete-own-template-path filtering removes a small non-random spatial subset. This is representativeness bias, not leakage. | Medium | Use predefined origin criteria and fixed latitude bands; distinguish fold-location instances from unique locations. | Reproduce 671 excluded fold-location instances, 617 unique excluded locations, and band-level summaries. | Mild spatial-selection bias may remain. | Requires Phase 1F implementation |
| L023 | External/operational data | A revised product or value published after the event is used historically. | Critical | Versioned snapshots and independent publication-latency evidence. | Validate release/version timestamps where metadata exists. | Publication records may be incomplete; organizer rules do not establish real-world latency. | Deferred beyond Phase 1 |
| L024 | Identifier handling | Opaque high-cardinality IDs enable memorization or unintended date/location proxying. | Medium | Restrict IDs to alignment; parse only approved deterministic components. | Assert raw IDs absent from model features. | Explicit coordinate/time features may still overfit without leaking. | Requires Phase 1F implementation |
| L025 | Submission generation | Positional mismatch assigns predictions to the wrong Test IDs. | High | Validate by unique ID and restore official order. | Exact membership, uniqueness, and order checks. | Manual post-processing. | Requires Phase 1F implementation |
| L026 | Derived artifacts | A full-data, future-aware, stale, or incompatible cache is reused within a fold. | Critical | Artifact manifest records data scope, cutoff, fold, policy, code/config hash, and provenance. | Reject missing or incompatible metadata and forbidden dates. | Unregistered local files. | Requires Phase 1F implementation |
| L027 | Feature matrix | Train `target`, submission `Target`, or a renamed target enters model inputs. | Critical | Explicit feature allowlist and target denylist. | Reject target-like fields and verify feature lineage. | Renamed fields can evade name-only checks. | Requires Phase 1F implementation |

## Leakage invariants

1. **Availability-aware temporal separation:** every training target or historical outcome used
   for fitting is genuinely available by the simulated validation prediction event. Its target
   month being earlier than the validation target month is necessary but not sufficient when
   release timing differs.
2. **Event cutoff:** feature source timestamps never exceed the simulated prediction event.
3. **Immutable TWS provenance:** every TWS value is exactly `observed`, `masked/unavailable`, or
   `model-generated`, and its state is never silently changed.
4. **Calendar semantics:** exact calendar offsets are used for temporal features.
5. **Fold-local fitting:** every learned transformation is fitted only on its fold's training
   partition. Deterministic calendar and coordinate transforms require no fit.
6. **Outcome-independent masks:** historical masks are generated without examining validation
   target values.
7. **Transplant fidelity:** strict transplantation preserves the intended effective horizon for
   every retained row.
8. **Validation identity:** row and target keys are unique within folds and explicitly checked
   for cross-fold overlap.
9. **Policy isolation:** recursive and observed-only policies have separate manifests,
   predictions, and scores.
10. **Design independence:** hidden Test targets, submission outcomes, and leaderboard feedback
    never influence validation design. Approved supplied Test structure may inform it.
11. **Location isolation:** every TWS source and target comparison retains exact location identity.
12. **No future backfill:** later observations never fill or infer earlier masked values.
13. **Mask/calendar separation:** an absent released month remains absent, not masked.
14. **Artifact compatibility:** a derived artifact is consumed only when fold, cutoff, policy,
    data version, code, and configuration metadata match.
15. **Submission identity:** each prediction maps to exactly one official Test ID and final order
    matches SampleSubmission.

## Phase 1F test mapping

| Test ID | Synthetic fixture or bounded assertion | Threats/invariants |
|---|---|---|
| T001 | Two locations over a December-January transition with explicit event, target, and release times | L002-L005; invariants 1, 2, 11 |
| T002 | Exact `t-1` absent but an older row available | L007; invariants 4, 13 |
| T003 | Masked `t`, later observed `t+1`, earlier observed `t-1` | L005, L006; invariants 2, 3, 12 |
| T004 | Same dates at two locations with distinct TWS | L005, L011; invariant 11 |
| T005 | Rolling window with safe, future, and out-of-partition members | L008; invariants 2, 4 |
| T006 | Spy scaler, imputer, encoder, and smoother recording fit keys | L009, L013; invariant 5 |
| T007 | Target normalizer with different train and validation means and release times | L010; invariants 1, 5 |
| T008 | Neighbour graph with observed, future, masked, and generated values | L011, L016A; invariants 2, 3, 11 |
| T009 | Target aggregate containing same-row, validation, unreleased, and safe historical candidates | L012; invariants 1, 2, 5 |
| T010 | Permute validation targets while holding structural mask inputs fixed | L020; invariant 6 |
| T011 | Partial transplant with a missing observed anchor | L021; must be rejected after horizon mismatch |
| T012 | Strict transplant with both 18-row and shorter official paths; reproduce every actual path row and create no omitted slot | L021, B022; invariants 7, 13 |
| T013 | Reproduce zero input-key and target-key intersections between proposed F01/F02 and 551,965 distinct pooled targets | L018, L019; invariant 8 |
| T014 | Illegal provenance transitions and generated TWS in observed-only mode | L016A; invariants 3, 9 |
| T015 | Unauthorized recursive configuration and mixed-policy score aggregation | L016B, L017; invariant 9 |
| T016 | Feature matrix containing raw ID, target, placeholder, or renamed denylisted fields | L024, L027 |
| T017 | Shuffled predictions with missing, extra, or duplicate IDs | L025; invariant 15 |
| T018 | Cache with wrong fold, cutoff, policy, data, code, or configuration hash | L026; invariant 14 |
| T019 | Bounded Test horizon audit: observed inputs are horizon 1 and all sources are safe | L005-L007; invariants 2-4, 11-13 |
| T020 | Reproduce retained/excluded counts, 671 excluded fold-location instances, 617 unique excluded locations, and fixed latitude-band summaries | B022; representativeness reporting |
| T021 | Design manifest containing allowed Test structure versus forbidden outcome-feedback fields | L014, L015; invariant 10 |

Tests should use deterministic synthetic fixtures by default and bounded aggregate checks on
official data. They must not materialize persistent row-level competition artifacts.

## Risks not fully automatable

- Organizer permission and detailed rules for recursive prediction.
- Organizer intent behind the supplied mask.
- Real-world publication and revision timing when authoritative metadata is unavailable.
- Human use of leaderboard or post-submission feedback in feature or validation selection.
- Whether fold origins were chosen from structural criteria rather than remembered model scores.
- Practical significance of complete-own-template-path spatial-selection bias.
- External notebooks or scripts that bypass the registered pipeline.
- Undesirable proxy behavior that is not formal future-information leakage.

These require governance, frozen configurations, reviewable decisions, provenance records, and
manual review in addition to automated tests.

## Residual risk classification

### Structurally preventable leakage

Calendar joins, event and release cutoffs, immutable provenance, strict transplantation,
fold-local fitting, uniqueness checks, policy isolation, and artifact compatibility can be
implemented and asserted in Phase 1F.

### Deferred modelling choices

Climatologies, spatial smoothers, neighbour features, target encodings, trend models,
imputation strategies, and coordinate encodings are candidate families, not selected features.
Any later use remains subject to this register.

### Organizer-policy uncertainty

Recursive activation remains disabled pending organizer clarification. The unconditional
provenance implementation does not depend on that response.

### Operational-data uncertainty

Supplied current-month SPEI and soil moisture may be used under matched competition conditions.
Real-world publication latency and revisions require independent evidence; they are not settled
by organizer competition policy alone.

### Representativeness bias, not leakage

Strict transplantation of complete own-template paths preserves horizons but excludes a small
non-random subset. This is B022: a sampling-bias risk requiring exclusion counts and spatial
diagnostics, not a reason to weaken L021's structural horizon-fidelity control.
