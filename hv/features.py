"""Crew 2's feature layer (PLAN.md §3.6).

Everything here reads the contract, never the raw data and never Crew 1's internals: the contract
says which columns are features, and a column it does not declare does not exist as far as this
module is concerned. Four engineered features turn raw counts into rates, because "500 in cashback"
means something different to a customer with fifty orders and to one with two.

Nulls are still nulls at this point - Crew 1 kept them on purpose and declared them. They are filled
inside the sklearn Pipeline, per fold, so that no fold ever learns from the rows it is scored on.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from hv.config import CSV_KW, PRIMARY_KEY, PROTECTED, TARGET
from hv.contract import Contract, file_sha256

ENGINEERED = ["cashback_per_order", "orders_per_tenure_month", "coupon_rate", "recency_bucket"]
ENGINEERED_NUMERIC = ["cashback_per_order", "orders_per_tenure_month", "coupon_rate"]
ENGINEERED_CATEGORICAL = ["recency_bucket"]

RECENCY_BINS = [-1, 3, 7, 14, np.inf]
RECENCY_LABELS = ["0-3", "4-7", "8-14", "15+"]
ENGINEERED_SOURCES = ["CashbackAmount", "OrderCount", "Tenure", "CouponUsed", "DaySinceLastOrder"]


def raw_feature_names(c: Contract) -> list[str]:
    """The columns the contract marks as features, in contract order."""
    return [col.name for col in c.columns if col.role == "feature"]


def feature_columns(c: Contract) -> tuple[list[str], list[str]]:
    """(numeric, categorical) raw features - the id, the target and the protected columns are not here."""
    features = [col for col in c.columns if col.role == "feature"]
    numeric = [col.name for col in features if col.dtype in ("int", "float")]
    categorical = [col.name for col in features if col.dtype in ("category", "bool")]
    return numeric, categorical


def assert_no_leakage(columns: list[str], c: Contract) -> None:
    """Refuse the identifier, the label and the protected attributes as model inputs.

    The identifier is a row number in disguise, the label is the answer, and Gender / MaritalStatus
    are a decision the design already made (D5). Each one produces a model that scores well and is
    worthless, or worse.
    """
    by_name = {col.name: col for col in c.columns}
    offenders = []
    for name in columns:
        spec = by_name.get(name)
        role = spec.role if spec else None
        if role in ("id", "target", "protected") or name in (PRIMARY_KEY, TARGET, *PROTECTED):
            offenders.append(f"{name} ({role or 'not declared'})")
    if offenders:
        raise ValueError(
            "these columns must never be model inputs: " + ", ".join(offenders)
        )


def add_engineered(df: pd.DataFrame) -> pd.DataFrame:
    """Add the four engineered features to a copy of the frame.

    A rate whose denominator is zero or missing is missing, not zero or infinity: "no orders" is not
    the same statement as "no cashback per order", and the imputer inside the Pipeline is the right
    place to decide what to do about it.
    """
    missing = [c for c in ENGINEERED_SOURCES if c not in df.columns]
    if missing:
        raise ValueError(f"cannot engineer features without {missing}")

    out = df.copy()
    orders = out["OrderCount"].where(out["OrderCount"] != 0)  # 0 and NaN both become NaN
    out["cashback_per_order"] = out["CashbackAmount"] / orders
    out["orders_per_tenure_month"] = out["OrderCount"] / (out["Tenure"] + 1)
    out["coupon_rate"] = out["CouponUsed"] / orders
    out["recency_bucket"] = pd.cut(
        out["DaySinceLastOrder"], bins=RECENCY_BINS, labels=RECENCY_LABELS
    ).astype(object)  # NaN stays NaN; object so the one-hot encoder sees plain strings
    return out


def build_features(df: pd.DataFrame, c: Contract) -> pd.DataFrame:
    """[id] + the contract's features + the engineered ones + [target], in that order."""
    raw = raw_feature_names(c)
    declared = {col.name for col in c.columns}

    undeclared = [name for name in df.columns if name not in declared]
    if undeclared:
        raise ValueError(
            f"column(s) {undeclared} are not declared in the contract; Crew 2 may only use what it declares"
        )
    needed = [PRIMARY_KEY, TARGET, *raw]
    absent = [name for name in needed if name not in df.columns]
    if absent:
        raise ValueError(f"the contract declares {absent}, but the data does not have those columns")

    assert_no_leakage(raw + ENGINEERED, c)
    out = add_engineered(df)
    return out[[PRIMARY_KEY, *raw, *ENGINEERED, TARGET]]


def make_preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    """Impute and scale inside the Pipeline, never before it.

    Imputing on the whole table before cross-validation leaks the test rows into the median every
    model then trains on. Here sklearn recomputes the median and the most frequent category from the
    training part of each fold alone.
    """
    numeric_steps = Pipeline(
        [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
    )
    categorical_steps = Pipeline(
        [
            ("impute", SimpleImputer(strategy="most_frequent")),
            # sparse_output=False: HistGradientBoosting cannot take a sparse matrix
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    return ColumnTransformer(
        [("num", numeric_steps, numeric), ("cat", categorical_steps, categorical)],
        remainder="drop",
    )


def write_features(fdf: pd.DataFrame, path: Path) -> str:
    """Write features.csv the way every data artifact here is written, and return its sha256."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fdf.to_csv(path, **CSV_KW)
    return file_sha256(path)
