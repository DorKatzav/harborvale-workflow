"""The pages, and the one endpoint that runs the validator live."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pandas as pd
from flask import Blueprint, Response, abort, jsonify, render_template, request, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge

from app import artifacts as A
from hv.config import ARTIFACTS_DIR, CSV_KW

try:  # READ_CSV_KW arrives with M4 (PR #15); until it merges, keep the same setting here
    from hv.config import READ_CSV_KW
except ImportError:  # pragma: no cover - removed when M4 merges
    READ_CSV_KW = {"float_precision": "round_trip"}
from hv.contract import PRESETS, load_contract, save_contract, tamper, validate

bp = Blueprint("pages", __name__)

PRESET_LABELS = {
    "unit_change": "Cashback in cents",
    "rename_column": "A column renamed",
    "drop_contract_field": "A row cut from the contract",
    "bad_category": "An old spelling returns",
    "dtype_change": "A number becomes text",
    "row_loss": "Rows lost in a filter",
}
PRESET_STORY = {
    "unit_change": "The exact fault that cost Harbor & Vale five weeks: dollars multiplied by 100.",
    "rename_column": "An upstream job renames OrderCount to order_count.",
    "drop_contract_field": "Tenure disappears from the contract while the data still has it.",
    "bad_category": "The raw CC spelling comes back into the payment column.",
    "dtype_change": "CityTier arrives as Tier 1, Tier 2, Tier 3 instead of numbers.",
    "row_loss": "A tenth of the rows never make it through.",
}


def _crews():
    return A.load_crew1(), A.load_crew2()


@bp.get("/")
def index():
    c1, c2 = _crews()
    return render_template(
        "index.html",
        c1=c1,
        c2=c2,
        run=A.load_run(),
        presets=[(p, PRESET_LABELS[p], PRESET_STORY[p]) for p in PRESETS],
        page="home",
    )


@bp.get("/analyst")
def analyst():
    c1, _ = _crews()
    return render_template("analyst.html", c1=c1, page="analyst")


@bp.get("/contract")
def contract():
    c1, _ = _crews()
    return render_template(
        "contract.html",
        c1=c1,
        rows=A.contract_rows(c1.contract),
        presets=[(p, PRESET_LABELS[p], PRESET_STORY[p]) for p in PRESETS],
        page="contract",
    )


@bp.get("/scientist")
def scientist():
    c1, c2 = _crews()
    return render_template(
        "scientist.html",
        c1=c1,
        c2=c2,
        variants=A.variant_rows(c2.metrics),
        importances=A.ranked_importances(c2.metrics),
        page="scientist",
    )


@bp.get("/runs")
def runs():
    c1, c2 = _crews()
    return render_template("runs.html", c1=c1, c2=c2, run=A.load_run(), page="runs")


@bp.get("/artifacts/<path:filename>")
def artifact_file(filename: str):
    """Serve a published artifact (the EDA report, the CSVs) from artifacts/ only."""
    return send_from_directory(ARTIFACTS_DIR, filename)


# ---------------------------------------------------------------- break it on purpose
def _report_payload(report, preset: str | None, source_label: str) -> dict:
    payload = report.to_dict()
    payload["preset"] = preset
    payload["source_label"] = source_label
    payload["failed_names"] = sorted(report.failed_names)
    return payload


def _validate_preset(preset: str) -> dict:
    """Tamper a copy of the published artifacts and validate it, exactly as scripts/break_it.py does."""
    clean = ARTIFACTS_DIR / "crew1" / "clean_data.csv"
    contract_path = ARTIFACTS_DIR / "crew1" / "dataset_contract.json"
    original = pd.read_csv(clean, **READ_CSV_KW)
    contract = load_contract(contract_path)
    tampered, tampered_contract = tamper(original, contract, preset)
    with tempfile.TemporaryDirectory(prefix=f"harborvale_{preset}_") as tmp:
        tmp_dir = Path(tmp)
        clean_copy, contract_copy = tmp_dir / "clean_data.csv", tmp_dir / "dataset_contract.json"
        if tampered.equals(original):
            shutil.copyfile(clean, clean_copy)  # data untouched: keep the original bytes and hash
        else:
            tampered.to_csv(clean_copy, **CSV_KW)
        save_contract(tampered_contract, contract_copy)
        report = validate(clean_copy, contract_copy)
    return _report_payload(report, preset, PRESET_LABELS.get(preset, preset))


def _validate_upload(storage) -> dict:
    contract = load_contract(ARTIFACTS_DIR / "crew1" / "dataset_contract.json")
    with tempfile.TemporaryDirectory(prefix="harborvale_upload_") as tmp:
        path = Path(tmp) / "clean_data.csv"
        storage.save(path)
        report = validate(path, contract)
    return _report_payload(report, None, storage.filename or "your file")


@bp.post("/api/validate")
def api_validate():
    """Run the contract validator against a deliberately broken copy, or against an uploaded CSV."""
    upload = request.files.get("clean_data")
    if upload is not None and upload.filename:
        try:
            return jsonify(_validate_upload(upload))
        except (UnicodeDecodeError, pd.errors.ParserError, ValueError) as e:
            return jsonify({"error": f"that file could not be read as the clean CSV: {e}"}), 400

    preset = (request.get_json(silent=True) or {}).get("preset") or request.form.get("preset")
    if not preset:
        return jsonify({"error": "send a preset, or upload a CSV as clean_data"}), 400
    if preset not in PRESETS:
        return jsonify({"error": f"unknown preset {preset!r}; choose one of {', '.join(PRESETS)}"}), 400
    return jsonify(_validate_preset(preset))


@bp.app_errorhandler(RequestEntityTooLarge)
def too_large(_e) -> tuple[Response, int]:
    return jsonify({"error": "that file is larger than 8 MB; the clean file is about 0.5 MB"}), 413


@bp.app_errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "no such endpoint"}), 404
    return render_template("404.html", page=""), 404


def _forbid_traversal(filename: str) -> None:  # pragma: no cover - defence in depth
    if ".." in Path(filename).parts:
        abort(404)
