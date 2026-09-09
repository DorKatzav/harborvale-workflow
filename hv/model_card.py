"""The two documents Crew 2 publishes (PLAN.md §3.8).

Same split as everywhere else in this project: every number in these pages is read out of
`metrics.json` and the contract, and the agent supplies only the prose around them. An agent that
writes "the model is highly accurate" cannot change the table underneath it, and a missing section
is an error rather than a silently shorter document.
"""

from __future__ import annotations

from hv.contract import Contract
from hv.evaluate import METRIC_NAMES

REQUIRED_SECTIONS = ["Purpose", "Training data", "Metrics", "Limitations", "Ethical considerations"]


def _fmt(value: float) -> str:
    return f"{value:.4f}"


def _variant_table(metrics: dict) -> list[str]:
    """Baseline first, then every variant, so the comparison is unavoidable."""
    header = ["model", *METRIC_NAMES, "precision@top10"]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]

    baseline = metrics["baseline"]
    cells = [f"baseline ({baseline['strategy']})"]
    cells += [_fmt(baseline[name]) for name in METRIC_NAMES]
    cells.append(_fmt(baseline["precision_at_top10"]))
    lines.append("| " + " | ".join(cells) + " |")

    for name, scores in metrics["variants"].items():
        label = f"**{name}** (served)" if name == metrics["served"] else name
        cells = [label]
        cells += [f"{_fmt(scores[m]['mean'])} ± {_fmt(scores[m]['std'])}" for m in METRIC_NAMES]
        cells.append(_fmt(scores["precision_at_top10"]))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _fairness_table(metrics: dict) -> list[str]:
    fairness = metrics.get("fairness") or {}
    if not fairness:
        return ["_No fairness measurement in this run: the protected columns were not supplied._"]
    lines = ["| attribute | group | n | recall | precision | flagged |", "|---|---|---|---|---|---|"]
    for attribute, groups in fairness.items():
        for group, stats in groups.items():
            lines.append(
                f"| {attribute} | {group} | {stats['n']} | {_fmt(stats['recall'])} | "
                f"{_fmt(stats['precision'])} | {_fmt(stats['positive_rate'])} |"
            )
    return lines


def _importance_table(metrics: dict, top: int = 10) -> list[str]:
    """Sorted here, not trusted from the file: metrics.json is written with sorted keys, so the
    importances arrive back in alphabetical order and "the top ten" would be a top ten of nothing."""
    ranked = sorted(metrics.get("importances", {}).items(), key=lambda kv: kv[1], reverse=True)
    lines = ["| feature | permutation importance |", "|---|---|"]
    for name, value in ranked[:top]:
        lines.append(f"| {name} | {_fmt(value)} |")
    return lines


def render_evaluation_report(metrics: dict, narrative: dict[str, str]) -> str:
    """The comparison document: every variant against the baseline, plus the agent's reading of it."""
    served = metrics["served"]
    lines = [
        "# Evaluation report",
        "",
        f"Served model: **{served}**, chosen by cross-validated ROC-AUC over "
        f"{len(metrics['variants'])} variants on {metrics['n_rows']} rows "
        f"(churn rate {_fmt(metrics['positive_rate'])}).",
        "",
        "## Variants against the baseline",
        "",
        *_variant_table(metrics),
        "",
        "Scores are the mean and standard deviation over five stratified folds; "
        "`precision@top10` is measured on the out-of-fold ranking.",
        "",
        "## What the served model leans on",
        "",
        *_importance_table(metrics),
        "",
    ]
    for heading, text in narrative.items():
        lines += [f"## {heading}", "", text.strip(), ""]
    return "\n".join(lines).rstrip() + "\n"


def render_model_card(metrics: dict, c: Contract, sections: dict[str, str]) -> str:
    """The model card, with the five required headings and generated facts under two of them."""
    missing = [name for name in REQUIRED_SECTIONS if not (sections.get(name) or "").strip()]
    if missing:
        raise ValueError(f"the model card is missing {missing}; all of {REQUIRED_SECTIONS} are required")

    nullable = [col for col in c.columns if col.nullable]
    lines = [
        f"# Model card - churn prediction ({metrics['served']})",
        "",
        "## Purpose",
        "",
        sections["Purpose"].strip(),
        "",
        "## Training data",
        "",
        sections["Training data"].strip(),
        "",
        f"- Source: `{c.source}`",
        f"- Rows: {c.dataset.row_count}; columns declared in the contract: {len(c.columns)}",
        f"- Model inputs: {len(metrics['features']['numeric'])} numeric, "
        f"{len(metrics['features']['categorical'])} categorical, "
        f"{len(metrics['features']['engineered'])} engineered",
        f"- Churn rate: {_fmt(c.dataset.target_positive_rate)}",
        f"- Columns with nulls kept and declared: {len(nullable)} "
        f"({sum(col.null_count for col in nullable)} values, imputed inside the model pipeline)",
        f"- Clean file sha256: `{c.dataset.sha256}`",
        "",
        "## Metrics",
        "",
        sections["Metrics"].strip(),
        "",
        *_variant_table(metrics),
        "",
        "### Fairness by protected attribute",
        "",
        *_fairness_table(metrics),
        "",
        "Gender and MaritalStatus are never model inputs; they are measured here to show whether the "
        "served model treats the groups differently anyway.",
        "",
        "## Limitations",
        "",
        sections["Limitations"].strip(),
        "",
        "## Ethical considerations",
        "",
        sections["Ethical considerations"].strip(),
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"
