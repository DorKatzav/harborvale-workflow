"""Run the HarborVale Flow once: Crew 1 → contract check → Crew 2 → outputs check → publish.

    python scripts/run_flow.py                                   # real crews, publish to artifacts/
    python scripts/run_flow.py --stub-crews --publish false      # no LLM, nothing published
    python scripts/run_flow.py --skip-crew1 --tamper unit_change # break the handoff on purpose

Exit codes: 0 published (or verified with --publish false) · 2 the contract check refused the handoff ·
3 Crew 2's outputs failed their checks · 1 unexpected error. On 2 and 3 the run directory holds FAILED.md.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flow.main import EXIT_CODES, run_flow  # noqa: E402
from hv.config import RAW_PATH, RUNS_DIR  # noqa: E402
from hv.contract import PRESETS  # noqa: E402


def _bool(text: str) -> bool:
    if text.lower() in ("true", "1", "yes"):
        return True
    if text.lower() in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError(f"expected true or false, got {text!r}")


def main(argv: list[str] | None = None, run: Callable[..., object] = run_flow) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=RAW_PATH, help="the raw Excel file (Crew 1's input)")
    ap.add_argument("--tamper", choices=PRESETS, default=None, help="break the run's copy of the handoff")
    ap.add_argument("--stub-crews", action="store_true", help="the stub crews: same tools, no LLM")
    ap.add_argument("--skip-crew1", action="store_true", help="start from the published artifacts/crew1")
    ap.add_argument("--publish", type=_bool, default=True, metavar="true|false",
                    help="copy a passing run into artifacts/ (default true)")  # fmt: skip
    ap.add_argument("--run-id", default=None, help="name of the run directory (default: timestamp)")
    ap.add_argument("--runs-root", type=Path, default=RUNS_DIR, help="where run directories go")
    args = ap.parse_args(argv)

    if not args.stub_crews:
        from dotenv import load_dotenv

        load_dotenv()

    try:
        state = run(
            raw_path=args.raw,
            tamper=args.tamper,
            stub_crews=args.stub_crews,
            skip_crew1=args.skip_crew1,
            publish=args.publish,
            run_id=args.run_id,
            runs_root=args.runs_root,
            echo=True,
        )
    except Exception as e:  # noqa: BLE001 - the run already logged it; the exit code is the contract here
        print(f"\nunexpected error: {type(e).__name__}: {e}")
        return 1

    run_dir = Path(state.run_dir)
    code = EXIT_CODES.get(state.status, 1)
    print()
    print(f"status:  {state.status}")
    print(f"run dir: {run_dir}")
    print(f"llm:     {state.llm_calls} calls, ${state.cost_usd:.4f}")
    if code:
        failed = run_dir / "FAILED.md"
        print(f"see:     {failed}")
        if failed.exists():
            print()
            print(failed.read_text(encoding="utf-8"))
    return code


if __name__ == "__main__":
    sys.exit(main())
