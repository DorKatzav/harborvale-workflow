"""Every page renders from the committed artifacts, and the break-it endpoint refuses bad data."""

import io

import pytest

from app.main import create_app
from hv.contract import PRESETS


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


@pytest.mark.parametrize("path", ["/", "/analyst", "/contract", "/scientist", "/runs"])
def test_pages_render(client, path):
    res = client.get(path)
    assert res.status_code == 200
    assert b"HarborVale" in res.data


def test_home_shows_the_seam_and_the_last_verdict(client):
    body = client.get("/").get_data(as_text=True)
    assert "clean_data.csv" in body and "dataset_contract.json" in body
    assert "5,073" in body  # rows, from the contract
    assert "Accepted" in body


def test_contract_page_lists_every_column_and_the_assumptions(client):
    body = client.get("/contract").get_data(as_text=True)
    for name in ("CashbackAmount", "Tenure", "PreferredPaymentMode", "Gender"):
        assert name in body
    assert "USD" in body  # the unit that started the Harbor &amp; Vale story
    assert "cents" in body.lower()  # the steward's assumption is on the page


def test_analyst_page_embeds_the_eda_report_and_insights(client):
    body = client.get("/analyst").get_data(as_text=True)
    assert "eda_report.html" in body  # served as a file, not inlined
    assert "Key numbers" in body


def test_scientist_page_is_honest_when_crew2_has_not_published(client):
    body = client.get("/scientist").get_data(as_text=True)
    assert "Not published yet" in body or "model card" in body.lower()


@pytest.mark.parametrize("preset", PRESETS)
def test_validate_catches_every_preset(client, preset):
    res = client.post("/api/validate", json={"preset": preset})
    assert res.status_code == 200
    body = res.get_json()
    assert body["passed"] is False
    assert body["failed_names"], f"{preset} produced no failing check"
    assert body["preset"] == preset
    assert any(c["hint"] for c in body["checks"] if not c["passed"])


def test_validate_names_the_unit_change(client):
    body = client.post("/api/validate", json={"preset": "unit_change"}).get_json()
    failures = [c for c in body["checks"] if not c["passed"]]
    assert any("CashbackAmount" == c["column"] for c in failures)
    assert any(c["hint"] and "100" in c["hint"] for c in failures)


def test_validate_rejects_an_unknown_preset(client):
    res = client.post("/api/validate", json={"preset": "definitely_not_a_preset"})
    assert res.status_code == 400
    assert "preset" in res.get_json()["error"]


def test_validate_with_no_payload_explains_what_to_send(client):
    res = client.post("/api/validate", json={})
    assert res.status_code == 400
    assert res.get_json()["error"]


def test_validate_accepts_an_uploaded_csv_and_reports_the_verdict(client):
    original = open("artifacts/crew1/clean_data.csv", encoding="utf-8").read()
    broken = original.replace("50001", "50001", 1).replace(",1,\n", ",1,\n", 1)
    tampered = "\n".join(original.splitlines()[:100]) + "\n"  # 99 rows instead of 5,073
    res = client.post(
        "/api/validate",
        data={"clean_data": (io.BytesIO(tampered.encode()), "clean_data.csv")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["passed"] is False
    assert "rows" in body["failed_names"]
    assert broken is not None


def test_validate_accepts_the_real_file(client):
    with open("artifacts/crew1/clean_data.csv", "rb") as fh:
        res = client.post(
            "/api/validate",
            data={"clean_data": (fh, "clean_data.csv")},
            content_type="multipart/form-data",
        )
    body = res.get_json()
    assert res.status_code == 200 and body["passed"] is True


def test_validate_refuses_a_file_that_is_too_large(client):
    big = io.BytesIO(b"x" * (A_MAX + 1))
    res = client.post(
        "/api/validate",
        data={"clean_data": (big, "clean_data.csv")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 413


A_MAX = 8 * 1024 * 1024


def test_eda_report_is_served_as_a_file(client):
    res = client.get("/artifacts/crew1/eda_report.html")
    assert res.status_code == 200
    assert b"EDA report" in res.data


def test_unknown_artifact_path_is_not_traversable(client):
    assert client.get("/artifacts/../.env").status_code in (400, 404)
    assert client.get("/artifacts/crew1/../../.env").status_code in (400, 404)
