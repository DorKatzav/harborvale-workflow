"""A live run of the Flow on the server, behind a password (PLAN.md §3.12, M7).

One `LiveRunner` per process: a single background thread, a lock, and a status the pages can poll. A server
run never publishes - it writes under `runs/` only, so the artifacts the site serves stay the ones committed
to the repository (D-M7-1). The browser follows the run by tailing the same `events.jsonl` the Flow writes,
sent as server-sent events.

gunicorn must run this with one worker (`--workers 1 --threads 4`, see Procfile): the runner's state lives
in the process, and a second worker would have its own idle runner.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from hv.config import RUNS_DIR

live_bp = Blueprint("live", __name__, url_prefix="/live")

SESSION_KEY = "live_ok"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class AlreadyRunning(RuntimeError):
    """A run is in progress; the runner takes one at a time."""


def _idle() -> dict[str, Any]:
    return {
        "status": "idle",
        "run_id": None,
        "run_dir": None,
        "started_at": None,
        "finished_at": None,
        "duration_s": None,
        "result": None,
        "error": None,
        "llm_calls": None,
        "cost_usd": None,
    }


class LiveRunner:
    """Runs `run(**kwargs)` (the Flow's `run_flow` by default) in one background thread at a time."""

    def __init__(self, run: Callable[..., Any] | None = None, runs_root: Path = RUNS_DIR) -> None:
        self._run = run
        self.runs_root = Path(runs_root)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state = _idle()

    def _resolve(self) -> Callable[..., Any]:
        if self._run is None:  # imported late: crewai is heavy and most requests never need it
            from flow.main import run_flow

            self._run = run_flow
        return self._run

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def is_running(self, run_id: str | None = None) -> bool:
        with self._lock:
            running = self._state["status"] == "running"
            return running and (run_id is None or self._state["run_id"] == run_id)

    def start(self, **kwargs) -> str:
        """Begin a run and return its id; raises AlreadyRunning while one is in progress."""
        with self._lock:
            if self._state["status"] == "running":
                raise AlreadyRunning(self._state["run_id"])
            run_id = time.strftime("%Y%m%d-%H%M%S") + "-live"
            self._state = {**_idle(), "status": "running", "run_id": run_id, "started_at": _now(),
                           "run_dir": str(self.runs_root / run_id)}  # fmt: skip
            self._thread = threading.Thread(target=self._work, args=(run_id, kwargs), daemon=True)
            self._thread.start()
        return run_id

    def _work(self, run_id: str, kwargs: dict) -> None:
        t0 = time.perf_counter()
        update: dict[str, Any]
        try:
            state = self._resolve()(run_id=run_id, runs_root=self.runs_root, publish=False, **kwargs)
            update = {
                "status": "done",
                "result": getattr(state, "status", None),
                "run_dir": getattr(state, "run_dir", None) or str(self.runs_root / run_id),
                "llm_calls": getattr(state, "llm_calls", None),
                "cost_usd": getattr(state, "cost_usd", None),
            }
        except Exception as e:  # noqa: BLE001 - the page must be able to say what went wrong
            update = {"status": "failed", "error": f"{type(e).__name__}: {e}"}
        with self._lock:
            self._state.update(update, finished_at=_now(), duration_s=round(time.perf_counter() - t0, 1))


def tail_events(
    runner: LiveRunner, run_id: str, poll_s: float = 0.5, keepalive_s: float = 15.0
) -> Iterator[str]:
    """Server-sent events from `<run>/events.jsonl`: every line as `data:`, a comment while waiting, and
    `event: end` once the run is over and the file has been read to its end."""
    path = runner.runs_root / run_id / "events.jsonl"
    offset = 0
    pending = b""
    last_sent = time.monotonic()

    def read_new() -> Iterator[str]:
        nonlocal offset, pending
        if not path.exists():
            return
        with open(path, "rb") as fh:
            fh.seek(offset)
            chunk = fh.read()
            offset = fh.tell()
        buffer = pending + chunk
        *lines, pending = buffer.split(b"\n")
        for raw in lines:
            if raw.strip():
                yield f"data: {raw.decode('utf-8')}\n\n"

    while True:
        sent = False
        for message in read_new():
            sent = True
            yield message
        if sent:
            last_sent = time.monotonic()
        if not runner.is_running(run_id):
            yield from read_new()  # whatever was written between the last read and the finish
            yield "event: end\ndata: {}\n\n"
            return
        if time.monotonic() - last_sent > keepalive_s:
            last_sent = time.monotonic()
            yield ": keepalive\n\n"
        time.sleep(poll_s)


# ---------------------------------------------------------------- password
def configured_password() -> str:
    return (os.getenv("APP_PASSWORD") or "").strip()


def secret_key() -> str:
    """Stable across restarts when APP_PASSWORD is set (one worker, one process), random otherwise."""
    explicit = os.getenv("FLASK_SECRET_KEY")
    if explicit:
        return explicit
    password = configured_password()
    if password:
        return hashlib.sha256(f"harborvale-session:{password}".encode()).hexdigest()
    return secrets.token_hex(32)


def _authenticated() -> bool:
    return bool(session.get(SESSION_KEY))


def _gate() -> Response | None:
    """None when the request may proceed; otherwise the response to send instead."""
    if not configured_password():
        return _page("disabled", 503)
    if not _authenticated():
        if request.path.endswith(("/status", "/events", "/start")):
            return jsonify({"error": "the live run needs the password; sign in at /live"}), 401
        return _page("locked", 401)
    return None


def _page(state: str, code: int = 200, **extra) -> Response:
    runner: LiveRunner = current_app.extensions["live"]
    return render_template("live.html", state=state, run=runner.snapshot(), page="live", **extra), code


# ---------------------------------------------------------------- routes
@live_bp.get("")
def live_page():
    return _gate() or _page("open")


@live_bp.post("/login")
def login():
    if not configured_password():
        return _page("disabled", 503)
    given = request.form.get("password", "")
    if not hmac.compare_digest(given.encode(), configured_password().encode()):
        time.sleep(0.5)  # a small cost per wrong guess
        return _page("locked", 401, error="That is not the password.")
    session[SESSION_KEY] = True
    return redirect(url_for("live.live_page"), code=303)


@live_bp.post("/logout")
def logout():
    session.pop(SESSION_KEY, None)
    return redirect(url_for("live.live_page"), code=303)


@live_bp.post("/start")
def start():
    if (denied := _gate()) is not None:
        return denied
    runner: LiveRunner = current_app.extensions["live"]
    try:
        run_id = runner.start(stub_crews=os.getenv("HV_STUB_CREWS", "0") == "1")
    except AlreadyRunning as e:
        return jsonify({"error": f"a run is already in progress ({e})", "run_id": str(e)}), 409
    return jsonify({"run_id": run_id, "status": "running"}), 202


@live_bp.get("/status")
def status():
    if (denied := _gate()) is not None:
        return denied
    runner: LiveRunner = current_app.extensions["live"]
    return jsonify(runner.snapshot())


@live_bp.get("/events")
def events():
    if (denied := _gate()) is not None:
        return denied
    runner: LiveRunner = current_app.extensions["live"]
    run_id = request.args.get("run_id") or runner.snapshot()["run_id"]
    if not run_id or ".." in run_id or not (runner.runs_root / run_id).is_dir():
        return jsonify({"error": "no such run"}), 404
    return Response(
        tail_events(runner, run_id),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
