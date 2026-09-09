"""Synthetic frames for the contract tests — no real data, no dependency on M1's output.

Same shape as the cleaned e-commerce churn file (`hv.cleaning.clean` output, PLAN.md §3.3): the 20
columns of the real dataset, canonical category values only (the entity map has already run), ints
where §3.3 casts to int, floats with nulls kept where the real file keeps them.

Twenty rows, and every nullable column holds several nulls on purpose: the `row_loss` preset drops
10% of the rows, and a column that lost its last null would read back from CSV as `int` and fail
the dtype check for the wrong reason.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from hv.config import CSV_KW

N = 20


def clean_frame() -> pd.DataFrame:
    """A clean, contract-abiding frame: 20 customers, 4 of them churned."""
    return pd.DataFrame(
        {
            "CustomerID": list(range(50001, 50001 + N)),
            "Churn": [0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0],
            "Tenure": [1.0, 4.0, None, 12.0, 7.0, 25.0, 3.0, None, 9.0, 18.0,
                       2.0, 30.0, None, 6.0, 11.0, 21.0, 1.0, 14.0, None, 8.0],
            "PreferredLoginDevice": ["Mobile Phone", "Computer"] * 10,
            "CityTier": [1, 2, 3] * 6 + [1, 2],
            "WarehouseToHome": [6.0, 8.0, 30.0, None, 15.0, 12.0, 9.0, 22.0, None, 11.0,
                                5.0, 18.0, 27.0, None, 13.0, 7.0, 33.0, 10.0, 16.0, None],
            "PreferredPaymentMode": ["Credit Card", "Debit Card", "Cash on Delivery", "E wallet", "UPI"] * 4,
            "Gender": ["Male", "Female"] * 10,
            "HourSpendOnApp": [3.0, 2.0, None, 4.0, 3.0, 1.0, 2.0, None, 3.0, 4.0,
                               2.0, 3.0, None, 2.0, 4.0, 3.0, 1.0, None, 2.0, 3.0],
            "NumberOfDeviceRegistered": [3, 4, 5, 2, 6, 3, 4, 5, 3, 2, 4, 6, 3, 5, 4, 2, 3, 6, 4, 5],
            "PreferedOrderCat": ["Mobile Phone", "Laptop & Accessory", "Fashion", "Grocery", "Others"] * 4,
            "SatisfactionScore": [3, 1, 5, 2, 4, 3, 1, 5, 2, 4, 3, 5, 1, 2, 4, 3, 5, 1, 2, 4],
            "MaritalStatus": ["Single", "Married", "Divorced", "Married"] * 5,
            "NumberOfAddress": [2, 5, 9, 1, 4, 7, 3, 6, 8, 2, 5, 1, 4, 9, 3, 7, 2, 6, 8, 5],
            "Complain": [0, 1, 1, 0, 0, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0, 1],
            "OrderAmountHikeFromlastYear": [11.0, 15.0, None, 20.0, 13.0, 18.0, None, 22.0, 14.0, 16.0,
                                            12.0, 24.0, 19.0, None, 17.0, 21.0, 13.0, 25.0, None, 15.0],
            "CouponUsed": [1.0, 2.0, None, 0.0, 4.0, 1.0, 3.0, None, 2.0, 5.0,
                           1.0, 0.0, None, 2.0, 6.0, 1.0, 3.0, None, 4.0, 2.0],
            "OrderCount": [2.0, 4.0, None, 1.0, 7.0, 3.0, 5.0, None, 4.0, 9.0,
                           2.0, 1.0, None, 6.0, 12.0, 3.0, 8.0, None, 5.0, 4.0],
            "DaySinceLastOrder": [3.0, 7.0, None, 1.0, 15.0, 5.0, 9.0, None, 4.0, 20.0,
                                  2.0, 11.0, None, 6.0, 8.0, 13.0, 1.0, None, 17.0, 5.0],
            "CashbackAmount": [120.5, 155.25, 98.75, 210.4, 143.6, 176.8, 112.35, 189.9, 134.15, 201.7,
                               107.45, 165.3, 128.6, 195.05, 149.8, 118.25, 183.5, 139.95, 171.15, 126.7],
        }
    )


def write_frame(df: pd.DataFrame, path: Path) -> Path:
    """Write a frame the way Crew 1 writes `clean_data.csv` (byte-identical settings)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, **CSV_KW)
    return path


def training_frame(n: int = 300, seed: int = 7) -> pd.DataFrame:
    """A bigger frame with a churn signal in it, for the cross-validation and training tests.

    Same 20 columns as `clean_frame`, but generated: tenure and complaints drive the label, so a
    model can actually learn something and the tests can assert it beats the majority baseline.
    Nulls are sprinkled through the columns that hold them in the real file.
    """
    rng = np.random.default_rng(seed)
    tenure = rng.integers(0, 36, n).astype(float)
    complain = rng.integers(0, 2, n)
    orders = rng.integers(1, 15, n).astype(float)
    risk = 1 / (1 + np.exp(-(0.9 - 0.16 * tenure + 1.1 * complain)))  # tuned for roughly the real churn rate
    churn = (rng.random(n) < risk).astype(int)

    df = pd.DataFrame(
        {
            "CustomerID": np.arange(60001, 60001 + n),
            "Churn": churn,
            "Tenure": tenure,
            "PreferredLoginDevice": rng.choice(["Mobile Phone", "Computer"], n),
            "CityTier": rng.integers(1, 4, n),
            "WarehouseToHome": rng.integers(5, 35, n).astype(float),
            "PreferredPaymentMode": rng.choice(
                ["Credit Card", "Debit Card", "Cash on Delivery", "E wallet", "UPI"], n
            ),
            "Gender": rng.choice(["Male", "Female"], n),
            "HourSpendOnApp": rng.integers(1, 5, n).astype(float),
            "NumberOfDeviceRegistered": rng.integers(2, 7, n),
            "PreferedOrderCat": rng.choice(
                ["Mobile Phone", "Laptop & Accessory", "Fashion", "Grocery", "Others"], n
            ),
            "SatisfactionScore": rng.integers(1, 6, n),
            "MaritalStatus": rng.choice(["Single", "Married", "Divorced"], n),
            "NumberOfAddress": rng.integers(1, 10, n),
            "Complain": complain,
            "OrderAmountHikeFromlastYear": rng.integers(11, 26, n).astype(float),
            "CouponUsed": rng.integers(0, 7, n).astype(float),
            "OrderCount": orders,
            "DaySinceLastOrder": rng.integers(0, 21, n).astype(float),
            "CashbackAmount": np.round(rng.uniform(95.0, 320.0, n), 2),
        }
    )
    for column in ("Tenure", "HourSpendOnApp", "CouponUsed", "OrderCount", "DaySinceLastOrder"):
        holes = rng.choice(n, size=max(1, n // 25), replace=False)
        df.loc[holes, column] = np.nan
    return df
