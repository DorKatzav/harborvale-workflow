"""M1 runner (temporary; replaced by the analyst crew in M3): raw → clean → EDA into artifacts/crew1/.

Usage:
    python scripts/run_crew1_tools.py [--out artifacts/crew1] [--keep-duplicate-records]

Prints the CleaningReport and the headline stats so the numbers can be copied into PROJECT_LOG.md
from the program output, never typed by hand.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hv import cleaning, eda, ingest  # noqa: E402
from hv.config import ARTIFACTS_DIR, RAW_PATH  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ARTIFACTS_DIR / "crew1")
    ap.add_argument("--raw", type=Path, default=RAW_PATH)
    ap.add_argument("--keep-duplicate-records", action="store_true")
    args = ap.parse_args()

    raw = ingest.load_raw(args.raw)
    prof = ingest.profile(raw)
    df, rep = cleaning.clean(raw, drop_duplicate_records=not args.keep_duplicate_records)
    clean_sha = cleaning.write_clean(df, args.out / "clean_data.csv")
    s = eda.stats(df)
    eda.write_stats(s, args.out / "stats.json")
    eda.render_eda_html(df, s, args.out / "eda_report.html")
    (args.out / "cleaning_report.json").write_text(json.dumps(rep.to_dict(), indent=2) + "\n")

    print(f"raw: {prof['rows']} rows x {prof['cols']} cols; raw sha256 {ingest.sha256_file(args.raw)[:12]}…")
    dup = f"rows {prof['duplicate_rows']}, ids {prof['duplicate_ids']}, records {prof['duplicate_records']}"
    print(f"raw duplicates: {dup}")
    print("cleaning report:", json.dumps(rep.to_dict(), indent=2))
    print(f"clean_data.csv sha256 {clean_sha}")
    print(f"churn rate {s['churn_rate']:.4f} ({s['churn_count']} / {s['n_rows']})")
    print(f"top drivers {s['top_drivers']}")
    print(f"complain churn {s['complain_churn_rate']} vs no-complain {s['no_complain_churn_rate']}")
    print("tenure buckets:", json.dumps(s["tenure_buckets"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
