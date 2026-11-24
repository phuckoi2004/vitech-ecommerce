"""Public card batches use real services/SQL on an isolated database."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import event

from app.models import ProductImage, ProductVariant
from tests.test_public_product_prices import catalog, public_catalog  # noqa: F401


def test_cards_keep_order_deduplicate_and_omit_missing_products(public_catalog):
    client, _, products = public_catalog
    ids = [products[4].ProductId, uuid.uuid4(), products[0].ProductId, products[4].ProductId]
    response = client.get("/products/cards", params=[("product_id", str(key)) for key in ids])
    assert response.status_code == 200, response.text
    rows = response.json()
    assert [row["ProductId"] for row in rows] == [str(ids[0]), str(ids[2])]
    assert Decimal(rows[0]["Variants"][0]["SalePrice"]) == 5000000
    assert rows[0]["Variants"][0]["StockQuantity"] == 4
    assert rows[1]["Variants"][0]["StockQuantity"] == 0
    assert "Description" not in rows[0] and "Specifications" not in rows[0]
    assert "CostPrice" not in rows[0]["Variants"][0]


def test_cards_use_public_visibility_and_default_variant_images(public_catalog):
    client, session, products = public_catalog
    products[1].Status = "Draft"
    products[2].Status = "Inactive"
    products[3].IsDeleted = True
    product = products[0]
    session.add_all([
        ProductVariant(ProductId=product.ProductId, Sku="HIDDEN", VariantName="Hidden", Price=1, IsActive=False),
        ProductVariant(ProductId=product.ProductId, Sku="DELETED", VariantName="Deleted", Price=2, IsDeleted=True),
        ProductImage(ProductId=product.ProductId, ImageUrl="https://example.test/default.png", IsDefault=True),
    ])
    session.commit()
    response = client.get("/products/cards", params=[("product_id", str(p.ProductId)) for p in products[:4]])
    assert response.status_code == 200, response.text
    row, = response.json()
    assert row["ProductId"] == str(product.ProductId)
    variant, = row["Variants"]
    assert Decimal(variant["Price"]) == 1000000
    assert row["DefaultVariantId"] == variant["ProductVariantId"]
    assert row["VariantImages"][row["DefaultVariantId"]][0]["ImageUrl"] == "https://example.test/default.png"


@pytest.mark.parametrize("ids", [[], ["invalid"], [str(uuid.uuid4())] * 51])
def test_cards_validate_ids_and_bound_batch_size(public_catalog, ids):
    client, *_ = public_catalog
    assert client.get("/products/cards", params=[("product_id", key) for key in ids]).status_code == 422


def test_card_query_count_does_not_grow_per_product(public_catalog):
    client, session, products = public_catalog
    ids = [p.ProductId for p in products]
    counts = []
    statements = []

    def record(*args):
        statements.append(args[2])

    event.listen(session.bind, "before_cursor_execute", record)
    try:
        for size in (1, 10):
            session.expire_all()
            statements.clear()
            response = client.get("/products/cards", params=[("product_id", str(key)) for key in ids[:size]])
            assert response.status_code == 200, response.text
            assert len(response.json()) == size
            counts.append(len(statements))
    finally:
        event.remove(session.bind, "before_cursor_execute", record)
    assert counts[0] == counts[1]
    assert counts[1] <= 8
