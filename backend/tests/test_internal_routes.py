"""Machine-to-machine routes: cron endpoints guarded by INTERNAL_CRON_SECRET and the SePay webhook."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import dependencies as deps
from app.routers import internal

SECRET = "cron-secret-for-tests-0123456789abcdef"
SEPAY_ENV = ("SEPAY_WEBHOOK_SECRET", "SEPAY_ACCOUNT_NUMBER", "SEPAY_BANK", "SEPAY_QR_IMAGE_URL",
             "SEPAY_PAYMENT_CODE_PREFIX", "SEPAY_PAYMENT_CODE_LENGTH")


class FakeJobs:
    def __init__(self):
        self.calls = []

    def expire_unpaid_qr_orders(self, *, limit):
        self.calls.append(("expire_unpaid_qr_orders", {"limit": limit}))
        return 3

    def process_unprocessed(self, *, older_than, limit):
        self.calls.append(("process_unprocessed", {"older_than": older_than, "limit": limit}))
        return 2


@pytest.fixture
def client(monkeypatch):
    for name in SEPAY_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(internal.INTERNAL_SECRET_ENV, SECRET)
    jobs = FakeJobs()
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[deps.get_order_service] = lambda: jobs
    try:
        with TestClient(app) as test_client:
            yield test_client, jobs, monkeypatch
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def auth(secret=SECRET):
    return {"X-Internal-Secret": secret}


def test_expire_job_requires_the_cron_secret(client):
    test_client, jobs, _ = client
    assert test_client.post("/internal/orders/expire-unpaid-qr").status_code == 401
    assert test_client.post("/internal/orders/expire-unpaid-qr", headers=auth("wrong")).status_code == 401
    assert jobs.calls == []
    response = test_client.post("/internal/orders/expire-unpaid-qr", headers=auth(), params={"limit": 50})
    assert response.status_code == 200 and response.json() == {"Processed": 3}
    assert jobs.calls == [("expire_unpaid_qr_orders", {"limit": 50})]
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("configured", [None, "too-short"])
def test_missing_or_weak_secret_disables_internal_routes(client, configured):
    test_client, jobs, monkeypatch = client
    if configured is None:
        monkeypatch.delenv(internal.INTERNAL_SECRET_ENV)
    else:
        monkeypatch.setenv(internal.INTERNAL_SECRET_ENV, configured)
    response = test_client.post("/internal/orders/expire-unpaid-qr", headers=auth(configured or SECRET))
    assert response.status_code == 503
    assert jobs.calls == []


def test_job_limits_are_bounded(client):
    test_client, jobs, _ = client
    for limit in (0, 1001):
        assert test_client.post("/internal/orders/expire-unpaid-qr", headers=auth(),
                                params={"limit": limit}).status_code == 422
    assert jobs.calls == []


def test_webhook_retry_job_checks_the_secret_before_sepay_configuration(client):
    test_client, _, _ = client
    # Without the secret the caller cannot learn whether SePay is configured.
    assert test_client.post("/internal/payment-webhooks/process").status_code == 401
    response = test_client.post("/internal/payment-webhooks/process", headers=auth())
    assert response.status_code == 503


def test_webhook_retry_job_runs_when_configured(client):
    test_client, jobs, _ = client
    app.dependency_overrides[internal.get_payment_webhook_service] = lambda: jobs
    response = test_client.post("/internal/payment-webhooks/process", headers=auth(),
                                params={"limit": 20, "older_than_minutes": 10})
    assert response.status_code == 200 and response.json() == {"Processed": 2}
    assert jobs.calls[-1] == ("process_unprocessed", {"older_than": timedelta(minutes=10), "limit": 20})


def test_sepay_webhook_is_registered_but_refuses_until_configured(client):
    test_client, _, _ = client
    response = test_client.post("/webhooks/sepay", content=b'{"id": 1}', headers={"Content-Type": "application/json"})
    assert response.status_code == 503
    assert response.json() == {"success": False}


def test_internal_routes_are_hidden_from_the_public_schema():
    paths = app.openapi()["paths"]
    assert not [path for path in paths if path.startswith("/internal")]
    assert "/webhooks/sepay" in paths
