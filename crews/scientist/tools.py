"""Scientist-crew tools: thin CrewAI wrappers over hv/, behind a sandbox (PLAN.md §3.10).

The brief's rule is that Crew 2 may read `dataset_contract.json` and `clean_data.csv` and nothing
else. An instruction in a prompt cannot enforce that - an agent that decides to look at the raw
workbook would simply look at it - so every tool that reads resolves its path first and raises
`SandboxError` when the result falls outside the Crew-1 directory it was handed. The refusal happens
on the path, before any file is opened, so a smuggled path fails whether the file exists or not.

Like the analyst's tools these take and return str paths and JSON strings, and they write only into
the `out_dir` they are given - never into `artifacts/`, which only the Flow may touch.
"""

from __future__ import annotations

import json
from pathlib import Path

from crewai.tools import tool

from crews.sandbox import SandboxError, guard, guard_write
from hv.config import PRIMARY_KEY, PROTECTED, READ_CSV_KW
from hv.contract import load_contract, validate
from hv.features import build_features, write_features
from hv.model_card import render_evaluation_report, render_model_card
from hv.train import METRICS_FILE, MODEL_FILE, train_all

__all__ = ["SandboxError", "set_crew1_dir", "set_run_dir"]

_CREW1_DIR: Path | None = None
_RUN_DIR: Path | None = None


def set_crew1_dir(path: Path | str) -> Path:
    """Point the sandbox at this run's Crew-1 directory (reads). The crew calls this before kickoff."""
    global _CREW1_DIR
    _CREW1_DIR = Path(path).resolve()
    return _CREW1_DIR


def set_run_dir(path: Path | str) -> Path:
    """Point the sandbox at the directory this crew may write into (M8 audit, A1)."""
    global _RUN_DIR
    _RUN_DIR = Path(path).resolve()
    return _RUN_DIR


def _crew1_dir() -> Path:
    if _CREW1_DIR is None:
        raise SandboxError("the sandbox has no Crew-1 directory yet; call set_crew1_dir() first")
    return _CREW1_DIR


def _guard(path: str | Path, allowed_dir: Path | str) -> Path:
    return guard(path, allowed_dir)


def _out(out_dir: str) -> Path:
    """The only place a tool may write: inside the run directory, never the Crew-1 handoff."""
    out = guard_write(out_dir, _RUN_DIR, _CREW1_DIR)
    out.mkdir(parents=True, exist_ok=True)
    return out


@tool("read_crew1_artifact")
def read_crew1_artifact(path: str) -> str:
    """Read one file from Crew 1's handoff directory as text. Only paths inside that directory are
    allowed: the raw workbook, other runs and anywhere else on the machine are refused."""
    return _guard(path, _crew1_dir()).read_text(encoding="utf-8")


@tool("validate_against_contract")
def validate_against_contract(clean_csv: str, contract_json: str) -> str:
    """Check the clean CSV against the dataset contract before anything is trained on it. Returns the
    ValidationReport as JSON; `passed` false means the handoff is broken and training must not start."""
    crew1 = _crew1_dir()
    report = validate(_guard(clean_csv, crew1), load_contract(_guard(contract_json, crew1)))
    return json.dumps(report.to_dict())


@tool("engineer_features")
def engineer_features(clean_csv: str, contract_json: str, out_dir: str) -> str:
    """Build the model inputs the contract declares plus the four engineered columns, and write
    <out_dir>/features.csv. Identifier, target and protected columns are never inputs.
    Returns JSON {"features_csv", "sha256", "rows", "columns"}."""
    import pandas as pd

    crew1 = _crew1_dir()
    contract = load_contract(_guard(contract_json, crew1))
    df = pd.read_csv(_guard(clean_csv, crew1), **READ_CSV_KW)
    features = build_features(df, contract)
    out = _out(out_dir)
    sha = write_features(features, out / "features.csv")
    return json.dumps(
        {
            "features_csv": str(out / "features.csv"),
            "sha256": sha,
            "rows": int(features.shape[0]),
            "columns": int(features.shape[1]),
        }
    )


@tool("train_and_evaluate")
def train_and_evaluate(features_csv: str, contract_json: str, out_dir: str) -> str:
    """Cross-validate the model variants, keep the best by ROC-AUC, and write <out_dir>/metrics.json
    and <out_dir>/model.joblib. The protected columns are read from the clean file for the fairness
    table only, never as inputs. Returns metrics.json as JSON."""
    import pandas as pd

    crew1 = _crew1_dir()
    out = _out(out_dir)
    contract = load_contract(_guard(contract_json, crew1))
    features = pd.read_csv(_guard(features_csv, out), **READ_CSV_KW)
    clean = pd.read_csv(_guard(crew1 / "clean_data.csv", crew1), **READ_CSV_KW)
    protected = clean[[PRIMARY_KEY, *[c for c in PROTECTED if c in clean.columns]]]
    metrics = train_all(features, contract, out, protected=protected)
    return json.dumps(metrics)


@tool("write_evaluation_report")
def write_evaluation_report(out_dir: str, narrative_json: str) -> str:
    """Render <out_dir>/evaluation_report.md: the generated comparison tables, then your reading of
    them. narrative_json is {"<heading>": "<prose>"}. Every number in the tables comes from
    metrics.json, so prose cannot change them. Returns the path."""
    out = _out(out_dir)
    metrics = json.loads((_guard(out / METRICS_FILE, out)).read_text(encoding="utf-8"))
    path = out / "evaluation_report.md"
    path.write_text(
        render_evaluation_report(metrics, json.loads(narrative_json)), encoding="utf-8", newline="\n"
    )
    return str(path)


@tool("write_model_card")
def write_model_card(out_dir: str, sections_json: str) -> str:
    """Render <out_dir>/model_card.md. sections_json must hold all five required sections - Purpose,
    Training data, Metrics, Limitations, Ethical considerations - or this returns an ERROR string and
    writes nothing. Returns the path."""
    out = _out(out_dir)
    crew1 = _crew1_dir()
    metrics = json.loads((_guard(out / METRICS_FILE, out)).read_text(encoding="utf-8"))
    contract = load_contract(_guard(crew1 / "dataset_contract.json", crew1))
    try:
        rendered = render_model_card(metrics, contract, json.loads(sections_json))
    except ValueError as e:
        return f"ERROR: {e}"
    path = out / "model_card.md"
    path.write_text(rendered, encoding="utf-8", newline="\n")
    return str(path)


EXPECTED_FILES = ["features.csv", METRICS_FILE, MODEL_FILE, "evaluation_report.md", "model_card.md"]
