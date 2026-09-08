"""Break the Crew 1 -> Crew 2 handoff on purpose and watch the validator refuse it.

Usage:
    python scripts/break_it.py --preset unit_change
    python scripts/break_it.py --preset row_loss --clean path/to/clean_data.csv \
        --contract path/to/dataset_contract.json

The original artifacts are never touched: the tampered copy is written to a temp directory and
validated from there, by path, so the run is the same one the Flow does. Exit code 2 means the
validator caught the break - that is the good outcome. Exit 0 means it did not.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hv.config import ARTIFACTS_DIR, CSV_KW  # noqa: E402
from hv.contract import PRESETS, load_contract, save_contract, tamper, validate  # noqa: E402

DEFAULT_CLEAN = ARTIFACTS_DIR / "crew1" / "clean_data.csv"
DEFAULT_CONTRACT = ARTIFACTS_DIR / "crew1" / "dataset_contract.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preset", required=True, choices=PRESETS, help="which break to apply")
    ap.add_argument("--clean", type=Path, default=DEFAULT_CLEAN, help="clean CSV written by Crew 1")
    ap.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT, help="contract written by Crew 1")
    ap.add_argument(
        "--out", type=Path, default=None, help="where to write the tampered copy (default: temp dir)"
    )
    args = ap.parse_args()

    import pandas as pd

    for path, what in ((args.clean, "clean CSV"), (args.contract, "contract")):
        if not path.exists():
            print(f"missing {what}: {path}")
            print("run Crew 1 first (M1) or pass --clean / --contract explicitly")
            return 1

    original = pd.read_csv(args.clean)
    contract = load_contract(args.contract)
    tampered, tampered_contract = tamper(original, contract, args.preset)

    out_dir = args.out or Path(tempfile.mkdtemp(prefix=f"harborvale_{args.preset}_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    clean_copy, contract_copy = out_dir / args.clean.name, out_dir / args.contract.name
    if tampered.equals(original):
        shutil.copyfile(args.clean, clean_copy)  # data untouched: keep the original bytes and hash
    else:
        tampered.to_csv(clean_copy, **CSV_KW)
    save_contract(tampered_contract, contract_copy)

    print(f"preset:   {args.preset}")
    print(f"tampered: {clean_copy}")
    print(f"contract: {contract_copy}")
    print()
    report = validate(clean_copy, contract_copy)
    print(report.to_markdown())

    if report.passed:
        print(f"WARNING: the {args.preset} break slipped through the validator - nothing failed.")
        return 0
    print(f"caught by: {', '.join(sorted(report.failed_names))}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
