# Evaluation report

Served model: **hist_gb**, chosen by cross-validated ROC-AUC over 3 variants on 5073 rows (churn rate 0.1658).

## Variants against the baseline

| model | roc_auc | pr_auc | f1 | precision | recall | accuracy | precision@top10 |
|---|---|---|---|---|---|---|---|
| baseline (majority) | 0.5000 | 0.1658 | 0.0000 | 0.0000 | 0.0000 | 0.8342 | 0.1658 |
| **hist_gb** (served) | 0.9857 ± 0.0051 | 0.9498 ± 0.0201 | 0.9033 ± 0.0216 | 0.9353 ± 0.0190 | 0.8740 ± 0.0319 | 0.9691 ± 0.0066 | 0.9724 |
| logreg | 0.8913 ± 0.0169 | 0.6860 ± 0.0201 | 0.5985 ± 0.0176 | 0.4726 ± 0.0120 | 0.8157 ± 0.0302 | 0.8186 ± 0.0065 | 0.7712 |
| random_forest | 0.9770 ± 0.0086 | 0.9170 ± 0.0196 | 0.8419 ± 0.0310 | 0.8566 ± 0.0278 | 0.8288 ± 0.0439 | 0.9485 ± 0.0096 | 0.9487 |

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
| DaySinceLastOrder | 0.0009 |
| NumberOfDeviceRegistered | 0.0009 |

## Reading

hist_gb is the served variant: it was selected because it led the evaluated models on the ranking metric used for the outreach call list and on overall discrimination. Compared with the majority baseline, it produces a much better prioritized call list by concentrating likely churners near the top so agents can target fewer customers for the same yield. The feature importances point to Tenure, Complain, and NumberOfAddress as the dominant signals, suggesting that short-tenure customers and those who lodged complaints are strong predictors — this is an association used by the model, not evidence those factors cause churn. One important open question the comparison does not settle is causal direction and subgroup calibration (for example whether these features proxy for protected groups or operational artifacts), so run subgroup calibration checks and consider A/B or causal studies before automating outreach.
