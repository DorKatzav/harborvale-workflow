# Insights — E-commerce Customer Churn (Harbor & Vale analyst crew)

## Key numbers

| Measure | Value |
|---|---|
| Rows (raw) | 5,630 |
| Rows (clean) | 5,073 |
| Duplicate records removed | 557 |
| Spelling fixes applied | 2,678 |
| Churn rate | 16.6% |
| Churned customers | 841 |
| Columns with missing values (kept) | 7 |
| Strongest correlate of churn | Tenure (r = -0.34) |
| Churn rate after a complaint | 31.3% |
| Churn rate in the first month (tenure 0-1) | 51.3% |

## Overview

Dataset: 5,630 raw rows ingested and 5,073 rows after cleaning. Headline churn rate is 16.6% (841 customers churned).

## Cleaning

I profiled and cleaned the workbook: 5,630 rows in → 5,073 rows out; 557 duplicate records were removed. I standardized label inconsistencies: PreferredLoginDevice 'Phone' standardized (1,231 rows), PreferredPaymentMode values unified for 'CC' (273) and 'COD' (365), and PreferedOrderCat 'Mobile' standardized (809). I cast CustomerID, Churn, CityTier, Complain, SatisfactionScore, NumberOfDeviceRegistered, and NumberOfAddress to integer types. I intentionally kept nulls for later review: Tenure (231), WarehouseToHome (221), HourSpendOnApp (230), OrderAmountHikeFromlastYear (252), CouponUsed (210), OrderCount (243), DaySinceLastOrder (288).

## Who churns

Highest churn: customers with Tenure 0–1 month churn at 51.3% (n=1,076). Lowest churn: Grocery customers churn at 4.4% (n=366).

## Drivers

Top correlations with churn (two-decimal): Tenure -0.34, Complain 0.25, DaySinceLastOrder -0.15, CashbackAmount -0.14, NumberOfDeviceRegistered 0.12. These statistics suggest newer customers and customers who have complained are associated with higher churn; the negative Tenure correlation aligns with the 51.3% churn in the 0–1 month group. The negative correlation for DaySinceLastOrder (-0.15) is unexpected and should be investigated further. Correlation is not causation.

## Recommendations

1) Run an intensive onboarding and early-engagement program for customers in Tenure 0–1 month (51.3% churn, n=1,076): automated welcome messages, a 2-week follow-up, and a first-order discount; measure 30-day churn reduction.

2) Implement a complaints rapid-response and escalation workflow: customers who complained churn at 31.3% versus 10.8% for non-complainers. Set a same-day triage SLA and track complaint-to-churn conversion.

3) Target the Mobile Phone order category (26.3% churn, n=1,855) with category-specific retention offers and UX/payment nudges; run a COD (25.4% churn, n=457) payment-education pilot to reduce friction.

_Key numbers are rendered from stats.json and cleaning_report.json; the sections are written by the analyst crew._
