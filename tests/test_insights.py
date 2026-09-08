import pytest

from hv import cleaning, eda, insights

SECTIONS = {
    "Overview": "Six customers, half of them churned.",
    "Cleaning": "Spellings unified, duplicates removed.",
    "Who churns": "New customers.",
    "Drivers": "Tenure and complaints.",
    "Recommendations": "Call new customers in their first month.",
}


@pytest.fixture
def stats_and_report(raw_frame):
    df, rep = cleaning.clean(raw_frame)
    return eda.stats(df), rep.to_dict()


def test_render_has_title_key_numbers_and_every_section_in_order(stats_and_report):
    s, rep = stats_and_report
    md = insights.render_insights(s, rep, SECTIONS)
    assert md.startswith("# ")
    assert "| Rows (clean) | 6 |" in md
    assert "| Churn rate | 50.0% |" in md
    positions = [md.index(f"## {name}") for name in insights.REQUIRED_SECTIONS]
    assert positions == sorted(positions)
    assert "Call new customers" in md


def test_render_refuses_a_missing_or_empty_section(stats_and_report):
    s, rep = stats_and_report
    missing = {k: v for k, v in SECTIONS.items() if k != "Drivers"}
    with pytest.raises(ValueError, match="Drivers"):
        insights.render_insights(s, rep, missing)
    empty = dict(SECTIONS, Drivers="   ")
    with pytest.raises(ValueError, match="Drivers"):
        insights.render_insights(s, rep, empty)


def test_render_ignores_unknown_sections(stats_and_report):
    s, rep = stats_and_report
    md = insights.render_insights(s, rep, dict(SECTIONS, Extra="should not appear"))
    assert "should not appear" not in md


def test_key_numbers_match_detects_a_typed_number(stats_and_report):
    s, rep = stats_and_report
    md = insights.render_insights(s, rep, SECTIONS)
    assert insights.key_numbers_match(md, s, rep)
    tampered = md.replace("| Churn rate | 50.0% |", "| Churn rate | 45.0% |")
    assert not insights.key_numbers_match(tampered, s, rep)
