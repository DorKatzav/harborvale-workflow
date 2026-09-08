"""insights.md renderer: key numbers come from stats.json / cleaning_report.json, prose from the agent.

The agent never types a number into the table; it only writes the five sections. `key_numbers_match` lets
the gate prove the table in a committed insights.md still equals the measured files.
"""

from __future__ import annotations

REQUIRED_SECTIONS = ["Overview", "Cleaning", "Who churns", "Drivers", "Recommendations"]
TITLE = "# Insights — E-commerce Customer Churn (Harbor & Vale analyst crew)"


def key_numbers(stats: dict, cleaning_report: dict) -> list[tuple[str, str]]:
    fixes = sum(sum(v.values()) for v in cleaning_report.get("entity_fixes", {}).values())
    corr = stats.get("correlation_with_churn", {})
    top = stats.get("top_drivers", [])
    strongest = f"{top[0]} (r = {corr[top[0]]:+.2f})" if top else "n/a"
    first_month = stats.get("tenure_buckets", {}).get("0-1", {}).get("churn_rate")
    complain = stats.get("complain_churn_rate")
    rows = [
        ("Rows (raw)", f"{cleaning_report.get('rows_in', 0):,}"),
        ("Rows (clean)", f"{cleaning_report.get('rows_out', stats.get('n_rows', 0)):,}"),
        ("Duplicate records removed", f"{cleaning_report.get('duplicate_records_dropped', 0):,}"),
        ("Spelling fixes applied", f"{fixes:,}"),
        ("Churn rate", f"{stats['churn_rate']:.1%}"),
        ("Churned customers", f"{stats['churn_count']:,}"),
        ("Columns with missing values (kept)", str(len(stats.get("nulls", {})))),
        ("Strongest correlate of churn", strongest),
        ("Churn rate after a complaint", f"{complain:.1%}" if complain is not None else "n/a"),
        (
            "Churn rate in the first month (tenure 0-1)",
            f"{first_month:.1%}" if first_month is not None else "n/a",
        ),
    ]
    return rows


def render_key_numbers_table(stats: dict, cleaning_report: dict) -> str:
    lines = ["| Measure | Value |", "|---|---|"]
    lines += [f"| {label} | {value} |" for label, value in key_numbers(stats, cleaning_report)]
    return "\n".join(lines)


def render_insights(stats: dict, cleaning_report: dict, sections: dict[str, str]) -> str:
    """Markdown document; raises ValueError naming the first missing or empty required section."""
    for name in REQUIRED_SECTIONS:
        text = sections.get(name)
        if text is None or not str(text).strip():
            raise ValueError(f"missing or empty section: {name!r} (required: {REQUIRED_SECTIONS})")
    parts = [TITLE, "", "## Key numbers", "", render_key_numbers_table(stats, cleaning_report), ""]
    for name in REQUIRED_SECTIONS:
        parts += [f"## {name}", "", str(sections[name]).strip(), ""]
    parts.append(
        "_Key numbers are rendered from stats.json and cleaning_report.json; "
        "the sections are written by the analyst crew._"
    )
    return "\n".join(parts) + "\n"


def key_numbers_match(markdown: str, stats: dict, cleaning_report: dict) -> bool:
    return render_key_numbers_table(stats, cleaning_report) in markdown
