"""Run Crew 2's tools over Crew 1's published artifacts (M4 task 5).

Temporary, like `run_crew1_tools.py` was: in M5 the three scientist agents call these same `hv`
functions through crew tools and the Flow orchestrates them. Until then this is how the real
artifacts get produced, deterministically and without an API key.

The first thing it does is validate the clean file against the contract. If they disagree, it stops
with exit code 2 and trains nothing - which is the entire point of the project.

    python scripts/run_crew2_tools.py [--out artifacts/crew2]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hv.config import ARTIFACTS_DIR, PRIMARY_KEY, PROTECTED, READ_CSV_KW  # noqa: E402
from hv.contract import load_contract, validate  # noqa: E402
from hv.features import build_features, write_features  # noqa: E402
from hv.model_card import REQUIRED_SECTIONS, render_evaluation_report, render_model_card  # noqa: E402
from hv.train import train_all  # noqa: E402

CREW1 = ARTIFACTS_DIR / "crew1"
CLEAN_CSV = CREW1 / "clean_data.csv"
CONTRACT_JSON = CREW1 / "dataset_contract.json"

# Placeholder prose. In M5 the Model Governance Officer writes these sections; the renderers refuse
# to produce a document without them, so the runner has to supply something in the meantime.
PLACEHOLDER = "_Written by scripts/run_crew2_tools.py; the Model Governance Officer replaces this in M5._"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clean", type=Path, default=CLEAN_CSV)
    ap.add_argument("--contract", type=Path, default=CONTRACT_JSON)
    ap.add_argument("--out", type=Path, default=ARTIFACTS_DIR / "crew2")
    args = ap.parse_args()

    import pandas as pd

    for path, what in ((args.clean, "clean CSV"), (args.contract, "contract")):
        if not path.exists():
            print(f"missing {what}: {path} - run Crew 1 first")
            return 1

    started = time.perf_counter()
    contract = load_contract(args.contract)

    report = validate(args.clean, contract)
    print(f"contract check: {'PASS' if report.passed else 'FAIL'} ({len(report.checks)} checks)")
    if not report.passed:
        print(report.to_markdown())
        print("refusing to train on data that disagrees with its contract")
        return 2

    df = pd.read_csv(args.clean, **READ_CSV_KW)
    features = build_features(df, contract)
    args.out.mkdir(parents=True, exist_ok=True)
    features_sha = write_features(features, args.out / "features.csv")
    print(f"features: {features.shape[0]} rows x {features.shape[1]} columns, sha256 {features_sha[:12]}")

    protected = df[[PRIMARY_KEY, *[c for c in PROTECTED if c in df.columns]]]
    metrics = train_all(features, contract, args.out, protected=protected)

    served = metrics["variants"][metrics["served"]]
    print(f"baseline roc_auc {metrics['baseline']['roc_auc']}, "
          f"precision@top10 {metrics['baseline']['precision_at_top10']}")
    for name, scores in metrics["variants"].items():
        mark = " <- served" if name == metrics["served"] else ""
        print(f"  {name:14s} roc_auc {scores['roc_auc']['mean']:.4f} +/- {scores['roc_auc']['std']:.4f}"
              f"  precision@top10 {scores['precision_at_top10']:.4f}{mark}")

    (args.out / "evaluation_report.md").write_text(
        render_evaluation_report(metrics, {"Reading": PLACEHOLDER}), encoding="utf-8", newline="\n"
    )
    (args.out / "model_card.md").write_text(
        render_model_card(metrics, contract, dict.fromkeys(REQUIRED_SECTIONS, PLACEHOLDER)),
        encoding="utf-8",
        newline="\n",
    )

    elapsed = round(time.perf_counter() - started, 1)
    (args.out / "run_meta.json").write_text(
        json.dumps(
            {
                "trained_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                "seconds": elapsed,
                "produced_by": "scripts/run_crew2_tools.py (M4; the scientist crew takes over in M5)",
                "clean_sha256": contract.dataset.sha256,
                "features_sha256": features_sha,
                "served": metrics["served"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"served: {metrics['served']} | roc_auc {served['roc_auc']['mean']:.4f} | {elapsed}s")
    print(f"five files in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
