"""Catalog list integration on isolated in-memory SQLite; no application database is accessed.

The real Repository, Service and response schema run together. PostgreSQL-specific SQL compilation
is checked separately; this does not substitute for integration against PostgreSQL.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, MetaData, create_engine, event
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_actor
from app.models import Brand, Category, Product, ProductImage, ProductVariant, User, Cart, CartItem, Promotion, PromotionProduct, PromotionCategory
from app.repositories.catalog import ProductRepository
from app.routers.catalog import admin_router
from app.routers.dependencies import get_product_service, get_variant_service, get_catalog_item_service
from app.services.catalog_item import CatalogItemService
from app.routers.errors import service_error_handler
from app.services import Actor, ProductService, ProductVariantService, ServiceError
from tests.test_query_shapes import RecordingSession


@pytest.fixture
def catalog():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def functions(connection, _):
        connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)
        connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat(" "))
        # PostgreSQL's Unicode lower() and translate(), used by the customer keyword search.
        connection.create_function("lower", 1, lambda text: None if text is None else text.lower(), deterministic=True)
        connection.create_function("translate", 3, lambda text, source, target: None if text is None
                                   else text.translate(str.maketrans(source, target)), deterministic=True)

    metadata = MetaData()
    for model in (Category, Brand, Product, ProductVariant, ProductImage, User, Cart, CartItem, Promotion, PromotionProduct, PromotionCategory):
        table = model.__table__.to_metadata(metadata)
        if model is Product:
            table.c.Specifications.type = JSON()
    metadata.create_all(engine)
    with Session(engine) as session:
        category = Category(Name="Điện thoại", Slug="dien-thoai")
        brand = Brand(Name="Hãng", Slug="hang")
        session.add_all([category, brand]); session.flush()
        products = []
        for i in range(12):
            product = Product(CategoryId=category.CategoryId, BrandId=brand.BrandId, Name=f"Máy {i}",
                              Slug=f"may-{i}", WarrantyMonths=12, Status="Active")
            session.add(product); session.flush()
            session.add(ProductVariant(ProductId=product.ProductId, Sku=f"SKU-{i}", VariantName="Đen",
                                       Price=Decimal(1000000 * (i + 1)), StockQuantity=i, MinStockLevel=3))
            products.append(product)
        session.commit()
        app = FastAPI()
        app.include_router(admin_router)
        app.add_exception_handler(ServiceError, service_error_handler)
        actor = {"role": "Admin"}
        app.dependency_overrides[get_current_actor] = lambda: Actor(uuid.uuid4(), actor["role"])
        app.dependency_overrides[get_product_service] = lambda: ProductService(session)
        app.dependency_overrides[get_variant_service] = lambda: ProductVariantService(session)
        app.dependency_overrides[get_catalog_item_service] = lambda: CatalogItemService(session)
        with TestClient(app) as client:
            yield client, session, products, actor
    engine.dispose()


def test_filters_run_before_pagination_and_total_matches(catalog):
    client, _, _, _ = catalog
    response = client.get("/admin/products", params={"min_price": 2000000, "max_price": 9000000,
                                                   "stock": "in_stock", "page": 2, "page_size": 3})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["Total"] == 8
    assert len(data["Items"]) == 3
    assert all(2000000 <= Decimal(item["MinPrice"]) <= 9000000 for item in data["Items"])
    assert all(item["StockQuantity"] > 0 for item in data["Items"])
    first = client.get("/admin/products", params={"min_price": 2000000, "max_price": 9000000,
                                                "stock": "in_stock", "page_size": 3}).json()
    assert {p["ProductId"] for p in first["Items"]}.isdisjoint(p["ProductId"] for p in data["Items"])


def test_totals_prices_stock_and_thumbnail_exclude_deleted_variants(catalog):
    client, session, products, _ = catalog
    product = products[2]
    session.add(ProductVariant(ProductId=product.ProductId, Sku="DELETED", VariantName="Đã xóa",
                               Price=1, StockQuantity=999, MinStockLevel=1000, IsDeleted=True))
    session.add(ProductVariant(ProductId=product.ProductId, Sku="EXTRA", VariantName="Trắng",
                               Price=4000000, StockQuantity=10, MinStockLevel=0))
    session.add_all([ProductImage(ProductId=product.ProductId, ImageUrl="https://example.com/other.png",
                                 DisplayOrder=0), ProductImage(ProductId=product.ProductId,
                                 ImageUrl="https://example.com/default.png", IsDefault=True, DisplayOrder=5)])
    session.commit()
    row = client.get("/admin/products", params={"keyword": str(product.ProductId)}).json()["Items"][0]
    assert row["Category"]["Name"] == "Điện thoại"
    assert row["Brand"]["Name"] == "Hãng"
    assert row["Skus"] == ["EXTRA", "SKU-2"]  # user-entered codes; deleted variant's SKU is excluded
    assert Decimal(row["MinPrice"]) == 3000000
    assert Decimal(row["MaxPrice"]) == 4000000
    assert row["StockQuantity"] == 12
    assert row["IsLowStock"] is True  # one variant is below its own threshold
    assert row["ThumbnailUrl"] == "https://example.com/default.png"


def test_search_handles_name_sku_uuid_and_literal_like_wildcards(catalog):
    client, session, products, _ = catalog
    for term in ("SKU-5", str(products[5].ProductId), "Máy 5"):
        data = client.get("/admin/products", params={"keyword": term}).json()
        assert data["Total"] == 1
        assert data["Items"][0]["ProductId"] == str(products[5].ProductId)
        assert data["Items"][0]["Skus"] == ["SKU-5"]
    products[5].Name = "Máy 50%_x"
    session.commit()
    assert client.get("/admin/products", params={"keyword": "%_"}).json()["Total"] == 1


def test_stock_states_and_empty_variant_prices(catalog):
    client, session, products, _ = catalog
    low = client.get("/admin/products", params={"stock": "low_stock"}).json()
    assert {p["StockQuantity"] for p in low["Items"]} == {1, 2, 3}
    # A product without variants has no price, and zero stock (not an invented price of zero).
    bare = Product(CategoryId=products[0].CategoryId, BrandId=products[0].BrandId, Name="Chưa có biến thể",
                   Slug="chua-co-bien-the", WarrantyMonths=0, Status="Draft")
    session.add(bare); session.commit()
    out = client.get("/admin/products", params={"stock": "out_of_stock"}).json()
    assert out["Total"] == 2
    row = next(p for p in out["Items"] if p["ProductId"] == str(bare.ProductId))
    assert row["MinPrice"] is None and row["MaxPrice"] is None
    assert row["Skus"] == []
    assert row["IsLowStock"] is False
    assert client.get("/admin/products", params={"min_price": 0, "status": "Draft"}).json()["Total"] == 0


def test_soft_delete_and_role_boundaries_stay_intact(catalog):
    client, _, products, actor = catalog
    actor["role"] = "Staff"
    assert client.get("/admin/products").status_code == 200
    assert client.delete(f"/admin/products/{products[0].ProductId}").status_code == 403
    actor["role"] = "Customer"
    assert client.get("/admin/products").status_code == 403
    actor["role"] = "Admin"
    assert client.delete(f"/admin/products/{products[0].ProductId}").status_code == 204
    assert client.get("/admin/products").json()["Total"] == 11
    assert client.get("/admin/products", params={"include_deleted": True}).json()["Total"] == 12


def test_list_uses_bounded_queries_and_public_contract_stays_unchanged(catalog):
    client, session, _, _ = catalog
    statements = []
    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(session.bind, "before_cursor_execute", record)
    try:
        response = client.get("/admin/products", params={"page_size": 8})
        assert response.status_code == 200
        assert len(response.json()["Items"]) == 8
        assert len(statements) == 4  # one page+joins, variants, images, and count
    finally:
        event.remove(session.bind, "before_cursor_execute", record)
    public = ProductService(session).search_products(page_size=8)
    assert public.Total == 12
    assert "StockQuantity" not in public.Items[0].model_dump()
    assert "CostPrice" not in public.Items[0].model_dump()


@pytest.mark.parametrize("query,code", [({"stock": "invalid"}, 422), ({"min_price": -1}, 422),
                                       ({"page_size": 101}, 422), ({"min_price": 20, "max_price": 10}, 400)])
def test_invalid_filters_are_rejected(catalog, query, code):
    client, _, _, _ = catalog
    assert client.get("/admin/products", params=query).status_code == code


def test_postgres_list_and_count_share_filters_and_page_is_loaded_in_batches():
    session = RecordingSession()
    repository = ProductRepository(session)
    filters = {"keyword": "SKU_1", "min_price": Decimal("10"), "max_price": Decimal("20"),
               "stock": "low_stock", "category_ids": [uuid.uuid4()], "brand_id": uuid.uuid4(),
               "status": "Active", "include_deleted": False}
    repository.list_admin_catalog(**filters, offset=8, limit=8)
    repository.count_admin_catalog(**filters)
    listing, count = session.statements
    def literal_sql(statement):
        return " ".join(str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).split())
    list_where = literal_sql(listing).split(" WHERE ", 1)[1].split(" ORDER BY ", 1)[0]
    count_where = literal_sql(count).split(" WHERE ", 1)[1]
    assert list_where == count_where
    assert '"ProductVariants"."IsDeleted" IS false' in list_where
    assert 'sum("ProductVariants"."StockQuantity")' in list_where
    assert 'min("ProductVariants"."Price")' in list_where
    assert '"Products"."IsDeleted" IS false' in list_where
    assert 'LIMIT 8 OFFSET 8' in literal_sql(listing)
    assert len(listing._with_options) == 4  # category/brand joins; variants/images select-in loading
