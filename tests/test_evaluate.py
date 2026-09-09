"""M4 task 2: the measurements themselves, checked against numbers worked out by hand."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from hv.contract import build_contract
from hv.evaluate import (
    METRIC_NAMES,
    cv_scores,
    fairness_by_group,
    feature_importances,
    majority_baseline,
    oof_proba,
    precision_at_top,
)
from hv.features import build_features, feature_columns, make_preprocessor
from tests.synthetic import training_frame, write_frame


@pytest.fixture
def trained_setup(tmp_path):
    """A 200-row frame, its contract, the feature matrix and an untrained logistic pipeline."""
    df = training_frame(200)
    contract = build_contract(df, "tests/synthetic.py", write_frame(df, tmp_path / "clean_data.csv"))
    features = build_features(df, contract)
    numeric, categorical = feature_columns(contract)
    pipe = Pipeline(
        [
            ("pre", make_preprocessor(
                numeric + ["cashback_per_order", "orders_per_tenure_month", "coupon_rate"],
                categorical + ["recency_bucket"],
            )),
            ("model", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)),
        ]
    )
    X = features.drop(columns=["CustomerID", "Churn"])
    return pipe, X, features["Churn"], df


# ---------------------------------------------------------------- the baseline
def test_majority_baseline_on_a_four_row_label():
    out = majority_baseline([0, 0, 0, 1])
    assert out["predicted_class"] == 0
    assert out["accuracy"] == 0.75  # right about the three who stayed, wrong about the one who left
    assert out["recall"] == 0.0 and out["precision"] == 0.0
    assert out["roc_auc"] == 0.5  # a constant answer ranks nobody
    assert out["pr_auc"] == 0.25 and out["precision_at_top10"] == 0.25


def test_majority_baseline_follows_the_majority():
    assert majority_baseline([1, 1, 1, 0])["predicted_class"] == 1


# ---------------------------------------------------------------- precision at the top of the list
def test_precision_at_top_on_a_hand_made_ranking():
    y = [1, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    perfect = [0.99, 0.98, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
    assert precision_at_top(y, perfect, frac=0.20) == 1.0  # both churners are the top two
    assert precision_at_top(y, perfect, frac=0.10) == 1.0  # top 1 of 10
    backwards = [0.1, 0.1, 0.99, 0.98, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4]
    assert precision_at_top(y, backwards, frac=0.20) == 0.0


def test_precision_at_top_always_takes_at_least_one_customer():
    assert precision_at_top([1, 0, 0], [0.9, 0.1, 0.1], frac=0.01) == 1.0


# ---------------------------------------------------------------- fairness
def test_fairness_by_group_counts_each_group_separately():
    y_true = [1, 1, 0, 0, 1, 1, 0, 0]
    y_pred = [1, 0, 0, 0, 1, 1, 1, 0]
    groups = pd.Series(["Male"] * 4 + ["Female"] * 4)
    out = fairness_by_group(y_true, y_pred, groups)
    assert set(out) == {"Male", "Female"}
    assert out["Male"] == {"n": 4, "recall": 0.5, "precision": 1.0, "positive_rate": 0.25}
    assert out["Female"] == {"n": 4, "recall": 1.0, "precision": 0.6667, "positive_rate": 0.75}


def test_fairness_ignores_rows_with_no_group():
    groups = pd.Series(["Male", "Male", None, "Female"])
    out = fairness_by_group([1, 0, 1, 1], [1, 0, 1, 1], groups)
    assert set(out) == {"Male", "Female"}
    assert out["Male"]["n"] == 2 and out["Female"]["n"] == 1


# ---------------------------------------------------------------- cross-validation
def test_cv_scores_returns_every_documented_key(trained_setup):
    pipe, X, y, _ = trained_setup
    scores = cv_scores(pipe, X, y)
    assert set(scores) == set(METRIC_NAMES) | {"precision_at_top10"}
    for name in METRIC_NAMES:
        assert set(scores[name]) == {"mean", "std"}
        assert 0.0 <= scores[name]["mean"] <= 1.0
        assert scores[name]["std"] >= 0.0


def test_cv_scores_beat_the_baseline_on_data_with_a_real_signal(trained_setup):
    pipe, X, y, _ = trained_setup
    scores = cv_scores(pipe, X, y)
    assert scores["roc_auc"]["mean"] > majority_baseline(y)["roc_auc"]
    assert scores["precision_at_top10"] > majority_baseline(y)["precision_at_top10"]


def test_cv_scores_are_the_same_on_two_runs(trained_setup):
    pipe, X, y, _ = trained_setup
    assert cv_scores(pipe, X, y) == cv_scores(pipe, X, y)


def test_out_of_fold_probabilities_cover_every_row_once(trained_setup):
    pipe, X, y, _ = trained_setup
    proba = oof_proba(pipe, X, y)
    assert proba.shape == (len(X),)
    assert ((proba >= 0.0) & (proba <= 1.0)).all()
    assert len(np.unique(proba)) > len(X) // 2  # real predictions, not a constant


# ---------------------------------------------------------------- importances
def test_feature_importances_name_the_raw_columns(trained_setup):
    pipe, X, y, _ = trained_setup
    fitted = pipe.fit(X, y)
    importances = feature_importances(fitted, X, y)
    assert set(importances) == set(X.columns)
    assert list(importances.values()) == sorted(importances.values(), reverse=True)
    assert importances["Tenure"] > 0  # the signal the synthetic frame was built around
