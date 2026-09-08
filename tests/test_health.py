import pytest

from app.main import create_app


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
    assert body["model_loaded"] is False  # no model artifact before M4
    assert body["uptime_s"] >= 0


def test_index_serves_html(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"HarborVale" in res.data


def test_health_prefers_railway_commit(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abcdef1234567890")
    app = create_app()
    assert app.config["COMMIT"] == "abcdef123456"
