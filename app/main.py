"""Flask application factory. ``gunicorn app.main:app`` serves the module-level ``app``."""

from __future__ import annotations

import os
import subprocess
import time

from flask import Flask, jsonify

from hv import __version__
from hv.config import ARTIFACTS_DIR, ROOT

STARTED_AT = time.time()


def current_commit() -> str:
    """Railway exposes the deployed commit; locally fall back to git. 'unknown' when neither is available."""
    sha = os.getenv("RAILWAY_GIT_COMMIT_SHA")
    if sha:
        return sha[:12]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["COMMIT"] = current_commit()
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

    from app.routes import bp

    app.register_blueprint(bp)

    @app.get("/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "version": __version__,
                "commit": app.config["COMMIT"],
                "model_loaded": (ARTIFACTS_DIR / "crew2" / "model.joblib").exists(),
                "uptime_s": round(time.time() - STARTED_AT, 1),
            }
        )

    @app.context_processor
    def _commit():
        return {"commit": app.config["COMMIT"], "version": __version__}

    return app


app = create_app()
