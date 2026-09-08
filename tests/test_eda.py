import json

import pytest

from hv import cleaning, eda


@pytest.fixture
def clean_frame(raw_frame):
    df, _ = cleaning.clean(raw_frame)
    return df


def test_stats_churn_rate_and_counts(clean_frame):
    s = eda.stats(clean_frame)
    assert s["n_rows"] == 6 and s["n_cols"] == 20
    assert s["churn_count"] == 3
    assert s["churn_rate"] == pytest.approx(0.5)
    assert s["nulls"] == {"Tenure": 1, "OrderCount": 1}


def test_stats_churn_by_category_covers_every_string_column_and_city_tier(clean_frame):
    s = eda.stats(clean_frame)
    expected = [
        "PreferredLoginDevice", "PreferredPaymentMode", "Gender",
        "PreferedOrderCat", "MaritalStatus", "CityTier",
    ]  # fmt: skip
    for col in expected:
        assert col in s["churn_by_category"], col
    computer = s["churn_by_category"]["PreferredLoginDevice"]["Computer"]
    assert computer["n"] == 2 and computer["churn_rate"] == pytest.approx(0.5)


def test_stats_numeric_by_churn_and_correlations(clean_frame):
    s = eda.stats(clean_frame)
    assert set(s["numeric_by_churn"]["Tenure"]) == {"mean_churn", "mean_stay"}
    assert "CustomerID" not in s["correlation_with_churn"]
    assert "Churn" not in s["correlation_with_churn"]
    assert len(s["top_drivers"]) <= 5
    assert s["complain_churn_rate"] is None or 0 <= s["complain_churn_rate"] <= 1


def test_stats_tenure_buckets(clean_frame):
    s = eda.stats(clean_frame)
    assert list(s["tenure_buckets"]) == ["0-1", "2-6", "7-12", "13+"]
    assert s["tenure_buckets"]["13+"]["n"] == 1  # tenure 20


def test_write_stats_is_sorted_json(clean_frame, tmp_path):
    s = eda.stats(clean_frame)
    eda.write_stats(s, tmp_path / "stats.json")
    loaded = json.loads((tmp_path / "stats.json").read_text())
    assert loaded["churn_rate"] == pytest.approx(0.5)
    assert (tmp_path / "stats.json").read_text().startswith('{\n  "churn_by_category"')


def test_render_eda_html_is_self_contained(clean_frame, tmp_path):
    s = eda.stats(clean_frame)
    out = eda.render_eda_html(clean_frame, s, tmp_path / "eda_report.html")
    html = out.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert 'src="http' not in html and 'href="http' not in html
    assert html.count('src="data:image/png;base64,') >= 4
    assert "Churn rate" in html and "50.0%" in html
