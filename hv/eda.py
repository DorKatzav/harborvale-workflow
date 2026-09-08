"""Descriptive statistics and a self-contained HTML EDA report (PLAN.md §3.4). No LLM, no external assets."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from hv.config import PRIMARY_KEY, TARGET  # noqa: E402

TENURE_BINS = [-0.5, 1.5, 6.5, 12.5, float("inf")]
TENURE_LABELS = ["0-1", "2-6", "7-12", "13+"]
CATEGORICAL_EXTRA = ["CityTier"]  # numeric by storage, categorical by meaning


def _is_text(s: pd.Series) -> bool:
    return pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s)


def _categorical_columns(df: pd.DataFrame) -> list[str]:
    cols = [c for c in df.columns if _is_text(df[c])]
    cols += [c for c in CATEGORICAL_EXTRA if c in df.columns and c not in cols]
    return cols


def _numeric_feature_columns(df: pd.DataFrame) -> list[str]:
    skip = {PRIMARY_KEY, TARGET, *CATEGORICAL_EXTRA}
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and c not in skip]


def _rate(s: pd.Series) -> float | None:
    return round(float(s.mean()), 4) if len(s) else None


def stats(df: pd.DataFrame) -> dict:
    y = df[TARGET]
    churn_by_category: dict[str, dict] = {}
    for col in _categorical_columns(df):
        grp = df.groupby(col, observed=True)[TARGET]
        churn_by_category[col] = {str(k): {"n": int(len(v)), "churn_rate": _rate(v)} for k, v in grp}
    numeric_cols = _numeric_feature_columns(df)
    numeric_by_churn = {
        c: {"mean_churn": _mean(df.loc[y == 1, c]), "mean_stay": _mean(df.loc[y == 0, c])}
        for c in numeric_cols
    }
    corr = {}
    for c in numeric_cols:
        if df[c].dropna().nunique() < 2 or y.nunique() < 2:
            continue  # constant column: correlation undefined
        r = df[c].corr(y)
        if pd.notna(r):
            corr[c] = round(float(r), 4)
    corr = dict(sorted(corr.items(), key=lambda kv: -abs(kv[1])))

    complain = df["Complain"] if "Complain" in df.columns else None
    tenure = df["Tenure"] if "Tenure" in df.columns else pd.Series(dtype=float)
    buckets = pd.cut(tenure, bins=TENURE_BINS, labels=TENURE_LABELS)
    tenure_buckets = {}
    for label in TENURE_LABELS:
        mask = buckets == label
        tenure_buckets[label] = {"n": int(mask.sum()), "churn_rate": _rate(y[mask])}

    return {
        "n_rows": int(len(df)),
        "n_cols": int(df.shape[1]),
        "churn_rate": _rate(y),
        "churn_count": int(y.sum()),
        "nulls": {c: int(n) for c, n in df.isna().sum().items() if n},
        "churn_by_category": churn_by_category,
        "numeric_by_churn": numeric_by_churn,
        "correlation_with_churn": corr,
        "top_drivers": list(corr)[:5],
        "complain_churn_rate": _rate(y[complain == 1]) if complain is not None else None,
        "no_complain_churn_rate": _rate(y[complain == 0]) if complain is not None else None,
        "tenure_buckets": tenure_buckets,
    }


def _mean(s: pd.Series) -> float | None:
    s = s.dropna()
    return round(float(s.mean()), 4) if len(s) else None


def write_stats(s: dict, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(s, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


# ------------------------------------------------------------------ report
def _fig_to_data_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _img(fig, caption: str) -> str:
    uri = _fig_to_data_uri(fig)
    return f'<figure><img src="{uri}" alt="{caption}"><figcaption>{caption}</figcaption></figure>'


def _fig_churn_overall(s: dict):
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar(["Stayed", "Churned"], [1 - s["churn_rate"], s["churn_rate"]], color=["#0f5c6e", "#c9560c"])
    ax.set_ylim(0, 1)
    ax.set_ylabel("share of customers")
    ax.set_title(f"Churn rate {s['churn_rate']:.1%} (n = {s['n_rows']:,})")
    return fig


def _fig_churn_by_category(s: dict):
    cats = s["churn_by_category"]
    n = len(cats)
    cols = 3
    rows = max(1, -(-n // cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3 * rows), squeeze=False)
    for ax, (col, groups) in zip(axes.flat, cats.items(), strict=False):
        labels = list(groups)
        rates = [groups[k]["churn_rate"] or 0 for k in labels]
        ax.barh(labels, rates, color="#0f5c6e")
        ax.axvline(s["churn_rate"], color="#c9560c", linestyle="--", linewidth=1)
        ax.set_xlim(0, 1)
        ax.set_title(col, fontsize=10)
    for ax in list(axes.flat)[n:]:
        ax.axis("off")
    fig.suptitle("Churn rate by category (dashed = overall)")
    fig.tight_layout()
    return fig


def _fig_numeric_by_churn(df: pd.DataFrame):
    cols = _numeric_feature_columns(df)
    ncol = 4
    rows = max(1, -(-len(cols) // ncol))
    fig, axes = plt.subplots(rows, ncol, figsize=(3.5 * ncol, 2.6 * rows), squeeze=False)
    for ax, c in zip(axes.flat, cols, strict=False):
        for label, color, val in (("stayed", "#0f5c6e", 0), ("churned", "#c9560c", 1)):
            ax.hist(df.loc[df[TARGET] == val, c].dropna(), bins=20, alpha=0.6, color=color, label=label)
        ax.set_title(c, fontsize=9)
    for ax in list(axes.flat)[len(cols):]:
        ax.axis("off")
    axes.flat[0].legend(fontsize=8)
    fig.suptitle("Numeric features by outcome")
    fig.tight_layout()
    return fig


def _fig_correlation(s: dict):
    corr = s["correlation_with_churn"]
    fig, ax = plt.subplots(figsize=(6, 0.35 * max(4, len(corr)) + 1))
    names = list(corr)[::-1]
    vals = [corr[k] for k in names]
    ax.barh(names, vals, color=["#c9560c" if v > 0 else "#0f5c6e" for v in vals])
    ax.axvline(0, color="#1b2733", linewidth=0.8)
    ax.set_title("Pearson correlation with Churn")
    return fig


def _fig_nulls(s: dict):
    nulls = s["nulls"] or {"(none)": 0}
    fig, ax = plt.subplots(figsize=(6, 0.35 * max(4, len(nulls)) + 1))
    ax.barh(list(nulls), list(nulls.values()), color="#46545f")
    ax.set_title("Missing values per column (kept, declared in the contract)")
    return fig


def render_eda_html(df: pd.DataFrame, s: dict, out_path: Path) -> Path:
    """Write a single-file HTML report (all figures embedded as base64 PNG)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    describe = df.describe().T.round(3).to_html(border=0, classes="num")
    figures = "\n".join(
        [
            _img(_fig_churn_overall(s), "Overall churn rate"),
            _img(_fig_churn_by_category(s), "Churn rate by category"),
            _img(_fig_numeric_by_churn(df), "Numeric features, stayed vs churned"),
            _img(_fig_correlation(s), "Correlation with churn"),
            _img(_fig_nulls(s), "Missing values"),
        ]
    )
    corr = s["correlation_with_churn"]
    drivers = ", ".join(f"{k} ({corr[k]:+.2f})" for k in s["top_drivers"])
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>HarborVale — EDA report</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: #1b2733;
         max-width: 64rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
  h1 {{ font-weight: 600; }}
  h2 {{ margin-top: 2rem; border-bottom: 1px solid #c9d2cd; padding-bottom: .25rem; }}
  figure {{ margin: 1rem 0; }}
  img {{ max-width: 100%; height: auto; border: 1px solid #c9d2cd; border-radius: 6px; }}
  figcaption {{ color: #46545f; font-size: .9rem; }}
  table.num {{ border-collapse: collapse; font-size: .9rem; }}
  table.num th, table.num td {{ border: 1px solid #c9d2cd; padding: .3rem .6rem; text-align: right; }}
  .kpi {{ display: inline-block; background: #e3eef1; border-radius: 8px; padding: .5rem 1rem;
         margin: .25rem .5rem .25rem 0; }}
</style>
</head>
<body>
<h1>EDA report — E-commerce Customer Churn</h1>
<p><span class="kpi">Rows: {s["n_rows"]:,}</span><span class="kpi">Columns: {s["n_cols"]}</span>
<span class="kpi">Churn rate: {s["churn_rate"]:.1%}</span>
<span class="kpi">Churned: {s["churn_count"]:,}</span></p>
<p>Top correlates of churn: {drivers or "n/a"}.</p>
<h2>Figures</h2>
{figures}
<h2>Descriptive statistics</h2>
{describe}
<p style="color:#46545f;font-size:.85rem">Generated by <code>hv.eda.render_eda_html</code>;
every number comes from <code>stats.json</code> / the cleaned frame.</p>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8", newline="\n")
    return out_path
