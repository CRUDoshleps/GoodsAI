# Catalog-silver evaluation

Reference: noisy catalog. Role: development_feedback.
Independent human quality: N/A. Auto-accept: forbidden. Support matcher awaits human audit.

Cards: 3037; families: 1270; protected reserve: 40 (not predicted).

| Attribute | TP | FP | FN | Agreement P | R | F1 | Supported R | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| battery_mah | 122 | 3 | 1617 | 0.9760 | 0.0702 | 0.1309 | 0.9355 | 0.0670 |
| brand | 2324 | 156 | 713 | 0.9371 | 0.7652 | 0.8425 | 0.7665 | 0.8166 |
| capacity_l | 0 | 0 | 1 | N/A | 0.0000 | 0.0000 | N/A | 0.3675 |
| color | 1274 | 96 | 596 | 0.9299 | 0.6813 | 0.7864 | 0.9347 | 0.5690 |
| model | 553 | 155 | 582 | 0.7811 | 0.4872 | 0.6001 | 0.4872 | 0.6342 |
| power_w | 97 | 9 | 189 | 0.9151 | 0.3392 | 0.4949 | 0.8083 | 0.3594 |
| ram_gb | 1581 | 4 | 183 | 0.9975 | 0.8963 | 0.9442 | 0.9615 | 0.8300 |
| screen_inches | 12 | 0 | 288 | 1.0000 | 0.0400 | 0.0769 | 1.0000 | 0.0489 |
| storage_gb | 1559 | 2 | 244 | 0.9987 | 0.8647 | 0.9269 | 0.8667 | 0.8181 |

## Variants

| Method | Status | Catalog F1 |
|---|---|---:|
| rules | measured | 0.7567 |
| registry | not_run | N/A |
| gliner | not_run | N/A |
| llm | not_run | N/A |

## Interpretation

Unknown catalog labels are not negatives; wrong known values count FP+FN. See run_stats.json for denominators, unknown/conflict/support counts, slices and grouped CI.
Top-30 is a metadata ranking, not 30 implemented schemas. Current runtime supports two categories. Seller/brand crossings are disclosed; this split is not seller-disjoint.
Closed test was not evaluated. Old validation is feedback. A catalog mismatch may be a catalog error and requires adjudication.
Calibration: offline_fitted. Any fitted score remains offline and does not establish true correctness probability.
Current known adversarial failure RED SOLUTION/color remains outside this evaluator; this report does not certify release readiness.

Reproduction: docs/research/silver_evaluation_protocol.md and docs/SILVER_EVALUATION.md.
