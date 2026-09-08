"""M4 task 4: the documents carry the agent's words and the code's numbers, never the reverse."""

from __future__ import annotations

import pytest

from hv.contract import build_contract
from hv.model_card import REQUIRED_SECTIONS, render_evaluation_report, render_model_card
from tests.synthetic import clean_frame, write_frame

METRICS = {
    "n_rows": 5073,
    "positive_rate": 0.1658,
    "features": {
        "numeric": ["Tenure"], "categorical": ["PreferredPaymentMode"], "engineered": ["coupon_rate"],
    },
    "baseline": {
        "strategy": "majority", "predicted_class": 0, "accuracy": 0.8342, "precision": 0.0,
        "recall": 0.0, "f1": 0.0, "roc_auc": 0.5, "pr_auc": 0.1658, "precision_at_top10": 0.1658,
    },
    "variants": {
        "logreg": {
            "roc_auc": {"mean": 0.8, "std": 0.01}, "pr_auc": {"mean": 0.5, "std": 0.02},
            "f1": {"mean": 0.5, "std": 0.02}, "precision": {"mean": 0.4, "std": 0.02},
            "recall": {"mean": 0.7, "std": 0.03}, "accuracy": {"mean": 0.75, "std": 0.01},
            "precision_at_top10": 0.55,
        },
        "hist_gb": {
            "roc_auc": {"mean": 0.95, "std": 0.01}, "pr_auc": {"mean": 0.8, "std": 0.02},
            "f1": {"mean": 0.7, "std": 0.02}, "precision": {"mean": 0.7, "std": 0.02},
            "recall": {"mean": 0.7, "std": 0.03}, "accuracy": {"mean": 0.9, "std": 0.01},
            "precision_at_top10": 0.9,
        },
    },
    "served": "hist_gb",
    "importances": {"Tenure": 0.12, "coupon_rate": 0.03},
    "fairness": {
        "Gender": {
            "Male": {"n": 3000, "recall": 0.7, "precision": 0.68, "positive_rate": 0.17},
            "Female": {"n": 2073, "recall": 0.66, "precision": 0.7, "positive_rate": 0.16},
        }
    },
    "versions": {"python": "3.11.16"},
}

SECTIONS = {name: f"prose for {name}" for name in REQUIRED_SECTIONS}


@pytest.fixture
def contract(tmp_path):
    df = clean_frame()
    return build_contract(df, "tests/synthetic.py", write_frame(df, tmp_path / "clean_data.csv"))


# ---------------------------------------------------------------- the model card
def test_every_required_heading_is_present_in_order(contract):
    card = render_model_card(METRICS, contract, SECTIONS)
    positions = [card.index(f"## {name}") for name in REQUIRED_SECTIONS]
    assert positions == sorted(positions)


@pytest.mark.parametrize("missing", REQUIRED_SECTIONS)
def test_a_missing_section_is_refused(contract, missing):
    sections = {k: v for k, v in SECTIONS.items() if k != missing}
    with pytest.raises(ValueError, match=missing):
        render_model_card(METRICS, contract, sections)


def test_an_empty_section_counts_as_missing(contract):
    with pytest.raises(ValueError, match="Limitations"):
        render_model_card(METRICS, contract, {**SECTIONS, "Limitations": "   "})


def test_the_agents_prose_reaches_the_page(contract):
    card = render_model_card(METRICS, contract, {**SECTIONS, "Purpose": "flag customers worth calling"})
    assert "flag customers worth calling" in card


def test_training_data_facts_come_from_the_contract_not_the_prose(contract):
    card = render_model_card(METRICS, contract, {**SECTIONS, "Training data": "about a million rows"})
    assert "about a million rows" in card  # the prose is kept
    assert f"Rows: {contract.dataset.row_count}" in card  # and contradicted by the measurement
    assert contract.dataset.sha256 in card


def test_the_fairness_table_is_rendered(contract):
    card = render_model_card(METRICS, contract, SECTIONS)
    assert "### Fairness by protected attribute" in card
    assert "| Gender | Male | 3000 |" in card
    assert "| Gender | Female | 2073 |" in card
    assert "never model inputs" in card


def test_a_run_without_fairness_says_so_instead_of_showing_an_empty_table(contract):
    card = render_model_card({**METRICS, "fairness": {}}, contract, SECTIONS)
    assert "No fairness measurement in this run" in card


def test_the_served_model_is_marked_in_the_table(contract):
    card = render_model_card(METRICS, contract, SECTIONS)
    assert "**hist_gb** (served)" in card
    assert "baseline (majority)" in card  # the comparison is unavoidable


# ---------------------------------------------------------------- the evaluation report
def test_the_evaluation_report_compares_every_variant_to_the_baseline():
    report = render_evaluation_report(METRICS, {"Reading": "the boosted model wins"})
    assert "baseline (majority)" in report
    for name in METRICS["variants"]:
        assert name in report
    assert "0.1658" in report  # the baseline's precision@top10, straight from metrics
    assert "## Reading" in report and "the boosted model wins" in report


def test_the_evaluation_report_lists_the_importances():
    report = render_evaluation_report(METRICS, {})
    assert "permutation importance" in report
    assert "| Tenure | 0.1200 |" in report


def test_importances_are_ranked_even_when_the_file_gives_them_alphabetically():
    """metrics.json is written with sorted keys, so the ranking has to be redone when rendering."""
    alphabetical = {"aardvark": 0.01, "zebra": 0.99}
    report = render_evaluation_report({**METRICS, "importances": alphabetical}, {})
    assert report.index("zebra") < report.index("aardvark")
