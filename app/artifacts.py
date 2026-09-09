"""Read what the last successful run published.

The app never computes anything: it renders `artifacts/`. Either half may be missing (a fresh clone,
or Crew 2 not published yet), so every loader reports `available` instead of raising.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import markdown as md

from hv.config import ARTIFACTS_DIR
from hv.contract import Contract, load_contract

MD_EXTENSIONS = ["tables", "sane_lists"]


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_markdown(path: Path) -> str:
    try:
        return md.markdown(path.read_text(encoding="utf-8"), extensions=MD_EXTENSIONS)
    except OSError:
        return ""


@dataclass
class Crew1:
    available: bool = False
    contract: Contract | None = None
    stats: dict = field(default_factory=dict)
    cleaning: dict = field(default_factory=dict)
    insights_html: str = ""
    clean_csv: Path | None = None
    eda_report: Path | None = None


@dataclass
class Crew2:
    available: bool = False
    metrics: dict | None = None
    model_card_html: str = ""
    evaluation_html: str = ""
    model_path: Path | None = None
    features_csv: Path | None = None


def load_crew1(root: Path = ARTIFACTS_DIR) -> Crew1:
    d = Path(root) / "crew1"
    contract_path, clean = d / "dataset_contract.json", d / "clean_data.csv"
    if not (contract_path.exists() and clean.exists()):
        return Crew1()
    return Crew1(
        available=True,
        contract=load_contract(contract_path),
        stats=_read_json(d / "stats.json") or {},
        cleaning=_read_json(d / "cleaning_report.json") or {},
        insights_html=_read_markdown(d / "insights.md"),
        clean_csv=clean,
        eda_report=d / "eda_report.html",
    )


def load_crew2(root: Path = ARTIFACTS_DIR) -> Crew2:
    d = Path(root) / "crew2"
    metrics = _read_json(d / "metrics.json")
    if metrics is None:
        return Crew2()
    return Crew2(
        available=True,
        metrics=metrics,
        model_card_html=_read_markdown(d / "model_card.md"),
        evaluation_html=_read_markdown(d / "evaluation_report.md"),
        model_path=d / "model.joblib",
        features_csv=d / "features.csv",
    )


def load_run(root: Path = ARTIFACTS_DIR) -> dict:
    """The cost and duration of the run that produced these artifacts (crew 1's meta, plus crew 2's)."""
    one = _read_json(Path(root) / "crew1" / "run_meta.json") or {}
    two = _read_json(Path(root) / "crew2" / "run_meta.json") or {}
    merged = dict(one)
    for key in ("llm_calls", "cost_usd", "duration_s"):
        if key in two:
            merged[key] = round(merged.get(key, 0) + two[key], 4)
    merged["crew1"], merged["crew2"] = one, two
    return merged


# ---------------------------------------------------------------- display helpers
def _fmt_number(value: float) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:g}"


def contract_rows(contract: Contract | None) -> list[dict]:
    """One row per column, with the constraint written the way a person reads it."""
    if contract is None:
        return []
    rows = []
    for spec in contract.columns:
        if spec.allowed_values is not None:
            constraint = ", ".join(spec.allowed_values)
        elif spec.min is not None and spec.max is not None:
            constraint = f"{_fmt_number(spec.min)} to {_fmt_number(spec.max)}"
        else:
            constraint = ""
        rows.append(
            {
                "name": spec.name,
                "dtype": spec.dtype,
                "role": spec.role,
                "unit": spec.unit or "",
                "constraint": constraint,
                "nulls": f"{spec.null_count:,}" if spec.nullable else "none",
                "description": spec.description,
                "rationale": spec.rationale,
            }
        )
    return rows


def ranked_importances(metrics: dict | None, limit: int = 10) -> list[tuple[str, float]]:
    """Importances sorted by value. metrics.json is written sorted by key, so ranking happens here."""
    if not metrics:
        return []
    items = [(k, float(v)) for k, v in (metrics.get("importances") or {}).items()]
    return sorted(items, key=lambda kv: -kv[1])[:limit]


def _std(value) -> float | None:
    return value.get("std") if isinstance(value, dict) else None


def variant_rows(metrics: dict | None) -> list[dict]:
    """The model comparison table: baseline first, then variants, the served one marked."""
    if not metrics:
        return []
    def cell(v):
        return v.get("mean") if isinstance(v, dict) else v

    rows = []
    base = metrics.get("baseline") or {}
    if base:
        rows.append(
            {
                "name": "baseline (majority)",
                "roc_auc": cell(base.get("roc_auc")),
                "precision_at_top10": base.get("precision_at_top10"),
                "f1": cell(base.get("f1")),
                "served": False,
            }
        )
    for name, v in (metrics.get("variants") or {}).items():
        rows.append(
            {
                "name": name,
                "roc_auc": cell(v.get("roc_auc")),
                "roc_auc_std": _std(v.get("roc_auc")),
                "precision_at_top10": v.get("precision_at_top10"),
                "f1": cell(v.get("f1")),
                "served": name == metrics.get("served"),
            }
        )
    return rows
