# Competition rules: confirmed evidence and open questions

This summary is evidence from the Phase 0A audit, not a replacement for the official rules.
The competition page was retrieved in a JavaScript-limited, unauthenticated form.

## Confirmed rules

- **Task:** predict global Total Water Storage for calendar month `t+1`. Masked test `TWS_t`
  creates stated effective horizons of approximately 1–7 months. Only information available
  at or before `t` may be used; future observations cannot fill or infer masked TWS. (Webpage
  Info section; starter notebook cells 1 and 5, markdown.)
- **Evaluation:** leaderboard RMSE is 50%, AI trustworthiness is 30%, and innovation and
  practicality is 20%. (Webpage Evaluation section.) The webpage states RMSE but does not
  reproduce its mathematical formula.
- **Submission:** exactly `ID` and `Target`; all test entries required; row order irrelevant.
  (Webpage Evaluation section; notebook cells 32, 35–37.)
- **Limits:** 5 processed submissions daily and 200 overall. Two submissions must be selected
  for private judging; otherwise the two best public submissions are used. The better private
  score is displayed. (Webpage Rules and Submissions sections.)
- **Leaderboards:** approximately 30% public and 70% private. (Webpage Rules.)
- **Teams:** up to four; no multiple accounts, cross-team membership, or private code sharing
  outside a team. Team changes freeze in the final five days; submission histories affect
  merged-team allowance. (Webpage Teams and collaboration.)
- **Tools:** publicly available open-source languages, tools, and packages only. Openly
  available pretrained models are permitted. AutoML is prohibited. Paid services and
  card-required free trials are prohibited. (Webpage Rules and Reproducibility.)
- **External data:** only challenge data and freely, operationally available datasets; data
  should be available within one month of acquisition. Copernicus additions must exist at
  prediction time, exclude future GRACE/TWS information, and be documented. (Webpage Info and
  Datasets sections.)
- **Review:** top 10 receive a model/code/report request and have 72 hours to respond. Code
  must run, reproduce the score, and set seeds; custom notebook packages are not accepted.
  Zindi may separately request code during the challenge with 24 hours to respond. (Webpage
  Model/Code/Report Review, Reproducibility, and Monitoring.)
- **Trustworthiness:** Data & Model Bias, Model Transparency, Approach Reusability, and
  Sustainability & Efficiency; each final-report section has a 100-word maximum. (Official
  trustworthiness PDF page 1; simplified prompts on page 2.)
- **Innovation/practicality:** creative and practical approaches demonstrating adaptability,
  robustness, and real-world applicability. No more detailed rubric was found. (Webpage
  Phase Two Evaluation.)

## Official-source inconsistencies

- The Data tab says targets are in a separate CSV, while the visible file list has no label
  file and the notebook treats `target` as a Train column (notebook cells 5 and 19).
- The Evaluation section names a DOCX trustworthiness file, while the Data tab and official
  download provide `Trustworthiness_Evaluation.pdf`.

## Unresolved interpretations

The official materials do not settle AI coding-assistant use, free Google Colab use, the exact
AutoML boundary, deadline time/timezone, external-data cutoff semantics, recursive use of
predictions across effective horizons, reproducibility archive layout, internal
trustworthiness weights, or the detailed innovation rubric. These remain unresolved.

## Sources

- [Competition Info, Evaluation and Rules](https://zindi.world/competitions/one-step-ahead-of-drought-forecasting-global-water-storage-challenge)
- [Competition Data tab](https://zindi.world/competitions/one-step-ahead-of-drought-forecasting-global-water-storage-challenge/data)
- `references/official/StarterNotebook.ipynb` (37 cells; cell references above are 1-based)
- `references/official/Trustworthiness_Evaluation.pdf` (2 pages)

