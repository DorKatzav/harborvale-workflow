"""Shared fixtures: a small synthetic frame shaped like the real dataset (20 columns)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

COLUMNS = [
    "CustomerID", "Churn", "Tenure", "PreferredLoginDevice", "CityTier", "WarehouseToHome",
    "PreferredPaymentMode", "Gender", "HourSpendOnApp", "NumberOfDeviceRegistered", "PreferedOrderCat",
    "SatisfactionScore", "MaritalStatus", "NumberOfAddress", "Complain", "OrderAmountHikeFromlastYear",
    "CouponUsed", "OrderCount", "DaySinceLastOrder", "CashbackAmount",
]  # fmt: skip


def _row(cid, churn, tenure, device, pay, cat, order_count=3.0, cashback=150.0, gender="Male"):
    return [
        cid, churn, tenure, device, 1, 15.0, pay, gender, 3.0, 4, cat, 3, "Single", 2, 0, 15.0,
        1.0, order_count, 5.0, cashback,
    ]  # fmt: skip


@pytest.fixture
def raw_frame() -> pd.DataFrame:
    """8 rows: messy spellings, whitespace, an exact duplicate, a same-record/different-id pair, nulls."""
    rows = [
        _row(1, 1, 10.0, "Mobile Phone", "Debit Card", "Laptop & Accessory"),
        _row(2, 0, np.nan, "Phone", "CC", "Mobile"),  # three spellings to fix, null tenure
        _row(3, 0, 5.0, "Computer", "COD ", "Fashion"),                     # trailing whitespace + COD
        _row(4, 1, 2.0, "Computer", "E wallet", "Grocery", order_count=np.nan),
        _row(4, 1, 2.0, "Computer", "E wallet", "Grocery", order_count=np.nan),  # exact duplicate of 4
        _row(5, 0, 20.0, "Mobile Phone", "UPI", "Others", gender="Female"),
        _row(6, 0, 20.0, "Mobile Phone", "UPI", "Others", gender="Female"),  # same record as id 5, new id
        _row(7, 1, 1.0, "Mobile Phone", "Cash on Delivery", "Mobile Phone", cashback=324.99),
    ]
    return pd.DataFrame(rows, columns=COLUMNS)
