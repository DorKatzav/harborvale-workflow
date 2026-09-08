"""Analyst-crew tools: thin CrewAI wrappers over hv/. Paths in, JSON out, files on disk (PLAN.md §3.10).

Tools return "ERROR: ..." strings instead of raising so the agent can read the problem and call again.
"""

from __future__ import annotations

import json
from pathlib import Path

from crewai.tools import tool

from hv import cleaning, eda, ingest, insights
from hv import contract as hvc
from hv.config import RAW_SHEET


@tool("profile_raw_data")
def profile_raw_data(raw_path: str) -> str:
    """Profile the raw workbook: rows, columns, dtypes, null counts, unique values with samples,
    duplicate rows, duplicate ids, duplicate records (identical except CustomerID), numeric ranges.
    Returns JSON."""
    df = ingest.load_raw(Path(raw_path))
    return json.dumps(ingest.profile(df))


@tool("clean_dataset")
def clean_dataset(raw_path: str, out_dir: str) -> str:
    """Clean the raw workbook deterministically (strip whitespace, unify spellings, drop duplicate
    rows / ids / records, cast integer columns, keep missing values) and write <out_dir>/clean_data.csv
    and <out_dir>/cleaning_report.json. Returns JSON {"clean_csv", "sha256", "report"}."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    df = ingest.load_raw(Path(raw_path))
    clean_df, rep = cleaning.clean(df)
    sha = cleaning.write_clean(clean_df, out / "clean_data.csv")
    (out / "cleaning_report.json").write_text(
        json.dumps(rep.to_dict(), indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return json.dumps({"clean_csv": str(out / "clean_data.csv"), "sha256": sha, "report": rep.to_dict()})


@tool("run_eda")
def run_eda(clean_csv: str, out_dir: str) -> str:
    """Compute descriptive statistics on the clean CSV (churn by category, numeric means by outcome,
    correlations with churn, tenure buckets, complaint effect) and write <out_dir>/stats.json and a
    self-contained <out_dir>/eda_report.html with charts. Returns JSON {"stats", "stats_json", "eda_html"}."""
    import pandas as pd

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(clean_csv)
    s = eda.stats(df)
    eda.write_stats(s, out / "stats.json")
    eda.render_eda_html(df, s, out / "eda_report.html")
    return json.dumps(
        {"stats": s, "stats_json": str(out / "stats.json"), "eda_html": str(out / "eda_report.html")}
    )


@tool("write_insights")
def write_insights(out_dir: str, sections_json: str) -> str:
    """Render <out_dir>/insights.md. The key-numbers table is generated from stats.json and
    cleaning_report.json; you supply the prose. sections_json must be a JSON object with exactly these
    keys, each a non-empty Markdown string: "Overview", "Cleaning", "Who churns", "Drivers",
    "Recommendations". Returns the file path, or "ERROR: ..." describing what to fix."""
    out = Path(out_dir)
    try:
        sections = json.loads(sections_json)
        if not isinstance(sections, dict):
            return "ERROR: sections_json must be a JSON object mapping section name to text"
        stats = json.loads((out / "stats.json").read_text(encoding="utf-8"))
        report = json.loads((out / "cleaning_report.json").read_text(encoding="utf-8"))
        md = insights.render_insights(stats, report, sections)
    except FileNotFoundError as e:
        return f"ERROR: run clean_dataset and run_eda first ({e.filename} missing)"
    except (ValueError, json.JSONDecodeError) as e:
        return f"ERROR: {e}"
    path = out / "insights.md"
    path.write_text(md, encoding="utf-8", newline="\n")
    return str(path)


# ---------------------------------------------------------------- the Data Steward's tools (M3b)
META_FIELDS = {"created_at", "produced_by", "source", "contract_version"}


def measured_fields(c: hvc.Contract) -> dict:
    """The part of a contract the validator reads: dataset facts + per-column measured fields.

    Excludes the human fields (description, rationale, assumptions) and run metadata (created_at,
    produced_by, source). Two contracts built from the same clean file must agree on this view.
    """
    cols = []
    for col in c.columns:
        d = col.model_dump(mode="json")
        cols.append({k: v for k, v in d.items() if k not in hvc.HUMAN_FIELDS})
    return {"dataset": c.dataset.model_dump(mode="json"), "columns": cols}


@tool("build_contract_measured")
def build_contract_measured(clean_csv: str, out_dir: str, raw_path: str) -> str:
    """Measure the clean CSV and write <out_dir>/dataset_contract.json with every measured field
    (dtype, role, unit, nullable, null_count, allowed_values, min, max, row_count, positive rate, sha256).
    Descriptions are pre-filled from the raw workbook's data dictionary; rationale and assumptions are
    empty until write_contract_human_fields. Returns JSON {"contract_path", "row_count", "sha256",
    "columns": [{name, dtype, role, unit, nullable, null_count, allowed_values, min, max, description}]}."""
    import pandas as pd

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(clean_csv)
    dictionary = ingest.load_data_dictionary(Path(raw_path)) if Path(raw_path).exists() else {}
    source = f"{Path(raw_path).name} [{RAW_SHEET}] -> hv.cleaning.clean -> {Path(clean_csv).name}"
    c = hvc.build_contract(df, source=source, clean_csv=Path(clean_csv), dictionary=dictionary)
    path = out / "dataset_contract.json"
    hvc.save_contract(c, path)
    cols = [{k: v for k, v in col.model_dump(mode="json").items() if k != "rationale"} for col in c.columns]
    return json.dumps(
        {
            "contract_path": str(path),
            "row_count": c.dataset.row_count,
            "sha256": c.dataset.sha256,
            "columns": cols,
        }
    )


@tool("write_contract_human_fields")
def write_contract_human_fields(
    contract_path: str, descriptions_json: str, rationales_json: str, assumptions_json: str
) -> str:
    """Add the human part of the contract: descriptions_json = {column: one-line description},
    rationales_json = {column: why this constraint exists / what the modelling crew may assume},
    assumptions_json = ["assumption", ...]. Only these fields change; measured fields are facts and
    cannot be edited here. Column names must exist in the contract. Returns the contract path, or
    "ERROR: ..." describing what to fix."""
    try:
        descriptions = json.loads(descriptions_json or "{}")
        rationales = json.loads(rationales_json or "{}")
        assumptions = json.loads(assumptions_json or "[]")
        if not isinstance(descriptions, dict) or not isinstance(rationales, dict):
            return "ERROR: descriptions_json and rationales_json must be JSON objects {column: text}"
        if not isinstance(assumptions, list):
            return "ERROR: assumptions_json must be a JSON list of strings"
        c = hvc.load_contract(contract_path)
        c = hvc.apply_human_fields(
            c,
            descriptions={k: str(v) for k, v in descriptions.items()},
            rationales={k: str(v) for k, v in rationales.items()},
            assumptions=[str(a) for a in assumptions],
        )
    except FileNotFoundError:
        return f"ERROR: contract not found at {contract_path}; call build_contract_measured first"
    except KeyError as e:
        return f"ERROR: {e.args[0]}"
    except (ValueError, json.JSONDecodeError) as e:
        return f"ERROR: invalid JSON: {e}"
    hvc.save_contract(c, Path(contract_path))
    return str(contract_path)


ANALYST_TOOLS = [
    profile_raw_data,
    clean_dataset,
    run_eda,
    write_insights,
    build_contract_measured,
    write_contract_human_fields,
]
