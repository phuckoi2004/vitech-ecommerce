"""Product / variant workflows on isolated SQLite, including customer details and cart."""

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select, func

from app.models import Product, ProductVariant, ProductImage, User
from app.repositories.catalog import ProductImageRepository
from app.schemas import CartItemCreate
from app.services import Actor, ProductService
from app.services.wishlist_cart import CartService
from tests.test_admin_product_list import catalog  # noqa: F401


def shared_payload(product, **changes):
    return {"Name": product.Name, "CategoryId": str(product.CategoryId), "BrandId": str(product.BrandId),
            "WarrantyMonths": 12, "Status": "Active", "Description": None, "Specifications": None, "Images": [], **changes}


def variant_payload(**changes):
    return {"Sku": "MY-WHITE", "Color": "Trắng", "Storage": "256GB", "Price": "1234567.89",
            "MinStockLevel": 4, "IsSerialTracked": False, "IsActive": True, **changes}


def selected(session, product):
    return session.scalar(select(ProductVariant).where(ProductVariant.ProductId == product.ProductId))


def test_new_product_always_has_its_first_variant_and_one_customer_entry(catalog):
    client, session, products, _ = catalog
    before = session.scalar(select(func.count()).select_from(Product))
    response = client.post("/admin/catalog-items", json={**variant_payload(),
        "Product": shared_payload(products[0], Name="Mẫu mới", Images=[{"ImageUrl": "https://example.com/white.png"}])})
    assert response.status_code == 201, response.text
    first = response.json()
    assert first["StockQuantity"] == 0 and first["Color"] == "Trắng"
    assert first["Images"][0]["IsDefault"] is True
    assert Decimal(first["Price"]) == Decimal("1234567.89")
    product_id = first["ProductId"]
    service = ProductService(session)
    detail = service.get_product_detail(uuid.UUID(product_id))
    assert len(detail.Variants) == 1 and detail.Variants[0].Sku == "MY-WHITE"
    for color, sku in (("Đen", "MY-BLACK"), ("Hồng", "MY-PINK")):
        response = client.post("/admin/catalog-items", json={**variant_payload(Sku=sku, Color=color), "ProductId": product_id})
        assert response.status_code == 201, response.text
        assert response.json()["ProductId"] == product_id
    assert session.scalar(select(func.count()).select_from(Product)) == before + 1
    assert service.search_products(keyword="Mẫu mới").Total == 1
    detail = service.get_product_detail(uuid.UUID(product_id))
    assert {variant.Sku for variant in detail.Variants} == {"MY-WHITE", "MY-BLACK", "MY-PINK"}
    assert client.get("/admin/variants", params={"keyword": "MY-"}).json()["Total"] == 3


def test_existing_product_without_variants_can_receive_its_first_variant(catalog):
    client, session, products, _ = catalog
    bare = Product(CategoryId=products[0].CategoryId, BrandId=products[0].BrandId, Name="Một màu",
                   Slug="mot-mau", WarrantyMonths=12, Status="Active")
    session.add(bare); session.commit()
    response = client.post("/admin/catalog-items", json={**variant_payload(), "ProductId": str(bare.ProductId)})
    assert response.status_code == 201, response.text
    assert response.json()["ProductId"] == str(bare.ProductId)
    assert len(ProductService(session).get_product_detail(bare.ProductId).Variants) == 1


def test_variant_edit_never_changes_parent_or_sibling_or_shared_images(catalog):
    client, session, products, _ = catalog
    product = products[2]
    variant = selected(session, product)
    sibling = ProductVariant(ProductId=product.ProductId, VariantName="Đen", Color="Đen", Sku="BLACK", Price=500, StockQuantity=7)
    image = ProductImage(ProductId=product.ProductId, ImageUrl="https://example.com/shared.png", IsDefault=True)
    session.add_all([sibling, image]); session.commit()
    original_id = product.ProductId
    product_count = session.scalar(select(func.count()).select_from(Product))
    response = client.put(f"/admin/catalog-items/{variant.ProductVariantId}", json=variant_payload(Color="Hồng", Price="999", IsActive=False))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ProductId"] == str(original_id) and data["StockQuantity"] == 2
    assert data["Color"] == "Hồng" and not data["IsActive"]
    assert data["Name"] == "Máy 2" and data["ThumbnailUrl"] == image.ImageUrl
    assert session.scalar(select(func.count()).select_from(Product)) == product_count
    other = client.get(f"/admin/catalog-items/{sibling.ProductVariantId}").json()
    assert other["ProductId"] == str(original_id) and other["Color"] == "Đen"
    assert Decimal(other["Price"]) == 500 and other["StockQuantity"] == 7 and other["IsActive"]
    visible = ProductService(session).get_product_detail(original_id).Variants
    assert [item.Sku for item in visible] == ["BLACK"]


def test_shared_edit_updates_same_parent_for_every_variant_preserving_ids_and_stock(catalog):
    client, session, products, _ = catalog
    product = products[2]
    variant = selected(session, product)
    sibling = ProductVariant(ProductId=product.ProductId, VariantName="Đen", Sku="BLACK", Price=500, StockQuantity=7)
    session.add(sibling); session.commit()
    ids = [variant.ProductVariantId, sibling.ProductVariantId]
    response = client.put(f"/admin/catalog-products/{product.ProductId}", json=shared_payload(product,
        Name="Tên chung mới", Description="Dùng chung", Specifications={"RAM": "16GB"},
        Images=[{"ImageUrl": "https://example.com/new.png"}]))
    assert response.status_code == 200, response.text
    for variant_id, stock in zip(ids, [2, 7]):
        row = client.get(f"/admin/catalog-items/{variant_id}").json()
        assert row["Name"] == "Tên chung mới" and row["Description"] == "Dùng chung"
        assert row["ProductId"] == str(product.ProductId) and row["StockQuantity"] == stock
        assert row["ThumbnailUrl"] == "https://example.com/new.png"
    assert ProductService(session).search_products(keyword="Tên chung mới").Total == 1
    assert len(ProductService(session).get_product_detail(product.ProductId).Variants) == 2


def test_cart_splits_different_variants_and_accumulates_same_variant(catalog):
    client, session, products, _ = catalog
    product = products[2]
    first = selected(session, product)
    first.StockQuantity = 10
    second = ProductVariant(ProductId=product.ProductId, Sku="SAME-MODEL-BLACK", VariantName="Đen", Color="Đen", Price=500, StockQuantity=10)
    user = User(Email="cart@example.test", PhoneNumber="0901234567", PasswordHash="unused-test-only",
                FullName="Customer", Role="Customer", AccountStatus="Active")
    session.add_all([second, user]); session.commit()
    service = CartService(session)
    actor = Actor(user.UserId, "Customer")
    service.add_item(actor, CartItemCreate(ProductVariantId=first.ProductVariantId, Quantity=1))
    service.add_item(actor, CartItemCreate(ProductVariantId=second.ProductVariantId, Quantity=1))
    summary = service.add_item(actor, CartItemCreate(ProductVariantId=first.ProductVariantId, Quantity=2))
    assert len(summary.Items) == 2
    rows = {item.ProductVariantId: item for item in summary.Items}
    assert rows[first.ProductVariantId].Quantity == 3
    assert rows[second.ProductVariantId].Quantity == 1
    assert {item.ProductId for item in summary.Items} == {product.ProductId}
    # Admin edits SKU/price while that cart exists; grouping and CartItem IDs remain stable.
    cart_ids = {item.CartItemId for item in summary.Items}
    response = client.put(f"/admin/catalog-items/{first.ProductVariantId}", json=variant_payload(Sku=first.Sku))
    assert response.status_code == 200, response.text
    after = service.get_cart(actor)
    assert {item.CartItemId for item in after.Items} == cart_ids
    assert {item.ProductId for item in after.Items} == {product.ProductId}


@pytest.mark.parametrize("existing", [False, True])
def test_duplicate_sku_rolls_back_without_leaving_new_parent_or_images(catalog, existing):
    client, session, products, _ = catalog
    counts = [session.scalar(select(func.count()).select_from(model)) for model in (Product, ProductVariant, ProductImage)]
    parent = {"ProductId": str(products[0].ProductId)} if existing else {
        "Product": shared_payload(products[0], Images=[{"ImageUrl": "https://example.com/a.png"}])}
    response = client.post("/admin/catalog-items", json={**variant_payload(Sku="SKU-0"), **parent})
    assert response.status_code == 409, response.text
    assert counts == [session.scalar(select(func.count()).select_from(model)) for model in (Product, ProductVariant, ProductImage)]


def test_failed_variant_edit_preserves_grouping_and_inventory(catalog):
    client, session, products, _ = catalog
    variant = selected(session, products[2])
    original_id, original_sku = variant.ProductId, variant.Sku
    response = client.put(f"/admin/catalog-items/{variant.ProductVariantId}", json=variant_payload(Sku="SKU-0"))
    assert response.status_code == 409, response.text
    assert variant.ProductId == original_id and variant.Sku == original_sku and variant.StockQuantity == 2
    response = client.put(f"/admin/catalog-items/{variant.ProductVariantId}", json=variant_payload(IsSerialTracked=True))
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "serial_tracking_change_requires_zero_stock"
    assert variant.ProductId == original_id and not variant.IsSerialTracked


def test_shared_image_failure_rolls_back_metadata_and_images(catalog):
    client, session, products, _ = catalog
    product = products[2]
    original_name = product.Name
    body = shared_payload(product, Name="Không được lưu", Images=[{"ImageUrl": "https://example.com/a.png"}])
    with patch.object(ProductImageRepository, "create", side_effect=RuntimeError("image row failure")):
        with pytest.raises(RuntimeError, match="image row failure"):
            client.put(f"/admin/catalog-products/{product.ProductId}", json=body)
    assert product.Name == original_name
    assert client.get(f"/admin/products/{product.ProductId}").json()["Images"] == []


@pytest.mark.parametrize("invalid", [{"Color": " "}, {"Color": ["Trắng", "Đen"]}, {"Sku": " "},
    {"StockQuantity": 99}, {"CostPrice": "1"}, {"Price": "-1"}, {"Name": "Not shared metadata"}])
def test_variant_form_rejects_invalid_or_shared_fields(catalog, invalid):
    client, _, products, _ = catalog
    response = client.post("/admin/catalog-items", json={**variant_payload(**invalid), "ProductId": str(products[0].ProductId)})
    assert response.status_code == 422, response.text


def test_parent_selection_is_explicit_and_update_cannot_reparent(catalog):
    client, session, products, _ = catalog
    assert client.post("/admin/catalog-items", json=variant_payload()).status_code == 422
    assert client.post("/admin/catalog-items", json={**variant_payload(), "ProductId": str(products[0].ProductId),
        "Product": shared_payload(products[0])}).status_code == 422
    assert client.post("/admin/catalog-items", json={**variant_payload(), "ProductId": str(uuid.uuid4())}).status_code == 404
    variant = selected(session, products[2])
    assert client.put(f"/admin/catalog-items/{variant.ProductVariantId}", json={
        **variant_payload(), "ProductId": str(products[0].ProductId)}).status_code == 422
    assert variant.ProductId == products[2].ProductId


def test_shared_status_hides_whole_product_but_keeps_each_variant(catalog):
    client, session, products, _ = catalog
    product = products[2]
    variant = selected(session, product)
    result = client.put(f"/admin/catalog-products/{product.ProductId}", json=shared_payload(product, Status="Inactive"))
    assert result.status_code == 200, result.text
    assert variant.IsActive is True and variant.ProductId == product.ProductId
    assert ProductService(session).search_products(keyword=product.Name).Total == 0
    assert client.get(f"/admin/catalog-items/{variant.ProductVariantId}").json()["Status"] == "Inactive"


def test_internal_read_admin_write_and_deleted_parent_guards(catalog):
    client, session, products, actor = catalog
    variant = selected(session, products[0])
    url = f"/admin/catalog-items/{variant.ProductVariantId}"
    shared_url = f"/admin/catalog-products/{products[0].ProductId}"
    actor["role"] = "Staff"
    assert client.get(url).status_code == 200
    assert client.post("/admin/catalog-items", json={**variant_payload(), "ProductId": str(products[0].ProductId)}).status_code == 403
    assert client.put(url, json=variant_payload()).status_code == 403
    assert client.put(shared_url, json=shared_payload(products[0])).status_code == 403
    actor["role"] = "Customer"
    assert client.get(url).status_code == 403
    actor["role"] = "Admin"
    products[0].IsDeleted = True; session.commit()
    assert client.get(url).status_code == 404
    assert client.put(url, json=variant_payload()).status_code == 404
    assert client.put(shared_url, json=shared_payload(products[0])).status_code == 404
    assert client.post("/admin/catalog-items", json={**variant_payload(), "ProductId": str(products[0].ProductId)}).status_code == 404
