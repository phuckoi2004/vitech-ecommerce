"""Tích hợp SePay: chữ ký HMAC, cấu hình, payload, xử lý request webhook, QR. Không gọi mạng, không database."""

import json
import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from app.integrations.sepay import (
    SePayConfigError,
    SePayQrGateway,
    SePaySettings,
    SePayWebhookPayload,
    WebhookAuthenticationError,
    compute_signature,
    handle_sepay_webhook,
    verify_sepay_signature,
)
from app.services import BusinessRuleError, PaymentVerificationError

SECRET = "test-secret-not-real"
TS = "1700000000"
BODY = b'{"id":92704,"transferAmount":5000000}'
# Vector tính độc lập bằng: printf '%s' '1700000000.<BODY>' | openssl dgst -sha256 -hmac 'test-secret-not-real'
OPENSSL_SIGNATURE = "sha256=223c89f1f19988afee154f36de95ebdab22103ff1d63bcb9ec645c17bbcebc1c"

SAMPLE = {  # payload mẫu trong tài liệu SePay
    "id": 92704,
    "gateway": "Vietcombank",
    "transactionDate": "2024-07-02 11:08:33",
    "accountNumber": "0123456789",
    "subAccount": "",
    "code": "VTPAYABCDEFGH",
    "content": "VTPAYABCDEFGH NGUYEN VAN A chuyen tien",
    "transferType": "in",
    "description": "NGUYEN VAN A chuyen tien",
    "transferAmount": 130000,
    "accumulated": 105000000,
    "referenceCode": "FT24012345678",
}


def signed_headers(body: bytes, ts: str = TS, secret: str = SECRET) -> dict:
    return {"X-SePay-Signature": compute_signature(secret, ts, body), "X-SePay-Timestamp": ts}


def settings(**overrides) -> SePaySettings:
    values = dict(
        webhook_secret=SECRET, account_number="0123456789", bank="Vietcombank",
        qr_image_url="https://qr.example.test/img", payment_code_prefix="VTPAY", payment_code_length=10,
    )
    values.update(overrides)
    return SePaySettings(**values)


class SignatureTest(unittest.TestCase):
    def verify(self, body=BODY, headers=None, now=1700000000, secret=SECRET):
        verify_sepay_signature(body, headers if headers is not None else signed_headers(body), secret=secret, now=now)

    def reason(self, **kwargs):
        with self.assertRaises(WebhookAuthenticationError) as ctx:
            self.verify(**kwargs)
        return ctx.exception.reason

    def test_matches_independent_openssl_vector(self):
        self.assertEqual(compute_signature(SECRET, TS, BODY), OPENSSL_SIGNATURE)
        self.verify(headers={"X-SePay-Signature": OPENSSL_SIGNATURE, "X-SePay-Timestamp": TS})

    def test_headers_are_case_insensitive(self):
        self.verify(headers={"x-sepay-signature": OPENSSL_SIGNATURE, "x-sepay-timestamp": TS})

    def test_wrong_secret_tampered_body_or_signature_rejected(self):
        self.assertEqual(self.reason(secret="other-secret"), "invalid_signature")
        self.assertEqual(self.reason(body=BODY.replace(b"5000000", b"5000001"), headers=signed_headers(BODY)), "invalid_signature")
        self.assertEqual(self.reason(headers={"X-SePay-Signature": OPENSSL_SIGNATURE[len("sha256="):], "X-SePay-Timestamp": TS}),
                         "invalid_signature")
        self.assertEqual(self.reason(headers={"X-SePay-Signature": OPENSSL_SIGNATURE.upper(), "X-SePay-Timestamp": TS}),
                         "invalid_signature")

    def test_reserialized_json_is_not_the_raw_body(self):
        raw = b'{"id": 92704,  "transferAmount": 5000000}'  # khoảng trắng như SePay gửi
        reserialized = json.dumps(json.loads(raw)).encode()
        self.assertNotEqual(raw, reserialized)
        self.assertEqual(self.reason(body=reserialized, headers=signed_headers(raw)), "invalid_signature")
        self.verify(body=raw, headers=signed_headers(raw))

    def test_missing_headers(self):
        self.assertEqual(self.reason(headers={"X-SePay-Timestamp": TS}), "missing_signature_headers")
        self.assertEqual(self.reason(headers={"X-SePay-Signature": OPENSSL_SIGNATURE}), "missing_signature_headers")
        self.assertEqual(self.reason(headers={}), "missing_signature_headers")

    def test_timestamp_validation(self):
        self.assertEqual(self.reason(headers=signed_headers(BODY, ts="17000x0000")), "invalid_timestamp")
        self.assertEqual(self.reason(headers=signed_headers(BODY, ts="-1700000000")), "invalid_timestamp")
        self.assertEqual(self.reason(now=1700000000 + 301), "timestamp_out_of_tolerance")
        self.assertEqual(self.reason(now=1700000000 - 301), "timestamp_out_of_tolerance")
        self.verify(now=1700000000 + 300)
        self.verify(now=1700000000 - 300)

    def test_missing_secret_refuses_instead_of_skipping_verification(self):
        with self.assertRaises(SePayConfigError):
            self.verify(secret="")

    def test_raw_body_must_be_bytes(self):
        with self.assertRaises(TypeError):
            verify_sepay_signature(BODY.decode(), signed_headers(BODY), secret=SECRET, now=1700000000)


class SettingsTest(unittest.TestCase):
    def test_required_webhook_config_and_no_secret_leak(self):
        with self.assertRaises(SePayConfigError) as ctx:
            SePaySettings.from_env({"SEPAY_WEBHOOK_SECRET": "  ", "SEPAY_ACCOUNT_NUMBER": ""})
        self.assertIn("SEPAY_WEBHOOK_SECRET", str(ctx.exception))
        self.assertIn("SEPAY_ACCOUNT_NUMBER", str(ctx.exception))
        loaded = SePaySettings.from_env({"SEPAY_WEBHOOK_SECRET": "super-secret-value", "SEPAY_ACCOUNT_NUMBER": " 0123 "})
        self.assertEqual(loaded.account_number, "0123")
        self.assertNotIn("super-secret-value", repr(loaded))

    def test_qr_config_validation(self):
        with self.assertRaises(SePayConfigError) as ctx:
            SePaySettings.from_env({"SEPAY_WEBHOOK_SECRET": "s", "SEPAY_ACCOUNT_NUMBER": "1"}).require_qr()
        for name in ("SEPAY_BANK", "SEPAY_QR_IMAGE_URL", "SEPAY_PAYMENT_CODE_PREFIX", "SEPAY_PAYMENT_CODE_LENGTH"):
            self.assertIn(name, str(ctx.exception))
        for bad in (dict(qr_image_url="http://qr.example.test/img"), dict(payment_code_prefix="VT-1"),
                    dict(payment_code_length=7), dict(payment_code_length=31)):
            with self.subTest(bad=bad), self.assertRaises(SePayConfigError):
                settings(**bad).require_qr()
        with self.assertRaises(SePayConfigError):
            SePaySettings.from_env({"SEPAY_WEBHOOK_SECRET": "s", "SEPAY_ACCOUNT_NUMBER": "1", "SEPAY_PAYMENT_CODE_LENGTH": "abc"})


class PayloadTest(unittest.TestCase):
    def test_documented_sample_parses(self):
        payload = SePayWebhookPayload.model_validate({**SAMPLE, "newFieldFromSePay": "x"})
        self.assertEqual((payload.id, payload.transferAmount, payload.payment_code), (92704, 130000, "VTPAYABCDEFGH"))
        self.assertEqual(payload.transaction_time_utc, datetime(2024, 7, 2, 4, 8, 33, tzinfo=timezone.utc))
        self.assertEqual(payload.reconciliation_key(), "sepay:0123456789:92704")
        stored = payload.stored_response_data()
        self.assertNotIn("content", stored)
        self.assertNotIn("description", stored)

    def test_nullable_and_empty_fields(self):
        payload = SePayWebhookPayload.model_validate({**SAMPLE, "code": None, "referenceCode": "", "description": "",
                                                      "transactionDate": "02/07/2024"})
        self.assertIsNone(payload.payment_code)
        self.assertIsNone(payload.transaction_time_utc)  # không đọc được ngày: không chặn ghi nhận
        self.assertIsNone(SePayWebhookPayload.model_validate({**SAMPLE, "code": "   "}).payment_code)

    def test_invalid_core_fields_rejected(self):
        bad_values = [
            {"id": "92704"}, {"id": None}, {"id": True}, {"transferAmount": 5000000.5}, {"transferAmount": -1},
            {"transferAmount": "130000"}, {"transferType": "IN"}, {"transferType": None}, {"accountNumber": ""},
        ]
        for bad in bad_values:
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                SePayWebhookPayload.model_validate({**SAMPLE, **bad})
        for missing in ("id", "accountNumber", "transferType", "transferAmount"):
            data = dict(SAMPLE)
            data.pop(missing)
            with self.subTest(missing=missing), self.assertRaises(ValidationError):
                SePayWebhookPayload.model_validate(data)


class HandleWebhookRequestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.calls = []

    def process(self, payload, data, cfg):
        self.calls.append((payload, data))
        return "paid"

    def handle(self, body, headers, *, process=None, loader=None):
        return handle_sepay_webhook(
            body, headers, settings_loader=loader or (lambda: settings()), process=process or self.process,
            now=lambda: 1700000000,
        )

    def body(self, **overrides):
        return json.dumps({**SAMPLE, **overrides}).encode()

    def test_success_response_matches_sepay_contract(self):
        body = self.body()
        status, response = self.handle(body, signed_headers(body))
        self.assertEqual((status, response), (200, {"success": True}))
        [(payload, data)] = self.calls
        self.assertEqual((payload.id, data["content"]), (92704, SAMPLE["content"]))

    def test_rejections_do_not_process(self):
        body = self.body()
        missing_config = lambda: (_ for _ in ()).throw(SePayConfigError("Thiếu cấu hình: SEPAY_WEBHOOK_SECRET"))
        cases = [
            (dict(loader=missing_config), body, signed_headers(body), 503),
            ({}, body, {**signed_headers(body), "X-SePay-Signature": "sha256=00"}, 401),
            ({}, body, {}, 401),
            ({}, b"not json", signed_headers(b"not json"), 400),
            ({}, b"[1, 2]", signed_headers(b"[1, 2]"), 400),
            ({}, self.body(transferAmount=-5), signed_headers(self.body(transferAmount=-5)), 400),
        ]
        for kwargs, payload, headers, expected in cases:
            with self.subTest(expected=expected), self.assertLogs("app.integrations.sepay", level="WARNING"):
                status, response = self.handle(payload, headers, **kwargs)
            self.assertEqual((status, response), (expected, {"success": False}))
        self.assertEqual(self.calls, [])

    def test_storage_failure_returns_retryable_error_without_leaking(self):
        body = self.body()
        headers = signed_headers(body)

        def failing(payload, data, cfg):
            raise RuntimeError(f"INSERT ... params={data['content']} secret={SECRET}")

        with self.assertLogs("app.integrations.sepay", level="ERROR") as logs:
            status, response = self.handle(body, headers, process=failing)
        self.assertEqual((status, response), (500, {"success": False}))
        joined = "\n".join(logs.output)
        for sensitive in (SECRET, SAMPLE["content"], SAMPLE["description"], headers["X-SePay-Signature"]):
            self.assertNotIn(sensitive, joined)
        self.assertIn("92704", joined)

    def test_success_logs_contain_no_sensitive_data(self):
        body = self.body()
        headers = signed_headers(body)
        with self.assertLogs("app.integrations.sepay", level="INFO") as logs:
            self.handle(body, headers)
        joined = "\n".join(logs.output)
        for sensitive in (SECRET, SAMPLE["content"], SAMPLE["description"], headers["X-SePay-Signature"], "0123456789"):
            self.assertNotIn(sensitive, joined)


class QrGatewayTest(unittest.TestCase):
    def test_builds_vietqr_url_with_random_payment_code(self):
        gateway = SePayQrGateway(settings())
        request = gateway.create_qr_payment(order_code="VT000001", amount=Decimal("130000.00"))
        url = urlparse(request.qr_data)
        query = parse_qs(url.query)
        self.assertEqual(f"{url.scheme}://{url.netloc}{url.path}", "https://qr.example.test/img")
        self.assertEqual((query["acc"], query["bank"], query["amount"]), (["0123456789"], ["Vietcombank"], ["130000"]))
        code = request.gateway_transaction_code
        self.assertEqual(query["des"], [code])
        self.assertTrue(code.startswith("VTPAY") and len(code) == 15 and code[5:].isalnum() and code[5:].isupper())
        self.assertNotIn("VT000001", code)  # mã không suy ra từ mã đơn (khó đoán)
        self.assertNotEqual(code, gateway.create_qr_payment(order_code="VT000001", amount=Decimal("1")).gateway_transaction_code)

    def test_amount_must_be_whole_vnd(self):
        gateway = SePayQrGateway(settings())
        for amount in (Decimal("130000.50"), Decimal("0"), Decimal("-1")):
            with self.subTest(amount=amount), self.assertRaises(BusinessRuleError) as ctx:
                gateway.create_qr_payment(order_code="X", amount=amount)
            self.assertEqual(ctx.exception.code, "qr_amount_not_supported")

    def test_capabilities(self):
        gateway = SePayQrGateway(settings())
        self.assertFalse(gateway.supports_refund)
        with self.assertRaises(PaymentVerificationError):
            gateway.verify_callback({})
        with self.assertRaises(SePayConfigError):
            SePayQrGateway(settings(bank=None))


class RouterTest(unittest.TestCase):
    def test_only_post_and_no_database_import(self):
        import app.routers.webhooks as webhooks

        self.assertEqual([(r.path, sorted(r.methods)) for r in webhooks.router.routes], [("/webhooks/sepay", ["POST"])])
        self.assertNotIn("app.database", sys.modules)


if __name__ == "__main__":
    unittest.main()
