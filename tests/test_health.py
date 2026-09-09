import pytest

from app.main import create_app
from hv.config import ARTIFACTS_DIR


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_health_reports_version_and_commit(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert isinstance(body["commit"], str) and body["commit"]
    # M4 published artifacts/crew2/model.joblib, so this now reports True on a full checkout;
    # what /health must always do is tell the truth about whether the file is there.
    assert body["model_loaded"] is (ARTIFACTS_DIR / "crew2" / "model.joblib").exists()
    assert body["uptime_s"] >= 0


def test_index_serves_html(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"HarborVale" in res.data


def test_health_prefers_railway_commit(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abcdef1234567890")
    app = create_app()
    assert app.config["COMMIT"] == "abcdef123456"
