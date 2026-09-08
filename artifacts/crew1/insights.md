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

Dataset: customer transactions cleaned to 5,073 rows. Headline churn is 16.6% (841 of 5,073 customers). This report summarizes who churns and the strongest statistical drivers found in the cleaned file.

## Cleaning

5630 rows came in and 5,073 rows went out after cleaning. We removed 557 duplicate records. We normalized spelling: PreferredLoginDevice 'Phone' across 1,231 rows; PreferredPaymentMode values 'CC' (273 rows) and 'COD' (365 rows); PreferedOrderCat 'Mobile' across 809 rows. We cast types for CustomerID, Churn, CityTier, Complain, SatisfactionScore, NumberOfDeviceRegistered, and NumberOfAddress. Missing values were intentionally kept for Tenure (231), WarehouseToHome (221), HourSpendOnApp (230), OrderAmountHikeFromlastYear (252), CouponUsed (210), OrderCount (243), and DaySinceLastOrder (288).

## Who churns

Highest churn: New customers (Tenure 0-1) churn at 51.3% (n=1,076). Lowest churn: customers preferring 'Grocery' churn at 4.4% (n=366). For context: single customers churn at 26.7% (n=1,553) while married customers churn at 11.3% (n=2,672).

## Drivers

Top correlations with churn (not causation): Tenure -0.34, Complain 0.25, DaySinceLastOrder -0.15, CashbackAmount -0.14, NumberOfDeviceRegistered 0.12. Interpretation: Tenure has the strongest negative relationship with churn (churn falls as tenure rises). Customers who complained have higher churn (31.3% vs 10.8%). DaySinceLastOrder shows a modest negative correlation and should be investigated further rather than assumed causal.

## Recommendations

1) Prioritize onboarding and retention for Tenure 0-1 customers: 1,076 customers churn at 51.3% — build an outreach workflow for this cohort and measure churn change.
2) Treat complainants as a high-retention-risk group: customers who complained churn at 31.3% versus 10.8% for non-complainers — add urgent complaint resolution plus targeted offers and track repeat churn.
3) Target payment-mode segments: COD users churn at 25.4% (n=457) and E-wallet users at 22.8% (n=562) versus Credit Card users at 14.2% (n=1,596) — run payment-specific incentives or friction-reduction experiments for COD and E-wallet cohorts.

_Key numbers are rendered from stats.json and cleaning_report.json; the sections are written by the analyst crew._
