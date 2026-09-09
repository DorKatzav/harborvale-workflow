"""M4 task 3: three variants, one served, and a metrics file that says the same thing twice."""

from __future__ import annotations

import json

import joblib
import pytest

from hv.contract import build_contract
from hv.features import ENGINEERED, build_features
from hv.train import METRICS_FILE, MODEL_FILE, VARIANTS, predict_one, train_all
from tests.synthetic import training_frame, write_frame


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    """One real training run on 300 synthetic rows, shared by the tests that only read it."""
    tmp = tmp_path_factory.mktemp("trained")
    df = training_frame(300)
    contract = build_contract(df, "tests/synthetic.py", write_frame(df, tmp / "clean_data.csv"))
    features = build_features(df, contract)
    protected = df[["CustomerID", "Gender", "MaritalStatus"]]
    metrics = train_all(features, contract, tmp / "crew2", protected=protected)
    return metrics, tmp / "crew2", df


def test_all_three_variants_are_scored(trained):
    metrics, _, _ = trained
    assert set(metrics["variants"]) == set(VARIANTS)
    assert len(metrics["variants"]) >= 3  # the brief asks for at least three
    for scores in metrics["variants"].values():
        assert scores["roc_auc"]["mean"] > 0.0


def test_the_served_variant_is_the_best_one_by_roc_auc(trained):
    metrics, _, _ = trained
    best = max(metrics["variants"], key=lambda n: metrics["variants"][n]["roc_auc"]["mean"])
    assert metrics["served"] == best


def test_the_served_model_beats_the_majority_baseline(trained):
    metrics, _, _ = trained
    served = metrics["variants"][metrics["served"]]
    assert served["roc_auc"]["mean"] > metrics["baseline"]["roc_auc"]
    assert served["precision_at_top10"] > metrics["baseline"]["precision_at_top10"]


def test_nothing_that_leaks_reached_the_feature_lists(trained):
    metrics, _, _ = trained
    listed = set(metrics["features"]["numeric"] + metrics["features"]["categorical"])
    assert not listed & {"CustomerID", "Churn", "Gender", "MaritalStatus"}
    assert metrics["features"]["engineered"] == ENGINEERED
    assert set(metrics["importances"]) == listed | set(ENGINEERED)


def test_fairness_is_measured_on_the_protected_columns(trained):
    metrics, _, _ = trained
    assert set(metrics["fairness"]) == {"Gender", "MaritalStatus"}
    for groups in metrics["fairness"].values():
        for stats in groups.values():
            assert set(stats) == {"n", "recall", "precision", "positive_rate"}
            assert stats["n"] > 0


def test_fairness_is_empty_and_honest_when_the_columns_are_not_supplied(tmp_path):
    df = training_frame(120)
    contract = build_contract(df, "s", write_frame(df, tmp_path / "clean_data.csv"))
    metrics = train_all(build_features(df, contract), contract, tmp_path / "crew2")
    assert metrics["fairness"] == {}  # no protected frame, no invented numbers


def test_metrics_json_is_written_and_matches_what_was_returned(trained):
    metrics, out_dir, _ = trained
    on_disk = json.loads((out_dir / METRICS_FILE).read_text(encoding="utf-8"))
    assert on_disk == metrics
    assert "trained_at" not in on_disk  # D-M4-2: the clock lives in run_meta.json


def test_the_model_loads_and_scores_one_contract_shaped_row(trained):
    metrics, out_dir, df = trained
    bundle = joblib.load(out_dir / MODEL_FILE)  # our own artifact, written by train_all above
    assert bundle["served"] == metrics["served"]
    probability = predict_one(out_dir / MODEL_FILE, df.iloc[0].to_dict())
    assert 0.0 <= probability <= 1.0


def test_predict_one_says_what_a_row_is_missing(trained):
    _, out_dir, df = trained
    row = df.iloc[0].to_dict()
    del row["Tenure"]
    with pytest.raises(ValueError, match="Tenure"):
        predict_one(out_dir / MODEL_FILE, row)


def test_two_runs_write_an_identical_metrics_file(tmp_path):
    df = training_frame(150)
    contract = build_contract(df, "s", write_frame(df, tmp_path / "clean_data.csv"))
    features = build_features(df, contract)
    protected = df[["CustomerID", "Gender", "MaritalStatus"]]
    train_all(features, contract, tmp_path / "a", protected=protected)
    train_all(features, contract, tmp_path / "b", protected=protected)
    assert (tmp_path / "a" / METRICS_FILE).read_bytes() == (tmp_path / "b" / METRICS_FILE).read_bytes()
