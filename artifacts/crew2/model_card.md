# Model card - churn prediction (hist_gb)

## Purpose

This score ranks customers by predicted risk of churn so the business can prioritize outreach and retention resources. It is a prioritization signal (a ranked list), not a verdict about any individual. The score should be interpreted as 'higher priority for retention action' rather than proof that a person will churn.

## Training data

Crew 2 only received the dataset contract and the cleaned file referenced in the contract. Inputs used to train the served model fall into three explicit groups that were derived from that file: numeric features (Tenure, CityTier, WarehouseToHome, HourSpendOnApp, NumberOfDeviceRegistered, SatisfactionScore, NumberOfAddress, Complain, OrderAmountHikeFromlastYear, CouponUsed, OrderCount, DaySinceLastOrder, CashbackAmount), categorical features (PreferredLoginDevice, PreferredPaymentMode, PreferedOrderCat), and engineered features (cashback_per_order, orders_per_tenure_month, coupon_rate, recency_bucket). The following columns were intentionally excluded from model inputs: CustomerID (role=id) because it is an identifier and would leak record identity and block traceability; Churn (role=target) because it is the label; Gender and MaritalStatus (role=protected) because they are protected attributes and must not be used as inputs in production models without an approved fairness and legal review. Note: a facts table listing the dataset contract and column-level metadata is included by the tool; the model card's Training data section complements that table with the explanations above.

- Source: `ecommerce_churn.xlsx [E Comm] -> hv.cleaning.clean -> clean_data.csv`
- Rows: 5073; columns declared in the contract: 20
- Model inputs: 13 numeric, 3 categorical, 4 engineered
- Churn rate: 0.1658
- Columns with nulls kept and declared: 7 (1675 values, imputed inside the model pipeline)
- Clean file sha256: `ef1e1f758009fa575837a3b4b62384c1f3516297d775aa2c10ef796a449073a2`

## Metrics

Comparison of the served variant (hist_gb) against the baseline (majority classifier). Baseline (majority): ROC-AUC = 0.50, PR-AUC = 0.1658, accuracy = 0.8342, precision = 0.0, recall = 0.0, F1 = 0.0, precision@top10 = 0.1658. Served (hist_gb): ROC-AUC = 0.9857 ± 0.0051, PR-AUC = 0.9498 ± 0.0201, accuracy = 0.9691 ± 0.0066, precision = 0.9353 ± 0.0190, recall = 0.8740 ± 0.0319, F1 = 0.9033 ± 0.0216, precision@top10 = 0.9724. Absolute margin of the served variant over baseline: ROC-AUC +0.4857, precision@top10 +0.8066. These numbers are the cross-validated evaluation results produced by the modelling run; a facts table reporting per-variant metrics is included by the tool alongside this text.

| model | roc_auc | pr_auc | f1 | precision | recall | accuracy | precision@top10 |
|---|---|---|---|---|---|---|---|
| baseline (majority) | 0.5000 | 0.1658 | 0.0000 | 0.0000 | 0.0000 | 0.8342 | 0.1658 |
| **hist_gb** (served) | 0.9857 ± 0.0051 | 0.9498 ± 0.0201 | 0.9033 ± 0.0216 | 0.9353 ± 0.0190 | 0.8740 ± 0.0319 | 0.9691 ± 0.0066 | 0.9724 |
| logreg | 0.8913 ± 0.0169 | 0.6860 ± 0.0201 | 0.5985 ± 0.0176 | 0.4726 ± 0.0120 | 0.8157 ± 0.0302 | 0.8186 ± 0.0065 | 0.7712 |
| random_forest | 0.9770 ± 0.0086 | 0.9170 ± 0.0196 | 0.8419 ± 0.0310 | 0.8566 ± 0.0278 | 0.8288 ± 0.0439 | 0.9485 ± 0.0096 | 0.9487 |

### Fairness by protected attribute

| attribute | group | n | recall | precision | flagged |
|---|---|---|---|---|---|
| Gender | Female | 2026 | 0.8900 | 0.9259 | 0.1466 |
| Gender | Male | 3047 | 0.8647 | 0.9407 | 0.1605 |
| MaritalStatus | Divorced | 848 | 0.9032 | 0.9655 | 0.1368 |
| MaritalStatus | Married | 2672 | 0.8709 | 0.8915 | 0.1104 |
| MaritalStatus | Single | 1553 | 0.8675 | 0.9600 | 0.2415 |

Gender and MaritalStatus are never model inputs; they are measured here to show whether the served model treats the groups differently anyway.

## Limitations

What this measurement does not cover: 1) No time-based split was used for evaluation — reported performance is from cross-validated/random splits and does not guarantee the same results under a production time-forward (temporal) split. 2) Null values present in the cleaned file were intentionally retained by the cleaning crew and were handled (imputed or encoded) by the modelling crew; results therefore depend on those imputation and feature-engineering choices and may change if an alternative imputation strategy is used. 3) Feature importance (and the model's use of a feature) is not evidence of causation: a feature registered as important by the model does not mean changing that feature will cause churn to change. 4) The evaluation reflects a single cleaned snapshot of the dataset (contracted sha256) and a single modelling run; it does not account for data drift, label bias, or upstream collection changes that could affect future performance. 5) Small subgroup sample sizes can make per-group metrics noisy; use statistical tests or larger samples before drawing strong fairness conclusions.

## Ethical considerations

Protected attributes (Gender and MaritalStatus) were excluded from model inputs per the dataset contract and product policy, but they were retained only for monitoring and fairness measurement. Per-group recalls from the served model: Gender — Female recall = 0.8900 (n=2026), Male recall = 0.8647 (n=3047); MaritalStatus — Divorced recall = 0.9032 (n=848), Married recall = 0.8709 (n=2672), Single recall = 0.8675 (n=1553). Precision and positive-rate differences are also reported in the fairness table included by the tool. Interpretation and required safeguards: small absolute differences in recall (on the order of a few percentage points) were observed; these are not necessarily unlawful or impermissible but must be reviewed with business context, legal counsel, and stakeholders before any operational decision that differentially affects people. The score must not be used as the sole basis for adverse automated actions (for example, denying service, terminating accounts, or other punitive decisions). It is intended for prioritization of outreach and should be combined with human review and business rules that mitigate potential disparate impacts. Finally, remember that the model's use of a feature is not a claim of causality — operational interventions should be validated via controlled experiments (A/B tests) rather than inferred from importance or correlations alone.
