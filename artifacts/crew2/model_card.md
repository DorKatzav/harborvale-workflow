# Model card - churn prediction (hist_gb)

## Purpose

_Written by scripts/run_crew2_tools.py; the Model Governance Officer replaces this in M5._

## Training data

_Written by scripts/run_crew2_tools.py; the Model Governance Officer replaces this in M5._

- Source: `ecommerce_churn.xlsx [E Comm] -> hv.cleaning.clean -> clean_data.csv`
- Rows: 5073; columns declared in the contract: 20
- Model inputs: 13 numeric, 3 categorical, 4 engineered
- Churn rate: 0.1658
- Columns with nulls kept and declared: 7 (1675 values, imputed inside the model pipeline)
- Clean file sha256: `ef1e1f758009fa575837a3b4b62384c1f3516297d775aa2c10ef796a449073a2`

## Metrics

_Written by scripts/run_crew2_tools.py; the Model Governance Officer replaces this in M5._

| model | roc_auc | pr_auc | f1 | precision | recall | accuracy | precision@top10 |
|---|---|---|---|---|---|---|---|
| baseline (majority) | 0.5000 | 0.1658 | 0.0000 | 0.0000 | 0.0000 | 0.8342 | 0.1658 |
| logreg | 0.8913 ± 0.0169 | 0.6860 ± 0.0201 | 0.5985 ± 0.0176 | 0.4726 ± 0.0120 | 0.8157 ± 0.0302 | 0.8186 ± 0.0065 | 0.7712 |
| random_forest | 0.9769 ± 0.0088 | 0.9164 ± 0.0196 | 0.8436 ± 0.0293 | 0.8587 ± 0.0243 | 0.8300 ± 0.0429 | 0.9491 ± 0.0090 | 0.9487 |
| **hist_gb** (served) | 0.9857 ± 0.0051 | 0.9504 ± 0.0204 | 0.9028 ± 0.0214 | 0.9341 ± 0.0190 | 0.8740 ± 0.0319 | 0.9689 ± 0.0066 | 0.9724 |

### Fairness by protected attribute

| attribute | group | n | recall | precision | flagged |
|---|---|---|---|---|---|
| Gender | Female | 2026 | 0.8900 | 0.9228 | 0.1471 |
| Gender | Male | 3047 | 0.8647 | 0.9407 | 0.1605 |
| MaritalStatus | Divorced | 848 | 0.9032 | 0.9655 | 0.1368 |
| MaritalStatus | Married | 2672 | 0.8675 | 0.8912 | 0.1100 |
| MaritalStatus | Single | 1553 | 0.8699 | 0.9576 | 0.2428 |

Gender and MaritalStatus are never model inputs; they are measured here to show whether the served model treats the groups differently anyway.

## Limitations

_Written by scripts/run_crew2_tools.py; the Model Governance Officer replaces this in M5._

## Ethical considerations

_Written by scripts/run_crew2_tools.py; the Model Governance Officer replaces this in M5._
