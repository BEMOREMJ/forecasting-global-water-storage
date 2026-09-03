# Organizer clarification register

These questions have not been sent or answered.

## Unresolved policy questions

1. Are AI coding assistants such as ChatGPT or Codex permitted, and is disclosure required?
2. What precisely counts as prohibited AutoML, including tuning and pipeline-search tools?
3. May earlier model predictions feed later masked months without violating future-information
   rules? If permitted, must generated values remain explicitly distinguished from observed TWS?
4. How is each effective 1–7-month horizon defined for evaluation and validation?

5. Are supplied current-month SPEI and soil-moisture values considered available at the
   prediction event for operational forecasting, or are they competition-only conveniences?
6. What observation, processing, publication, and revision dates apply to those supplied
   current-month covariates?

These questions do not block Phase 2 under frozen `recursion-disabled-v1`. Recursive results,
if later authorized, require a separately named policy and may never be pooled with the
principal observed-only score. Operational forecasting claims remain deferred until publication
latency is established.

## Must resolve before external-data use

1. What event defines “available within one month”: observation, acquisition, processing, or release?
2. Must external data have been public before competition launch, or only by prediction time?
3. What versioning and evidence prove historical prediction-time availability?

## Must resolve before final submission

1. What exact time and timezone govern the deadline and final two-submission selection?
2. What files, layout, environment specification, weights, and hardware notes belong in the 72-hour package?
3. Do all top-10 participants submit model, code, and report despite the later code-only wording?
4. Are the four trustworthiness categories equally weighted within the 30%?
5. Is there a detailed rubric or template for innovation/practicality and the final report?

## Useful but non-blocking

1. Is free-tier Google Colab permitted for development and reproducibility?
2. Does the paid-service restriction cover every paid compute/storage service or only inaccessible tools?
3. Is the Train target intentionally embedded in `Train.csv`, despite the Data-tab wording?
4. Are there runtime limits or prescribed dependency-lock formats for reproducibility review?
