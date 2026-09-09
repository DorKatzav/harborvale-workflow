"""M4 task 1: the contract decides what a feature is, and nothing that leaks can become one."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hv.features import (
    ENGINEERED,
    add_engineered,
    assert_no_leakage,
    build_features,
    feature_columns,
    make_preprocessor,
    raw_feature_names,
    write_features,
)
from tests.synthetic import clean_frame, write_frame


@pytest.fixture
def contract(tmp_path):
    from hv.contract import build_contract

    df = clean_frame()
    return build_contract(df, "tests/synthetic.py", write_frame(df, tmp_path / "clean_data.csv"))


@pytest.fixture
def four_rows():
    """Four rows chosen for the division rules: a normal one, zero orders, missing orders, missing tenure."""
    df = clean_frame().head(4).reset_index(drop=True)
    df.loc[:, "CashbackAmount"] = [100.0, 80.0, 60.0, 50.0]
    df.loc[:, "OrderCount"] = [4.0, 0.0, np.nan, 5.0]
    df.loc[:, "Tenure"] = [9.0, 3.0, 7.0, np.nan]
    df.loc[:, "CouponUsed"] = [2.0, 1.0, 3.0, 0.0]
    df.loc[:, "DaySinceLastOrder"] = [1.0, 5.0, 14.0, np.nan]
    return df


# ---------------------------------------------------------------- which columns are features
def test_feature_columns_leave_out_id_target_and_protected(contract):
    numeric, categorical = feature_columns(contract)
    chosen = set(numeric) | set(categorical)
    assert "CustomerID" not in chosen and "Churn" not in chosen
    assert "Gender" not in chosen and "MaritalStatus" not in chosen
    assert chosen == set(raw_feature_names(contract))
    assert len(chosen) == 16  # 20 columns minus id, target and two protected


def test_numeric_and_categorical_split_follows_the_contract(contract):
    numeric, categorical = feature_columns(contract)
    assert categorical == ["PreferredLoginDevice", "PreferredPaymentMode", "PreferedOrderCat"]
    assert "CityTier" in numeric  # cast to int by cleaning, so the contract calls it numeric
    assert set(numeric) & set(categorical) == set()


# ---------------------------------------------------------------- the engineered four
def test_rates_are_computed_per_row(four_rows):
    out = add_engineered(four_rows)
    assert out.loc[0, "cashback_per_order"] == pytest.approx(25.0)  # 100 / 4
    assert out.loc[0, "orders_per_tenure_month"] == pytest.approx(0.4)  # 4 / (9 + 1)
    assert out.loc[0, "coupon_rate"] == pytest.approx(0.5)  # 2 / 4
    assert out.loc[3, "cashback_per_order"] == pytest.approx(10.0)
    assert out.loc[3, "coupon_rate"] == pytest.approx(0.0)  # a real zero, not a missing value


def test_zero_orders_gives_a_missing_rate_not_an_infinity(four_rows):
    out = add_engineered(four_rows)
    assert pd.isna(out.loc[1, "cashback_per_order"])
    assert pd.isna(out.loc[1, "coupon_rate"])
    # 0 orders over 4 months is a real zero, not a missing value
    assert out.loc[1, "orders_per_tenure_month"] == pytest.approx(0.0)


def test_missing_inputs_stay_missing(four_rows):
    out = add_engineered(four_rows)
    assert pd.isna(out.loc[2, "cashback_per_order"])  # OrderCount is NaN
    assert pd.isna(out.loc[2, "orders_per_tenure_month"])
    assert pd.isna(out.loc[3, "orders_per_tenure_month"])  # Tenure is NaN
    assert pd.isna(out.loc[3, "recency_bucket"])  # DaySinceLastOrder is NaN


def test_recency_buckets_and_their_edges(four_rows):
    out = add_engineered(four_rows)
    assert list(out["recency_bucket"][:3]) == ["0-3", "4-7", "8-14"]  # 1, 5, 14 - 14 is an edge
    edges = add_engineered(four_rows.assign(DaySinceLastOrder=[0.0, 3.0, 7.0, 15.0]))
    assert list(edges["recency_bucket"]) == ["0-3", "0-3", "4-7", "15+"]


def test_add_engineered_says_what_it_is_missing(four_rows):
    with pytest.raises(ValueError, match="CashbackAmount"):
        add_engineered(four_rows.drop(columns=["CashbackAmount"]))


# ---------------------------------------------------------------- leakage
@pytest.mark.parametrize("column", ["CustomerID", "Churn", "Gender", "MaritalStatus"])
def test_leakage_check_refuses_id_target_and_protected(contract, column):
    with pytest.raises(ValueError, match=column):
        assert_no_leakage([column], contract)


def test_leakage_check_reports_every_offender_at_once(contract):
    with pytest.raises(ValueError) as e:
        assert_no_leakage(["Tenure", "Churn", "Gender"], contract)
    assert "Churn" in str(e.value) and "Gender" in str(e.value) and "Tenure" not in str(e.value)


def test_leakage_check_passes_the_real_feature_list(contract):
    assert_no_leakage(raw_feature_names(contract) + ENGINEERED, contract)  # does not raise


# ---------------------------------------------------------------- the features frame
def test_build_features_shape_and_order(contract):
    out = build_features(clean_frame(), contract)
    assert list(out.columns) == ["CustomerID", *raw_feature_names(contract), *ENGINEERED, "Churn"]
    assert len(out) == 20
    assert "Gender" not in out.columns and "MaritalStatus" not in out.columns


def test_build_features_refuses_a_column_the_contract_does_not_declare(contract):
    with pytest.raises(ValueError, match="SecretScore"):
        build_features(clean_frame().assign(SecretScore=1), contract)


def test_build_features_refuses_data_that_is_missing_a_declared_feature(contract):
    with pytest.raises(ValueError, match="Tenure"):
        build_features(clean_frame().drop(columns=["Tenure"]), contract)


def test_write_features_is_byte_identical_across_runs(contract, tmp_path):
    out = build_features(clean_frame(), contract)
    first = write_features(out, tmp_path / "a" / "features.csv")
    second = write_features(out, tmp_path / "b" / "features.csv")
    assert first == second
    assert (tmp_path / "a" / "features.csv").read_bytes() == (tmp_path / "b" / "features.csv").read_bytes()


# ---------------------------------------------------------------- the preprocessor
def test_preprocessor_fills_nulls_and_encodes_categories(contract):
    numeric, categorical = feature_columns(contract)
    out = build_features(clean_frame(), contract)
    pre = make_preprocessor(numeric + ["cashback_per_order"], categorical + ["recency_bucket"])
    matrix = pre.fit_transform(out)
    assert not np.isnan(matrix).any()  # every null was imputed inside the transformer
    assert matrix.shape[0] == len(out)
    assert matrix.shape[1] > len(numeric) + 1  # one-hot widened the categoricals


def test_preprocessor_ignores_a_category_it_has_never_seen(contract):
    numeric, categorical = feature_columns(contract)
    out = build_features(clean_frame(), contract)
    pre = make_preprocessor(numeric, categorical).fit(out)
    unseen = out.copy()
    unseen.loc[0, "PreferredPaymentMode"] = "Barter"
    assert pre.transform(unseen).shape == pre.transform(out).shape  # no crash, no new column
