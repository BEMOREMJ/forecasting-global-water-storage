# Final report outline

Phase 1 structural, availability, mask, leakage, validation-design, and implementation evidence
is closed. `validation-v1` is frozen with deterministic F01/F02 audits. Model scores,
model-dependent robustness, and operational-deployment evidence remain pending.

1. **Problem and operational context** — scope and users; pending.
2. **Data and prediction-time availability** — 2,154,021 Train rows, 280,961 Test rows,
   15,715 shared locations, discontinuous monthly coverage, schemas and identifier construction
   documented in `docs/data_dictionary.md` and `docs/phase1a_structural_audit.md`. Supplied
   current covariates are permitted under matched competition conditions; operational
   publication timing remains unresolved as documented in `docs/prediction_time_availability.md`.
3. **Leakage prevention** — exact calendar joining is required: target equals same-location
   `t+1` TWS for all 1,992,901 verifiable rows, with zero mismatches; 161,120 rows lack supplied
   exact-next-month TWS. Stable threats and invariants cover event/release cutoffs, immutable
   provenance, fold-local fitting, mask independence, validation uniqueness, policy isolation,
   and artifact compatibility. Phase 1F implementation is complete; see
   `docs/leakage_threat_register.md`.
4. **Validation methodology** — proposed `validation-v1` fits once at fixed origins
   F01=`2004-09` and F02=`2008-12`, then simulates each complete 40-month Test-shaped window
   under exact own-template-path masks and observed-only TWS. Of 15,715 Test locations, 15,226
   have all 18 rows and 489 have sparse official paths, accounting for 1,909 omitted slots that
   remain absent. F01 retains 15,526 locations/278,059 template rows and F02 retains 15,233
   locations/273,906 rows, with zero incomplete rows among retained paths. Its 551,965 pooled
   rows have zero cross-fold target-key overlap. Origins, ranking, horizons, and overlaps remain
   unchanged. Selection used a recency-first structural rule frozen before model results; the
   Phase 1G audit reproduced all counts twice. See
   `docs/phase1c_test_mask_and_horizons.md` and `docs/phase1e_validation_design.md`.
5. **Baselines** — definitions and measured results; pending.
6. **Model architecture** — final approach and parameters; pending.
7. **Innovation** — evidence against the official expectation; pending.
8. **Results** — Test horizon counts are structurally established; model metrics remain pending.
9. **Robustness** — required diagnostics are fixed for horizons, observed/masked inputs,
   predefined SPEI bins, and latitude bands. The selected folds exclude 671 fold-location
   instances representing 617 unique locations, with spatially non-uniform attrition; measured
   metric results remain pending.
10. **Practical deployment** — current-covariate publication latency is unresolved; no
   operational claim will be made without evidence. Other latency and deployment work is pending.
11. **Reproducibility** — frozen YAML, deterministic compact manifest, source/data hashes,
    seeds, and tested validation infrastructure are complete; model artifacts remain pending.
12. **References and artifact manifest** — pending.

## Official trustworthiness sections

Each section is limited to 100 words in the official PDF; model-dependent prose and evidence
remain pending.

### Data & Model Bias (maximum 100 words)

Pending: assessment of the spatially masked grid and unequal history coverage, mitigation,
unresolved bias and likely impact.

### Model Transparency (maximum 100 words)

Pending: interpretability method, influential features, figures and unexpected findings.

### Approach Reusability (maximum 100 words)

Pending: adaptability, flexibility choices and limitations across contexts or lead times.

### Sustainability and Efficiency (maximum 100 words)

Pending: measured environmental impact, optimizations, and complexity/efficiency trade-offs.
