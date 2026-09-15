"""M7: a live run behind a password - one runner, one run at a time, events streamed from the run's log.

The Flow itself is replaced by a fake here (it writes real events.jsonl lines through RunLogger and blocks on
an Event so the tests can look at a run while it is "running"); the real thing is exercised by gate M7 on
the deployed site.
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from app import live as L
from flow.state import FlowState
from hv.runlog import RunLogger, new_run_dir

PASSWORD = "quay-gate-42"


def _fake_run(gate: threading.Event, status: str = "verified", boom: bool = False):
    """A stand-in for flow.main.run_flow with the same keyword interface."""

    def run(**kw):
        run_dir = new_run_dir(kw["runs_root"], kw["run_id"])
        log = RunLogger(run_dir)
        log.event("flow", "start", run_id=kw["run_id"], stub_crews=kw.get("stub_crews"))
        log.event("ingest", "ok", duration_s=0.0)
        gate.wait(timeout=10)
        if boom:
            log.event("flow", "fail", error="RuntimeError: provider down")
            raise RuntimeError("provider down")
        log.event("flow", "ok", result=status)
        return FlowState(run_id=kw["run_id"], run_dir=str(run_dir), status=status, publish=False)

    return run


def _wait(pred, seconds: float = 5.0) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


# ---------------------------------------------------------------- the runner
def test_runner_starts_idle_and_reports_a_finished_run(tmp_path):
    gate = threading.Event()
    runner = L.LiveRunner(run=_fake_run(gate), runs_root=tmp_path)
    assert runner.snapshot()["status"] == "idle"

    run_id = runner.start(stub_crews=True)
    assert runner.snapshot()["status"] == "running" and runner.snapshot()["run_id"] == run_id
    gate.set()
    assert _wait(lambda: runner.snapshot()["status"] == "done")
    snap = runner.snapshot()
    assert snap["result"] == "verified" and snap["finished_at"] and snap["duration_s"] >= 0
    assert (tmp_path / run_id / "events.jsonl").exists()


def test_runner_refuses_a_second_start_while_running(tmp_path):
    gate = threading.Event()
    runner = L.LiveRunner(run=_fake_run(gate), runs_root=tmp_path)
    runner.start(stub_crews=True)
    with pytest.raises(L.AlreadyRunning):
        runner.start(stub_crews=True)
    gate.set()
    assert _wait(lambda: runner.snapshot()["status"] == "done")
    assert runner.start(stub_crews=True)  # free again once the run is over
    gate.set()


def test_runner_records_a_crash_as_failed_with_the_error(tmp_path):
    gate = threading.Event()
    gate.set()
    runner = L.LiveRunner(run=_fake_run(gate, boom=True), runs_root=tmp_path)
    runner.start(stub_crews=True)
    assert _wait(lambda: runner.snapshot()["status"] == "failed")
    assert "provider down" in runner.snapshot()["error"]


def test_runner_never_publishes_to_artifacts(tmp_path):
    seen = {}
    gate = threading.Event()
    gate.set()
    inner = _fake_run(gate)

    def run(**kw):
        seen.update(kw)
        return inner(**kw)

    runner = L.LiveRunner(run=run, runs_root=tmp_path)
    runner.start(stub_crews=True)
    assert _wait(lambda: runner.snapshot()["status"] == "done")
    assert seen["publish"] is False and seen["stub_crews"] is True


def test_events_tail_replays_the_file_and_stops_when_the_run_is_over(tmp_path):
    gate = threading.Event()
    runner = L.LiveRunner(run=_fake_run(gate), runs_root=tmp_path)
    run_id = runner.start(stub_crews=True)
    assert _wait(lambda: (tmp_path / run_id / "events.jsonl").exists())
    chunks: list[str] = []

    def consume():
        chunks.extend(L.tail_events(runner, run_id, poll_s=0.02, keepalive_s=0.1))

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    time.sleep(0.3)
    gate.set()
    t.join(timeout=5)
    assert not t.is_alive(), "the stream did not end after the run finished"
    data = [json.loads(c[len("data: "):].strip()) for c in chunks if c.startswith("data: ")]
    assert [(e["step"], e["status"]) for e in data] == [("flow", "start"), ("ingest", "ok"), ("flow", "ok")]
    assert any(c.startswith(":") for c in chunks), "no keepalive comment while waiting"
    assert chunks[-1].startswith("event: end")


# ---------------------------------------------------------------- the routes
@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", PASSWORD)
    monkeypatch.setenv("HV_STUB_CREWS", "1")
    from app.main import create_app

    application = create_app()
    application.config["TESTING"] = True
    gate = threading.Event()
    application.extensions["live"] = L.LiveRunner(run=_fake_run(gate), runs_root=tmp_path)
    application.extensions["live_gate"] = gate  # so a test can finish the fake run
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, password: str = PASSWORD):
    return client.post("/live/login", data={"password": password})


def test_live_page_is_401_without_the_password(client):
    res = client.get("/live")
    assert res.status_code == 401
    assert b"password" in res.data.lower()


def test_live_is_503_when_no_password_is_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    from app.main import create_app

    res = create_app().test_client().get("/live")
    assert res.status_code == 503
    assert b"not enabled" in res.data.lower()


def test_wrong_password_is_401_and_right_password_opens_the_page(client):
    assert _login(client, "nope").status_code == 401
    res = _login(client)
    assert res.status_code in (302, 303) and res.headers["Location"].endswith("/live")
    page = client.get("/live")
    assert page.status_code == 200 and b"Start" in page.data


def test_start_needs_the_password_and_answers_202_then_409(client, app):
    assert client.post("/live/start").status_code == 401
    _login(client)
    first = client.post("/live/start")
    assert first.status_code == 202
    run_id = first.get_json()["run_id"]
    assert client.post("/live/start").status_code == 409
    status = client.get("/live/status").get_json()
    assert status["status"] == "running" and status["run_id"] == run_id
    app.extensions["live_gate"].set()
    assert _wait(lambda: client.get("/live/status").get_json()["status"] == "done")
    assert client.get("/live/status").get_json()["result"] == "verified"


def test_status_and_events_need_the_password_too(client):
    assert client.get("/live/status").status_code == 401
    assert client.get("/live/events").status_code == 401


def test_events_endpoint_streams_the_run(client, app):
    _login(client)
    run_id = client.post("/live/start").get_json()["run_id"]
    app.extensions["live_gate"].set()
    assert _wait(lambda: client.get("/live/status").get_json()["status"] == "done")
    res = client.get(f"/live/events?run_id={run_id}")
    assert res.status_code == 200 and res.content_type.startswith("text/event-stream")
    body = res.get_data(as_text=True)
    assert '"step": "flow"' in body and "event: end" in body


def test_events_for_an_unknown_run_is_404(client):
    _login(client)
    assert client.get("/live/events?run_id=nope").status_code == 404


def test_logout_closes_the_page(client):
    _login(client)
    assert client.get("/live").status_code == 200
    client.post("/live/logout")
    assert client.get("/live").status_code == 401


# ---------------------------------------------------------------- the runs page
def test_runs_page_lists_server_runs_with_status_and_duration(client, app, tmp_path):
    from app import artifacts as A

    for run_id, final in (("20260914-100000", "published"), ("20260914-110000", "handoff_failed")):
        log = RunLogger(new_run_dir(tmp_path, run_id))
        log.event("flow", "start", run_id=run_id)
        log.event("flow", "ok" if final == "published" else "fail", result=final)
    rows = A.list_server_runs(tmp_path)
    assert [r["run_id"] for r in rows] == ["20260914-110000", "20260914-100000"]  # newest first
    assert rows[1]["result"] == "published" and rows[0]["result"] == "handoff_failed"
    assert all(r["duration_s"] is not None for r in rows)

    body = client.get("/runs").get_data(as_text=True)
    assert "20260914-110000" in body and "handoff_failed" in body
    assert "not committed" in body.lower()
