"""Milestone gate checks — "is this milestone really done?".

Usage:
    python scripts/gate.py --m 0

Prints one line per check ([PASS] / [FAIL] reason / [SKIP] reason) and a final
"GATE M<N>: PASS k/k" (or FAIL) line. Exit code 1 on any failure. Live checks read
LIVE_URL from .env and are SKIPPED with a reason — never silently passed — when unset.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

Check = tuple[str, Callable[[], None]]


class Skip(Exception):
    """Raise inside a check to mark it skipped (with a reason)."""


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:  # pragma: no cover
        pass


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)


def _live_url() -> str:
    url = os.getenv("LIVE_URL", "").rstrip("/")
    if not url:
        raise Skip("LIVE_URL not set in .env")
    return url


def _get_json(url: str, timeout: int = 20) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as res:  # noqa: S310 - our own URL
        return json.loads(res.read().decode())


# ---------------------------------------------------------------- M0 checks
def check_pytest() -> None:
    res = _run([PY, "-m", "pytest", "-q"])
    tail = (res.stdout.strip().splitlines() or [res.stderr.strip()])[-1]
    assert res.returncode == 0, tail


def check_ruff() -> None:
    res = _run([PY, "-m", "ruff", "check", "."])
    assert res.returncode == 0, res.stdout.strip().splitlines()[-1] if res.stdout else res.stderr


def check_crewai_importable() -> None:
    res = _run([PY, "-c", "import crewai; print(crewai.__version__)"])
    assert res.returncode == 0, res.stderr.strip().splitlines()[-1] if res.stderr else "import failed"


def check_secret_scan() -> None:
    # key material only (OpenAI keys, JWT-shaped tokens); this script is excluded from its own scan
    pattern = r"sk-[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]{20,}\.eyJ"
    res = _run(["git", "grep", "-nIE", pattern, "--", ".", ":!scripts/gate.py"])
    assert res.returncode == 1, f"possible secret in repo:\n{res.stdout.strip()}"


def check_live_health() -> None:
    url = _live_url()
    body = _get_json(f"{url}/health")
    assert body.get("status") == "ok", body
    head = _run(["git", "rev-parse", "origin/main"]).stdout.strip()
    live = body.get("commit", "?")
    assert head.startswith(live), f"live commit {live} != origin/main {head[:12]}"


M0: list[Check] = [
    ("pytest green", check_pytest),
    ("ruff clean", check_ruff),
    ("crewai importable in this env", check_crewai_importable),
    ("no key material in the repo", check_secret_scan),
    ("live /health serves origin/main", check_live_health),
]

GATES: dict[int, list[Check]] = {0: M0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--m", type=int, required=True)
    m = ap.parse_args().m
    if m not in GATES:
        print(f"no gate defined for M{m}")
        return 1
    _load_dotenv()
    checks = GATES[m]
    passed = failed = 0
    for name, fn in checks:
        try:
            fn()
        except Skip as e:
            print(f"[SKIP] {name} — {e}")
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {name} — {e}")
        except Exception as e:  # noqa: BLE001 - report, don't crash
            failed += 1
            print(f"[FAIL] {name} — {type(e).__name__}: {e}")
        else:
            passed += 1
            print(f"[PASS] {name}")
    total = passed + failed
    verdict = "PASS" if failed == 0 else "FAIL"
    print(f"GATE M{m}: {verdict} {passed}/{total}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
