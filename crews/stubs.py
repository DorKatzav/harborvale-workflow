"""Stub crews for tests and CI: the same hv tools, canned prose, no LLM, no network.

Run: ``python -m crews.stubs analyst --out DIR`` or ``python -m crews.stubs scientist --out DIR``
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from crews.analyst.crew import AnalystResult
from crews.analyst.tools import (
    build_contract_measured,
    clean_dataset,
    run_eda,
    write_contract_human_fields,
    write_insights,
)
from crews.scientist.crew import HandoffRefused, ScientistResult
from hv.config import ARTIFACTS_DIR, PRIMARY_KEY, PROTECTED, RAW_PATH, READ_CSV_KW, TARGET
from hv.contract import Contract, load_contract, validate
from hv.features import build_features, write_features
from hv.model_card import render_evaluation_report, render_model_card
from hv.train import METRICS_FILE, MODEL_FILE, train_all


def _analyst_sections(stats: dict, report: dict) -> dict[str, str]:
    top = stats["top_drivers"]
    corr = stats["correlation_with_churn"]
    first = stats["tenure_buckets"]["0-1"]
    fixes = ", ".join(
        f"{old} → {n} rows" for col in report["entity_fixes"].values() for old, n in col.items()
    ) or "none needed"
    drivers = ", ".join(f"{k} ({corr[k]:+.2f})" for k in top[:3]) or "none measurable"
    return {
        "Overview": (
            f"The dataset holds {report['rows_out']:,} customers after cleaning "
            f"({report['rows_in']:,} raw rows); {stats['churn_rate']:.1%} of them churned "
            f"({stats['churn_count']:,} customers)."
        ),
        "Cleaning": (
            f"Spellings were unified ({fixes}); {report['duplicate_rows_dropped']} exact duplicate rows, "
            f"{report['duplicate_ids_dropped']} duplicate ids and {report['duplicate_records_dropped']} "
            f"duplicate records were removed; missing values were kept in {len(report['nulls_kept'])} "
            "columns and are declared for the modelling crew."
        ),
        "Who churns": (
            f"Customers in their first month (tenure 0-1) churn at {first['churn_rate']:.1%} "
            f"(n = {first['n']:,}); after a complaint the churn rate is "
            f"{(stats['complain_churn_rate'] or 0):.1%} versus "
            f"{(stats['no_complain_churn_rate'] or 0):.1%} without one."
        ),
        "Drivers": f"Strongest correlates of churn: {drivers}. Correlation is not causation.",
        "Recommendations": (
            "1. Contact new customers before the end of their first month. "
            "2. Resolve complaints within days and follow up. "
            "3. Watch the highest-churn categories and payment modes in the EDA report."
        ),
    }


def _rationale(col: dict) -> str:
    if col["role"] == "id":
        return "Identifies one customer; never a feature."
    if col["role"] == "target":
        return "The label the modelling crew predicts; binary 0/1, no nulls."
    if col["role"] == "protected":
        return "Protected attribute: kept for fairness reporting, never a feature."
    parts = []
    if col.get("unit"):
        parts.append(f"Unit: {col['unit']}.")
    if col.get("allowed_values") is not None:
        parts.append(f"Only the {len(col['allowed_values'])} listed spellings are valid.")
    elif col.get("min") is not None:
        parts.append(f"Observed range {col['min']:g} to {col['max']:g}; outside it is an upstream change.")
    parts.append("Nulls are declared, left for the modelling pipeline." if col["nullable"] else "Never null.")
    return " ".join(parts)


def _steward_step(clean_csv: str, out_dir: Path, raw_path: Path) -> Path:
    built = json.loads(build_contract_measured.func(clean_csv, str(out_dir), str(raw_path)))
    rationales = {c["name"]: _rationale(c) for c in built["columns"]}
    assumptions = [
        "CashbackAmount is in USD, not cents.",
        f"The row count and sha256 identify exactly this clean_data.csv ({built['row_count']} rows).",
        "Missing values are kept; imputation is the modelling crew's job, inside its pipeline.",
        "Rows identical in every column except the id were removed, keeping the lowest id (D-M1-1).",
        f"{PRIMARY_KEY} is not a feature; {TARGET} is the label; {', '.join(PROTECTED)} are not features.",
    ]
    result = write_contract_human_fields.func(
        built["contract_path"], "{}", json.dumps(rationales), json.dumps(assumptions)
    )
    if result.startswith("ERROR"):
        raise RuntimeError(result)
    return Path(result)


def run_analyst_stub(raw_path: Path = RAW_PATH, out_dir: Path | None = None) -> AnalystResult:
    out_dir = Path(out_dir or Path("runs") / time.strftime("%Y%m%d-%H%M%S") / "crew1")
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    cleaned = json.loads(clean_dataset.func(str(raw_path), str(out_dir)))
    explored = json.loads(run_eda.func(cleaned["clean_csv"], str(out_dir)))
    sections = _analyst_sections(explored["stats"], cleaned["report"])
    result = write_insights.func(str(out_dir), json.dumps(sections))
    if result.startswith("ERROR"):
        raise RuntimeError(result)
    contract_path = _steward_step(cleaned["clean_csv"], out_dir, Path(raw_path))
    res = AnalystResult(
        clean_csv=Path(cleaned["clean_csv"]),
        eda_html=Path(explored["eda_html"]),
        stats_json=Path(explored["stats_json"]),
        insights_md=Path(result),
        contract_json=contract_path,
        llm_calls=0,
        prompt_tokens=0,
        cached_prompt_tokens=0,
        completion_tokens=0,
        cost_usd=0.0,
        duration_s=round(time.perf_counter() - t0, 1),
    )
    (out_dir / "run_meta.json").write_text(
        json.dumps(res.to_dict(), indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return res


def _evaluation_narrative(metrics: dict) -> dict[str, str]:
    """The reading the ML Engineer writes under the generated tables; the numbers stay generated."""
    served = metrics["variants"][metrics["served"]]
    base = metrics["baseline"]
    ranked = sorted(metrics.get("importances", {}).items(), key=lambda kv: kv[1], reverse=True)
    top = ", ".join(name for name, _ in ranked[:3]) or "no feature measurably"
    return {
        "Reading": (
            f"{metrics['served']} is served: ROC-AUC {served['roc_auc']['mean']:.4f} against the "
            f"{base['strategy']} baseline's {base['roc_auc']:.4f}, and precision@top10 "
            f"{served['precision_at_top10']:.4f} against {base['precision_at_top10']:.4f}. Ranking the "
            "riskiest tenth of the book is the decision this model is actually used for, so that second "
            f"number matters more than the first. It leans mostly on {top}."
        )
    }


def _scientist_sections(metrics: dict, contract: Contract) -> dict[str, str]:
    """The five model-card sections, stated from this run's own numbers rather than typed."""
    served = metrics["variants"][metrics["served"]]
    base = metrics["baseline"]
    f = metrics["features"]
    nullable = [col for col in contract.columns if col.nullable]
    gaps = []
    for attribute, groups in (metrics.get("fairness") or {}).items():
        recalls = {g: s["recall"] for g, s in groups.items()}
        if len(recalls) > 1:
            low, high = min(recalls, key=recalls.get), max(recalls, key=recalls.get)
            gaps.append(f"{attribute}: {high} {recalls[high]:.4f} vs {low} {recalls[low]:.4f} recall")
    gap_text = "; ".join(gaps) or "not measurable in this run"
    return {
        "Purpose": (
            f"Rank the {contract.dataset.row_count:,} customers in the clean file by their probability of "
            "churning, so retention spends its week on the riskiest names instead of on everybody. The "
            "score is a priority list, not a verdict about a person."
        ),
        "Training data": (
            "Exactly the file the contract describes, nothing else: Crew 2 never sees the raw workbook or "
            f"Crew 1's internals. {len(f['numeric'])} numeric and {len(f['categorical'])} categorical "
            f"columns go in, plus {len(f['engineered'])} engineered from them; {PRIMARY_KEY} (identifier), "
            f"{TARGET} (the label) and {', '.join(PROTECTED)} (protected) are never model inputs."
        ),
        "Metrics": (
            f"Five stratified folds. Served {metrics['served']} at ROC-AUC "
            f"{served['roc_auc']['mean']:.4f} (+/-{served['roc_auc']['std']:.4f}) against a "
            f"{base['strategy']} baseline at {base['roc_auc']:.4f}; precision@top10 "
            f"{served['precision_at_top10']:.4f} against {base['precision_at_top10']:.4f}. A variant that "
            "did not beat the baseline on both would not be published - the Flow refuses to publish it."
        ),
        "Limitations": (
            f"Cross-validation on one historical snapshot of {metrics['n_rows']:,} rows, with no time-based "
            "split, so this measures ranking on customers like these, not next quarter's. Nulls in "
            f"{len(nullable)} columns are imputed inside the pipeline rather than collected properly "
            "upstream. Permutation importance says what the model used, not what causes churn."
        ),
        "Ethical considerations": (
            f"{' and '.join(PROTECTED)} are excluded from the inputs, which does not by itself make the "
            "score even-handed - correlated columns can carry the same information - so recall is measured "
            f"per group and reported here anyway ({gap_text}). Use the score to offer help, not to withdraw "
            "it: a customer flagged as likely to leave should get a call, never worse terms."
        ),
    }


def run_scientist_stub(
    contract_json: Path, clean_csv: Path, out_dir: Path | None = None
) -> ScientistResult:
    """Crew 2 without the agents: check the handoff, then the same hv calls the real tools will make.

    This is what runs under --stub-crews, in CI, and in the app when HV_STUB_CREWS=1. It asks the
    contract question before it trains anything and raises HandoffRefused without writing a model,
    which is the behaviour the brief is about. When crews/scientist/tools.py lands (M5 task 1) these
    calls move behind those sandboxed tools, the way run_analyst_stub already goes through Crew 1's.
    """
    import pandas as pd

    out_dir = Path(out_dir or Path("runs") / time.strftime("%Y%m%d-%H%M%S") / "crew2")
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    contract = load_contract(contract_json)
    report = validate(clean_csv, contract)
    if not report.passed:
        raise HandoffRefused(
            f"{clean_csv} disagrees with its contract "
            f"({', '.join(sorted(report.failed_names))}); nothing was trained"
        )

    df = pd.read_csv(clean_csv, **READ_CSV_KW)
    features = build_features(df, contract)
    features_csv = out_dir / "features.csv"
    write_features(features, features_csv)

    protected = df[[PRIMARY_KEY, *[c for c in PROTECTED if c in df.columns]]]
    metrics = train_all(features, contract, out_dir, protected=protected)

    evaluation_md = out_dir / "evaluation_report.md"
    evaluation_md.write_text(
        render_evaluation_report(metrics, _evaluation_narrative(metrics)), encoding="utf-8", newline="\n"
    )
    model_card_md = out_dir / "model_card.md"
    model_card_md.write_text(
        render_model_card(metrics, contract, _scientist_sections(metrics, contract)),
        encoding="utf-8",
        newline="\n",
    )

    res = ScientistResult(
        features_csv=features_csv,
        metrics_json=out_dir / METRICS_FILE,
        model_path=out_dir / MODEL_FILE,
        evaluation_md=evaluation_md,
        model_card_md=model_card_md,
        llm_calls=0,
        prompt_tokens=0,
        cached_prompt_tokens=0,
        completion_tokens=0,
        cost_usd=0.0,
        duration_s=round(time.perf_counter() - t0, 1),
    )
    (out_dir / "run_meta.json").write_text(
        json.dumps(res.to_dict(), indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("crew", choices=["analyst", "scientist"])
    ap.add_argument("--raw", type=Path, default=RAW_PATH)
    ap.add_argument("--contract", type=Path, default=ARTIFACTS_DIR / "crew1" / "dataset_contract.json")
    ap.add_argument("--clean", type=Path, default=ARTIFACTS_DIR / "crew1" / "clean_data.csv")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if args.crew == "analyst":
        res = run_analyst_stub(args.raw, args.out)
    else:
        try:
            res = run_scientist_stub(args.contract, args.clean, args.out)
        except HandoffRefused as e:
            print(f"refused: {e}")
            return 2
    print(json.dumps(res.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
