"""Public price filters through the real API, service and SQL on isolated SQLite."""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models import Brand, Category, ProductVariant
from app.repositories.catalog import ProductRepository
from app.routers.catalog import router
from tests.test_admin_product_list import catalog  # noqa: F401
from tests.test_query_shapes import RecordingSession


@pytest.fixture
def public_catalog(catalog):
    client, session, products, _ = catalog
    client.app.include_router(router)
    return client, session, products


def test_price_filter_precedes_pagination_with_matching_totals(public_catalog):
    client, _, products = public_catalog
    params = {"min_price": 2000000, "max_price": 9000000, "page_size": 3}
    pages = [client.get("/products", params={**params, "page": page}).json() for page in (1, 2, 3)]
    assert [page["Total"] for page in pages] == [8, 8, 8]
    identifiers = [row["ProductId"] for page in pages for row in page["Items"]]
    assert len(identifiers) == len(set(identifiers)) == 8
    assert set(identifiers) == {str(product.ProductId) for product in products[1:9]}
    assert client.get("/products", params={"max_price": "999999.99"}).json()["Total"] == 0
    assert client.get("/products", params={"min_price": "12000000"}).json()["Total"] == 1
    assert client.get("/products").json()["Total"] == 12


def test_adjacent_price_ranges_have_no_overlapping_boundary(public_catalog):
    client, session, products = public_catalog
    for product, price in zip(products[:4], ("4999999.99", "5000000", "9999999.99", "10000000")):
        variant = session.scalar(select(ProductVariant).where(ProductVariant.ProductId == product.ProductId))
        variant.Price = Decimal(price)
    session.commit()
    for params, expected in (
        ({"max_price": "4999999.99"}, products[:1]),
        ({"min_price": "5000000", "max_price": "9999999.99"}, products[1:3] + products[4:9]),
    ):
        data = client.get("/products", params=params).json()
        assert {row["ProductId"] for row in data["Items"]} == {str(product.ProductId) for product in expected}


def test_uses_lowest_visible_variant_price_without_duplicate_products(public_catalog):
    client, session, products = public_catalog
    product = products[1]
    session.add_all([
        ProductVariant(ProductId=product.ProductId, Sku="HIDDEN-CHEAP", VariantName="Hidden", Price=1, IsActive=False),
        ProductVariant(ProductId=product.ProductId, Sku="DELETED-CHEAP", VariantName="Deleted", Price=2, IsDeleted=True),
        ProductVariant(ProductId=product.ProductId, Sku="MORE-EXPENSIVE", VariantName="Extra", Price=50000000),
        ProductVariant(ProductId=product.ProductId, Sku="SAME-PRICE", VariantName="Other", Price=2000000),
    ])
    # An out-of-stock visible variant still contributes to the displayed price.
    for variant in session.scalars(select(ProductVariant).where(ProductVariant.ProductId == product.ProductId)):
        variant.StockQuantity = 0
    for variant in session.scalars(select(ProductVariant).where(ProductVariant.ProductId == products[0].ProductId)):
        variant.IsActive = False
    products[2].Status = "Inactive"
    products[3].IsDeleted = True
    session.commit()
    data = client.get("/products", params={"min_price": 2000000, "max_price": 2000000}).json()
    assert data["Total"] == 1
    assert [row["ProductId"] for row in data["Items"]] == [str(product.ProductId)]
    assert client.get("/products", params={"min_price": 20000000}).json()["Total"] == 0
    assert client.get("/products", params={"max_price": 4000000}).json()["Total"] == 1


def test_combines_category_descendants_brand_keyword_and_price(public_catalog):
    client, session, products = public_catalog
    root_id = products[0].CategoryId
    child = Category(Name="Con", Slug="con", ParentCategoryId=root_id)
    other_brand = Brand(Name="Khác", Slug="khac")
    session.add_all([child, other_brand]); session.flush()
    products[1].CategoryId = child.CategoryId
    products[2].BrandId = other_brand.BrandId
    session.commit()
    params = {"category_id": str(root_id), "include_descendants": True,
              "brand_id": str(products[0].BrandId), "keyword": "Máy", "min_price": 2000000, "max_price": 3000000}
    data = client.get("/products", params=params).json()
    assert data["Total"] == 1 and data["Items"][0]["ProductId"] == str(products[1].ProductId)
    assert client.get("/products", params={**params, "include_descendants": False}).json()["Total"] == 0


@pytest.mark.parametrize("params,status", [
    ({"min_price": -1}, 422), ({"max_price": "abc"}, 422), ({"min_price": "NaN"}, 422),
    ({"min_price": "1.001"}, 422), ({"max_price": "10000000000000"}, 422),
    ({"min_price": 10, "max_price": 1}, 400),
])
def test_invalid_price_ranges_are_rejected(public_catalog, params, status):
    client, *_ = public_catalog
    response = client.get("/products", params=params)
    assert response.status_code == status, response.text
    if status == 400:
        assert response.json()["code"] == "invalid_price_range"


def test_price_query_compiles_for_postgres_using_active_non_deleted_variants():
    session = RecordingSession()
    repo = ProductRepository(session)
    repo.list_products(min_price=Decimal("5000000"), max_price=Decimal("9999999.99"))
    sql = str(session.statements[-1].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert 'min(coalesce(' in sql
    assert '"Promotions"."ApplyMode" = \'Automatic\'' in sql
    assert '"ProductVariants"."CostPrice"' in sql
    assert '"ProductVariants"."IsActive" IS true' in sql
    assert '"ProductVariants"."IsDeleted" IS false' in sql
    assert '>= 5000000' in sql and '<= 9999999.99' in sql
