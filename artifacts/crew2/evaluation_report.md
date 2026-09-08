# Evaluation report

Served model: **hist_gb**, chosen by cross-validated ROC-AUC over 3 variants on 5073 rows (churn rate 0.1658).

## Variants against the baseline

| model | roc_auc | pr_auc | f1 | precision | recall | accuracy | precision@top10 |
|---|---|---|---|---|---|---|---|
| baseline (majority) | 0.5000 | 0.1658 | 0.0000 | 0.0000 | 0.0000 | 0.8342 | 0.1658 |
| logreg | 0.8913 ± 0.0169 | 0.6860 ± 0.0201 | 0.5985 ± 0.0176 | 0.4726 ± 0.0120 | 0.8157 ± 0.0302 | 0.8186 ± 0.0065 | 0.7712 |
| random_forest | 0.9769 ± 0.0088 | 0.9164 ± 0.0196 | 0.8436 ± 0.0293 | 0.8587 ± 0.0243 | 0.8300 ± 0.0429 | 0.9491 ± 0.0090 | 0.9487 |
| **hist_gb** (served) | 0.9857 ± 0.0051 | 0.9504 ± 0.0204 | 0.9028 ± 0.0214 | 0.9341 ± 0.0190 | 0.8740 ± 0.0319 | 0.9689 ± 0.0066 | 0.9724 |

Scores are the mean and standard deviation over five stratified folds; `precision@top10` is measured on the out-of-fold ranking.

## What the served model leans on

| feature | permutation importance |
|---|---|
| Tenure | 0.0889 |
| Complain | 0.0209 |
| NumberOfAddress | 0.0090 |
| WarehouseToHome | 0.0043 |
| CashbackAmount | 0.0035 |
| SatisfactionScore | 0.0023 |
| orders_per_tenure_month | 0.0017 |
| PreferredPaymentMode | 0.0012 |
| NumberOfDeviceRegistered | 0.0009 |
| DaySinceLastOrder | 0.0009 |

## Reading

_Written by scripts/run_crew2_tools.py; the Model Governance Officer replaces this in M5._
