"""Shared helpers for the Stage 7 API tests (tests/api).

Every test talks to the application only over HTTP (FastAPI TestClient) with real JWT logins. Test data that is
not the subject of the test (catalog rows, payment/shipping methods, users) is inserted directly with the ORM
inside the test's own database transaction, which is rolled back afterwards.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from app.models import (
    Brand,
    Category,
    PaymentMethod,
    Product,
    ProductVariant,
    ShippingMethod,
    Supplier,
    User,
)
from tests.postgres_safety import POSTGRES_TESTS_ENABLED

PASSWORD = "Password1!"

requires_postgres = pytest.mark.skipif(
    not POSTGRES_TESTS_ENABLED, reason="API tests need RUN_POSTGRES_TESTS=1 and a separate TEST_DATABASE_URL")


def random_id() -> str:
    return str(uuid.uuid4())


def tag() -> str:
    return uuid.uuid4().hex[:10]


# ------------------------------------------------------------------------------------------------- assertions


def expect(response, status: int, code: str | None = None):
    """Assert the HTTP status (and the business ``code`` of ServiceError bodies); return the JSON body."""
    assert response.status_code == status, f"expected {status}, got {response.status_code}: {response.text}"
    if status == 204:
        return None
    body = response.json()
    if code is not None:
        assert body.get("code") == code, f"expected code {code!r}, got {body}"
    return body


def expect_validation(response, *fields: str):
    """422 from request validation, naming each field that failed (body, query or path)."""
    body = expect(response, 422)
    failed = {str(part) for error in body["detail"] for part in error["loc"]}
    missing = [name for name in fields if name not in failed]
    assert not missing, f"422 did not report {missing}: {body['detail']}"
    # Validation errors never echo the submitted values back.
    assert all(set(error) == {"loc", "msg", "type"} for error in body["detail"])
    return body


def expect_unauthorized(response):
    assert response.status_code == 401, f"expected 401, got {response.status_code}: {response.text}"
    return response.json()


def expect_forbidden(response):
    assert response.status_code == 403, f"expected 403, got {response.status_code}: {response.text}"
    return response.json()


# ------------------------------------------------------------------------------------------------- actors


@dataclass
class Person:
    id: str
    email: str
    phone: str
    role: str
    headers: dict = field(default_factory=dict)


# ------------------------------------------------------------------------------------------------- seeding


class Seed:
    """Direct ORM inserts for arrangement data; every commit only releases a savepoint of the test transaction."""

    def __init__(self, sessions, password_hash: str):
        self.sessions = sessions
        self.password_hash = password_hash

    def add(self, *rows):
        with self.sessions() as db:
            db.add_all(rows)
            db.commit()

    def user(self, role: str = "Customer", *, status: str = "Active") -> Person:
        identity = uuid.uuid4()
        email = f"{role.lower()}-{identity.hex[:12]}@example.com"
        phone = f"09{identity.int % 10**8:08d}"
        self.add(User(UserId=identity, Email=email, PhoneNumber=phone, FullName=f"Test {role}",
                      PasswordHash=self.password_hash, Role=role, AccountStatus=status,
                      IsEmailVerified=True, IsDeleted=False))
        return Person(id=str(identity), email=email, phone=phone, role=role)

    def variant(self, *, stock: int = 10, price: str = "100000.00", cost: str = "70000.00",
                status: str = "Active", warranty_months: int = 12) -> dict:
        t = tag()
        ids = {key: uuid.uuid4() for key in ("category", "brand", "product", "variant")}
        result = {"category_id": str(ids["category"]), "category_slug": f"danh-muc-{t}", "brand_id": str(ids["brand"]),
                  "product_id": str(ids["product"]), "product_slug": f"dien-thoai-{t}",
                  "variant_id": str(ids["variant"]), "sku": f"SKU-{t.upper()}"}
        self.add(Category(CategoryId=ids["category"], Name=f"Danh mục {t}", Slug=result["category_slug"]),
                 Brand(BrandId=ids["brand"], Name=f"Hãng {t}", Slug=f"hang-{t}"))
        self.add(Product(ProductId=ids["product"], CategoryId=ids["category"], BrandId=ids["brand"],
                         Name=f"Điện thoại {t}", Slug=result["product_slug"], WarrantyMonths=warranty_months,
                         Status=status))
        self.add(ProductVariant(ProductVariantId=ids["variant"], ProductId=ids["product"], Sku=result["sku"],
                                VariantName="8GB/128GB", Price=Decimal(price), StockQuantity=stock,
                                CostPrice=Decimal(cost)))
        return result

    def shipping_method(self, fee: str = "30000.00") -> str:
        method_id = uuid.uuid4()
        self.add(ShippingMethod(ShippingMethodId=method_id, Code=f"SHIP-{tag().upper()}", Name="Giao tiêu chuẩn",
                                BaseFee=Decimal(fee), EstimatedDays=3))
        return str(method_id)

    def payment_method(self, code: str = "COD") -> str:
        method_id = uuid.uuid4()
        self.add(PaymentMethod(PaymentMethodId=method_id, Code=code, Name=f"Thanh toán {code}"))
        return str(method_id)

    def supplier(self) -> dict:
        supplier_id, code = uuid.uuid4(), f"NCC-{tag().upper()}"
        self.add(Supplier(SupplierId=supplier_id, SupplierCode=code, Name="Nhà cung cấp",
                          PhoneNumber="0281234567", Address="1 Lê Lợi, TP.HCM"))
        return {"supplier_id": str(supplier_id), "code": code}
