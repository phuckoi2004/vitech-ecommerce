"""Machine-to-machine routes: cron endpoints guarded by INTERNAL_CRON_SECRET and the SePay webhook."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from sqlalchemy.exc import OperationalError

from app.main import app
from app.routers import dependencies as deps
from app.routers import internal
from app.services.base import BaseService
from app.services.internal_jobs import JobRun, run_job

from tests.fakes import FakeSession, InMemoryDB

SECRET = "cron-secret-for-tests-0123456789abcdef"
SEPAY_ENV = ("SEPAY_WEBHOOK_SECRET", "SEPAY_ACCOUNT_NUMBER", "SEPAY_BANK", "SEPAY_QR_IMAGE_URL",
             "SEPAY_PAYMENT_CODE_PREFIX", "SEPAY_PAYMENT_CODE_LENGTH")


class FakeJobs:
    def __init__(self):
        self.calls = []
        self.expiry = JobRun("expire_unpaid_qr_orders", selected=4, processed=3, skipped=1)
        self.webhooks = JobRun("process_unprocessed_webhooks", selected=2, processed=2)

    def expire_unpaid_qr_orders(self, *, limit):
        self.calls.append(("expire_unpaid_qr_orders", {"limit": limit}))
        if isinstance(self.expiry, Exception):
            raise self.expiry
        return self.expiry

    def process_unprocessed(self, *, older_than, limit):
        self.calls.append(("process_unprocessed", {"older_than": older_than, "limit": limit}))
        return self.webhooks


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
    assert response.status_code == 200
    assert response.json() == {"Processed": 3, "Selected": 4, "Skipped": 1, "Failed": 0}
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
    assert response.status_code == 200
    assert response.json() == {"Processed": 2, "Selected": 2, "Skipped": 0, "Failed": 0}
    assert jobs.calls[-1] == ("process_unprocessed", {"older_than": timedelta(minutes=10), "limit": 20})


@pytest.mark.parametrize("path", ["/internal/orders/expire-unpaid-qr", "/internal/payment-webhooks/process"])
def test_a_run_with_failed_records_is_reported_as_a_failure_with_its_counts(client, path):
    test_client, jobs, _ = client
    app.dependency_overrides[internal.get_payment_webhook_service] = lambda: jobs
    jobs.expiry = JobRun("expire_unpaid_qr_orders", selected=3, processed=2, failed=1)
    jobs.webhooks = JobRun("process_unprocessed_webhooks", selected=3, processed=1, skipped=1, failed=1)
    response = test_client.post(path, headers=auth())
    assert response.status_code == 500
    body = response.json()
    assert body["Failed"] == 1 and body["Selected"] == 3
    assert body["Processed"] + body["Skipped"] + body["Failed"] == body["Selected"]
    assert SECRET not in response.text


def test_webhook_retry_job_parameters_are_bounded(client):
    test_client, jobs, _ = client
    app.dependency_overrides[internal.get_payment_webhook_service] = lambda: jobs
    for params in ({"older_than_minutes": 0}, {"older_than_minutes": 1441}, {"limit": 0}, {"limit": 1001}):
        assert test_client.post("/internal/payment-webhooks/process", headers=auth(), params=params).status_code == 422
    assert jobs.calls == []


def test_a_database_error_before_selection_is_a_logged_503_without_its_text(client, caplog):
    test_client, jobs, _ = client
    jobs.expiry = OperationalError("SELECT secret_column FROM x", {"p": "private-value"}, Exception("conn to db.host"))
    with caplog.at_level("ERROR", logger="app.main"):
        response = test_client.post("/internal/orders/expire-unpaid-qr", headers=auth())
    assert response.status_code == 503
    assert "private-value" not in response.text and "db.host" not in response.text
    [record] = [r for r in caplog.records if r.name == "app.main"]
    assert "OperationalError" in record.getMessage() and "/internal/orders/expire-unpaid-qr" in record.getMessage()
    for leaked in ("secret_column", "private-value", "db.host", SECRET):
        assert leaked not in record.getMessage()


def test_sepay_webhook_is_registered_but_refuses_until_configured(client):
    test_client, _, _ = client
    response = test_client.post("/webhooks/sepay", content=b'{"id": 1}', headers={"Content-Type": "application/json"})
    assert response.status_code == 503
    assert response.json() == {"success": False}


class BrokenSelection:
    """Both jobs through the real run_job, with a selection step that raises ``error``."""

    def __init__(self, error):
        self.error = error

    def _run(self, job):
        def select():
            raise self.error

        return run_job(BaseService(FakeSession(InMemoryDB())), job, select=select, handle=lambda record_id: True)

    def expire_unpaid_qr_orders(self, *, limit):
        return self._run("expire_unpaid_qr_orders")

    def process_unprocessed(self, *, older_than, limit):
        return self._run("process_unprocessed_webhooks")


JOB_PATHS = ["/internal/orders/expire-unpaid-qr", "/internal/payment-webhooks/process"]


@pytest.mark.parametrize("path", JOB_PATHS)
def test_an_unexpected_selection_error_is_a_500_with_the_standard_error_body_and_no_counts(client, path):
    test_client, _, _ = client
    broken = BrokenSelection(RuntimeError("internal detail private-value"))
    app.dependency_overrides[deps.get_order_service] = lambda: broken
    app.dependency_overrides[internal.get_payment_webhook_service] = lambda: broken
    response = test_client.post(path, headers=auth())
    assert response.status_code == 500
    assert response.json() == {
        "detail": "Không chọn được bản ghi để xử lý; tác vụ chưa xử lý bản ghi nào. Vui lòng thử lại sau.",
        "code": "job_selection_failed",
    }
    assert "private-value" not in response.text


@pytest.mark.parametrize("path", JOB_PATHS)
def test_a_database_error_at_selection_stays_a_503(client, path):
    test_client, _, _ = client
    broken = BrokenSelection(OperationalError("SELECT 1", {}, Exception("conn to db.host")))
    app.dependency_overrides[deps.get_order_service] = lambda: broken
    app.dependency_overrides[internal.get_payment_webhook_service] = lambda: broken
    response = test_client.post(path, headers=auth())
    assert response.status_code == 503
    assert response.json() == {"detail": "Không thể xử lý dữ liệu lúc này. Vui lòng thử lại"}


def test_internal_routes_are_hidden_from_the_public_schema():
    paths = app.openapi()["paths"]
    assert not [path for path in paths if path.startswith("/internal")]
    assert "/webhooks/sepay" in paths
