"""Build `artifacts/crew1/dataset_contract.json` from the clean file (M2 task 5).

Temporary, like `scripts/run_crew1_tools.py`: in M3 the Data Steward agent calls
`hv.contract.build_contract` through a crew tool and writes the same file. Until then this keeps the
artifact reproducible - the numbers in it are measured, never typed.

    python scripts/build_contract.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hv.config import ARTIFACTS_DIR, RAW_PATH, RAW_SHEET  # noqa: E402
from hv.contract import build_contract, save_contract, validate  # noqa: E402

DEFAULT_CLEAN = ARTIFACTS_DIR / "crew1" / "clean_data.csv"
DEFAULT_OUT = ARTIFACTS_DIR / "crew1" / "dataset_contract.json"
SOURCE = f"{RAW_PATH.name} [{RAW_SHEET}] -> hv.cleaning.clean -> artifacts/crew1/clean_data.csv"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clean", type=Path, default=DEFAULT_CLEAN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    import pandas as pd

    from hv.ingest import load_data_dictionary

    if not args.clean.exists():
        print(f"missing clean file: {args.clean} - run scripts/run_crew1_tools.py first")
        return 1

    df = pd.read_csv(args.clean)
    dictionary = load_data_dictionary()
    contract = build_contract(
        df,
        source=SOURCE,
        clean_csv=args.clean,
        produced_by="scripts/build_contract.py (M2; the analyst crew takes over in M3)",
        dictionary=dictionary,
    )
    save_contract(contract, args.out)

    report = validate(args.clean, args.out)
    print(f"contract: {args.out}")
    print(f"rows {contract.dataset.row_count}, columns {len(contract.columns)}, "
          f"positive rate {contract.dataset.target_positive_rate}")
    print(f"sha256 {contract.dataset.sha256}")
    described = sum(1 for c in contract.columns if c.description)
    print(f"descriptions from the data dictionary: {described}/{len(contract.columns)}")
    print(f"validation: {'PASS' if report.passed else 'FAIL'} ({len(report.checks)} checks)")
    if not report.passed:
        print(report.to_markdown())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
