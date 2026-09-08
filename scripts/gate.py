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
    url = os.getenv("LIVE_URL", "").strip().rstrip("/")
    if not url:
        raise Skip("LIVE_URL not set in .env")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url  # Railway's panel shows the bare host
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


# ---------------------------------------------------------------- M1 checks
CREW1 = ROOT / "artifacts" / "crew1"


def _crew1_clean():
    import pandas as pd

    path = CREW1 / "clean_data.csv"
    assert path.exists(), "artifacts/crew1/clean_data.csv missing"
    return pd.read_csv(path)


def _cleaning_report() -> dict:
    path = CREW1 / "cleaning_report.json"
    assert path.exists(), "artifacts/crew1/cleaning_report.json missing"
    return json.loads(path.read_text())


def check_clean_rows_match_report() -> None:
    df = _crew1_clean()
    rep = _cleaning_report()
    assert len(df) == rep["rows_out"], f"clean rows {len(df)} != report rows_out {rep['rows_out']}"
    dropped = rep["duplicate_rows_dropped"] + rep["duplicate_ids_dropped"] + rep["duplicate_records_dropped"]
    assert rep["rows_in"] - dropped == rep["rows_out"], "report arithmetic does not add up"


def check_no_unmapped_spellings() -> None:
    sys.path.insert(0, str(ROOT))
    from hv.config import ENTITY_MAP

    df = _crew1_clean()
    bad = {col: int(df[col].isin(list(m)).sum()) for col, m in ENTITY_MAP.items()}
    assert not any(bad.values()), f"unmapped spellings remain: {bad}"


def check_nulls_kept_not_imputed() -> None:
    df = _crew1_clean()
    rep = _cleaning_report()
    observed = {c: int(n) for c, n in df.isna().sum().items() if n}
    assert observed == rep["nulls_kept"], f"nulls in file {observed} != report {rep['nulls_kept']}"


def check_two_runs_identical() -> None:
    import hashlib
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        res = _run([PY, "-m", "crews.stubs", "analyst", "--out", tmp])
        assert res.returncode == 0, res.stderr.strip().splitlines()[-1] if res.stderr else "runner failed"
        for name in ("clean_data.csv", "stats.json"):
            a = hashlib.sha256((CREW1 / name).read_bytes()).hexdigest()
            b = hashlib.sha256((Path(tmp) / name).read_bytes()).hexdigest()
            assert a == b, f"{name} differs between runs"


def check_eda_outputs() -> None:
    html = CREW1 / "eda_report.html"
    stats = CREW1 / "stats.json"
    assert html.exists() and stats.exists(), "eda_report.html / stats.json missing"
    text = html.read_text(encoding="utf-8")
    assert 'src="http' not in text and 'href="http' not in text, "eda_report.html references external assets"
    rate = json.loads(stats.read_text())["churn_rate"]
    assert 0.05 <= rate <= 0.5, f"churn_rate {rate} outside the plausible range"


# ---------------------------------------------------------------- M3 checks
def check_pytest_without_key() -> None:
    env = dict(os.environ)
    env.pop("OPENAI_API_KEY", None)
    res = subprocess.run([PY, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True, env=env)
    tail = (res.stdout.strip().splitlines() or [res.stderr.strip()])[-1]
    assert res.returncode == 0, tail


def check_crew1_files_present() -> None:
    expected = ["clean_data.csv", "cleaning_report.json", "stats.json", "eda_report.html", "insights.md"]
    missing = [f for f in expected if not (CREW1 / f).exists()]
    assert not missing, f"missing in artifacts/crew1: {missing}"


def check_insights_sections_and_numbers() -> None:
    sys.path.insert(0, str(ROOT))
    from hv import insights

    text = (CREW1 / "insights.md").read_text(encoding="utf-8")
    missing = [n for n in insights.REQUIRED_SECTIONS if f"## {n}" not in text]
    assert not missing, f"insights.md lacks sections: {missing}"
    stats = json.loads((CREW1 / "stats.json").read_text())
    rep = json.loads((CREW1 / "cleaning_report.json").read_text())
    assert insights.key_numbers_match(text, stats, rep), "key-numbers table in insights.md != stats.json"


def check_real_run_recorded() -> None:
    meta_path = CREW1 / "run_meta.json"
    assert meta_path.exists(), "artifacts/crew1/run_meta.json missing (real crew run not recorded)"
    meta = json.loads(meta_path.read_text())
    assert meta["llm_calls"] > 0, "run_meta.json shows zero LLM calls (stub output committed?)"
    assert meta["cost_usd"] > 0 and meta["duration_s"] > 0, meta
    log = (ROOT / "PROJECT_LOG.md").read_text(encoding="utf-8")
    assert "M3" in log and "cost" in log.lower(), "PROJECT_LOG.md has no M3 run record"


M0: list[Check] = [
    ("pytest green", check_pytest),
    ("ruff clean", check_ruff),
    ("crewai importable in this env", check_crewai_importable),
    ("no key material in the repo", check_secret_scan),
    ("live /health serves origin/main", check_live_health),
]

M1: list[Check] = [
    ("pytest green", check_pytest),
    ("ruff clean", check_ruff),
    ("clean_data.csv row count matches the cleaning report", check_clean_rows_match_report),
    ("no Phone / CC / COD / Mobile spellings remain", check_no_unmapped_spellings),
    ("nulls kept exactly as reported (nothing imputed)", check_nulls_kept_not_imputed),
    ("two runs produce identical clean_data.csv and stats.json", check_two_runs_identical),
    ("eda_report.html self-contained, churn_rate plausible", check_eda_outputs),
]

M3: list[Check] = [
    ("pytest green with OPENAI_API_KEY unset", check_pytest_without_key),
    ("ruff clean", check_ruff),
    ("five crew-1 files in artifacts/crew1", check_crew1_files_present),
    ("insights.md: five sections, key numbers equal stats.json", check_insights_sections_and_numbers),
    ("clean_data.csv / stats.json identical to a fresh stub run", check_two_runs_identical),
    ("real crew run recorded (run_meta.json + PROJECT_LOG)", check_real_run_recorded),
]

GATES: dict[int, list[Check]] = {0: M0, 1: M1, 3: M3}


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
            print(f"[SKIP] {name} - {e}")
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {name} - {e}")
        except Exception as e:  # noqa: BLE001 - report, don't crash
            failed += 1
            print(f"[FAIL] {name} - {type(e).__name__}: {e}")
        else:
            passed += 1
            print(f"[PASS] {name}")
    total = passed + failed
    verdict = "PASS" if failed == 0 else "FAIL"
    print(f"GATE M{m}: {verdict} {passed}/{total}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
