"""Stub crews for tests and CI: the same hv tools, canned prose, no LLM, no network.

Run: ``python -m crews.stubs analyst --out DIR``
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from crews.analyst.crew import AnalystResult
from crews.analyst.tools import clean_dataset, run_eda, write_insights
from hv.config import RAW_PATH


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
    res = AnalystResult(
        clean_csv=Path(cleaned["clean_csv"]),
        eda_html=Path(explored["eda_html"]),
        stats_json=Path(explored["stats_json"]),
        insights_md=Path(result),
        contract_json=None,
        llm_calls=0,
        prompt_tokens=0,
        cached_prompt_tokens=0,
        completion_tokens=0,
        cost_usd=0.0,
        duration_s=round(time.perf_counter() - t0, 1),
    )
    (out_dir / "run_meta.json").write_text(json.dumps(res.to_dict(), indent=2) + "\n", encoding="utf-8")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("crew", choices=["analyst"])
    ap.add_argument("--raw", type=Path, default=RAW_PATH)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    res = run_analyst_stub(args.raw, args.out)
    print(json.dumps(res.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
