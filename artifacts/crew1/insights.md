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

This dataset is Harbor & Vale's cleaned customer file after preprocessing; 5,073 customer records remain. Overall churn is 16.6% (841 customers churned out of 5,073).

## Cleaning

The Data Quality Engineer removed 557 duplicate records (5630 rows came in, 5073 rows went out). They unified spellings in PreferredLoginDevice (Phone: 1231 rows), PreferredPaymentMode (CC: 273; COD: 365) and PreferedOrderCat (Mobile: 809). Data types were cast for CustomerID, Churn, CityTier, Complain, SatisfactionScore, NumberOfDeviceRegistered and NumberOfAddress. Columns intentionally left with missing values for the next crew: Tenure (231), WarehouseToHome (221), HourSpendOnApp (230), OrderAmountHikeFromlastYear (252), CouponUsed (210), OrderCount (243), DaySinceLastOrder (288). The cleaned CSV was written to: /Users/katzav/AI Developers Course/Projects/Final_Project/HarborVale_Workflow/runs/m5-real-run-2/crew1/clean_data.csv.

## Who churns

Highest churn: customers with Tenure 0-1 months churn at 51.3% (n=1,076). Lowest churn: customers who order Grocery churn at 4.4% (n=366).

## Drivers

Top correlates with churn are: Tenure (correlation -0.34), Complain (correlation 0.25), and DaySinceLastOrder (correlation -0.15). These suggest short-tenure customers, customers who have complained, and customers with longer gaps since their last order are the strongest statistical signals of higher churn; correlation is not causation.

## Recommendations

1) Launch a new-customer retention program targeting the Tenure 0-1 month cohort (51.3% churn, n=1,076): provide proactive onboarding touches and a time-limited incentive in the first month.
2) Institute a complaints rapid-response and recovery workflow: customers who complained churn at 31.3% versus 10.8% for others — set SLA targets for complaint resolution and attach a recovery offer when a complaint is closed.
3) Build automated re-engagement triggers based on DaySinceLastOrder (correlation -0.15): identify customers with growing inactivity and send win-back messages or targeted promotions; measure lift against the 16.6% baseline churn.

_Key numbers are rendered from stats.json and cleaning_report.json; the sections are written by the analyst crew._
