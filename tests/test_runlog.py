"""M5 task 4: every run writes events.jsonl + flow.log, and a manifest whose hashes match the files."""

from __future__ import annotations

import hashlib
import json
import re

import pytest

from hv import runlog


def test_new_run_dir_creates_the_crew_folders(tmp_path):
    run_dir = runlog.new_run_dir(tmp_path, run_id="abc")
    assert run_dir == tmp_path / "abc"
    assert (run_dir / "crew1").is_dir() and (run_dir / "crew2").is_dir()


def test_new_run_dir_names_the_run_by_timestamp_when_no_id_given(tmp_path):
    run_dir = runlog.new_run_dir(tmp_path)
    assert re.fullmatch(r"\d{8}-\d{6}", run_dir.name), run_dir.name
    assert run_dir.parent == tmp_path


def test_event_appends_one_json_line_and_one_log_line(tmp_path):
    log = runlog.RunLogger(tmp_path)
    log.event("ingest", "start")
    log.event("ingest", "ok", rows=5073, sha256="ab" * 32)

    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    second = json.loads(lines[1])
    assert second["step"] == "ingest" and second["status"] == "ok"
    assert second["rows"] == 5073 and second["sha256"] == "ab" * 32
    assert "ts" in second
    text = (tmp_path / "flow.log").read_text(encoding="utf-8")
    assert text.count("\n") == 2 and "ingest" in text and "5073" in text


def test_event_refuses_an_unknown_status(tmp_path):
    log = runlog.RunLogger(tmp_path)
    with pytest.raises(ValueError, match="status"):
        log.event("ingest", "done")


def test_step_logs_start_and_ok_with_a_duration(tmp_path):
    log = runlog.RunLogger(tmp_path)
    with log.step("analyst"):
        pass
    events = [json.loads(ln) for ln in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert [(e["step"], e["status"]) for e in events] == [("analyst", "start"), ("analyst", "ok")]
    assert events[1]["duration_s"] >= 0
    assert log.durations == {"analyst": events[1]["duration_s"]}


def test_step_logs_fail_with_the_error_and_re_raises(tmp_path):
    log = runlog.RunLogger(tmp_path)
    with pytest.raises(RuntimeError, match="crew crashed"):
        with log.step("analyst"):
            raise RuntimeError("crew crashed")
    events = [json.loads(ln) for ln in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert events[-1]["status"] == "fail"
    assert "RuntimeError" in events[-1]["error"] and "crew crashed" in events[-1]["error"]
    assert "analyst" in log.durations


def test_write_manifest_hashes_every_artifact(tmp_path):
    run_dir = runlog.new_run_dir(tmp_path, run_id="r1")
    a = run_dir / "crew1" / "clean_data.csv"
    b = run_dir / "crew2" / "metrics.json"
    a.write_bytes(b"CustomerID,Churn\n1,0\n")
    b.write_text('{"served": "hist_gb"}')

    path = runlog.write_manifest(
        run_dir, {"clean_data.csv": a, "metrics.json": b}, {"durations_s": {"ingest": 0.1}}
    )

    assert path == run_dir / "manifest.json"
    m = json.loads(path.read_text(encoding="utf-8"))
    assert m["run_id"] == "r1" and m["created_at"]
    assert m["artifacts"]["clean_data.csv"] == {
        "path": "crew1/clean_data.csv",
        "sha256": hashlib.sha256(a.read_bytes()).hexdigest(),
        "bytes": a.stat().st_size,
    }
    assert m["artifacts"]["metrics.json"]["path"] == "crew2/metrics.json"
    assert set(m["versions"]) == {"python", "pandas", "sklearn", "crewai"}
    assert m["durations_s"] == {"ingest": 0.1}


def test_write_manifest_refuses_a_missing_artifact(tmp_path):
    run_dir = runlog.new_run_dir(tmp_path, run_id="r2")
    with pytest.raises(FileNotFoundError, match="features.csv"):
        runlog.write_manifest(run_dir, {"features.csv": run_dir / "crew2" / "features.csv"}, {})
