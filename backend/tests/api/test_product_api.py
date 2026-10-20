"""API tests — Product catalog: categories, brands, products, variants (Admin manages, Staff reads, public views)."""

from .support import (
    expect,
    expect_forbidden,
    expect_unauthorized,
    expect_validation,
    random_id,
    requires_postgres,
    tag,
)

pytestmark = requires_postgres


def new_catalog(api, admin):
    t = tag()
    client = api.client
    category = expect(client.post("/admin/categories", headers=admin.headers,
                                  json={"Name": f"Điện thoại {t}", "Slug": f"dien-thoai-{t}"}), 201)
    brand = expect(client.post("/admin/brands", headers=admin.headers, json={"Name": f"Hãng {t}", "Slug": f"hang-{t}"}),
                   201)
    product = expect(client.post("/admin/products", headers=admin.headers, json={
        "CategoryId": category["CategoryId"], "BrandId": brand["BrandId"], "Name": f"Máy {t}", "Slug": f"may-{t}",
        "WarrantyMonths": 12, "Status": "Active"}), 201)
    variant = expect(client.post("/admin/variants", headers=admin.headers, json={
        "ProductId": product["ProductId"], "Sku": f"SKU-{t.upper()}", "VariantName": "8GB/256GB",
        "Price": "15990000.00"}), 201)
    return {"category": category, "brand": brand, "product": product, "variant": variant}


def test_success_admin_builds_catalog_and_public_sees_it(api, admin, staff):
    catalog = new_catalog(api, admin)
    product_id = catalog["product"]["ProductId"]
    assert catalog["variant"]["StockQuantity"] == 0  # stock only changes through inventory operations
    public = expect(api.client.get(f"/products/{product_id}"), 200)
    assert public["ProductId"] == product_id
    assert expect(api.client.get(f"/products/slug/{catalog['product']['Slug']}"), 200)["ProductId"] == product_id
    found = expect(api.client.get("/products", params={"keyword": catalog["product"]["Name"]}), 200)
    assert [p["ProductId"] for p in found["Items"]] == [product_id]
    # Staff reads the admin catalog (Stage 4 roles) but does not change it.
    assert expect(api.client.get(f"/admin/products/{product_id}", headers=staff.headers), 200)["ProductId"] == \
        product_id
    renamed = expect(api.client.patch(f"/admin/products/{product_id}", headers=admin.headers,
                                      json={"Name": "Tên mới"}), 200)
    assert renamed["Name"] == "Tên mới"


def test_401_admin_catalog_needs_a_token(api):
    expect_unauthorized(api.client.post("/admin/categories", json={"Name": "A", "Slug": "a"}))
    expect_unauthorized(api.client.get("/admin/products"))
    expect_unauthorized(api.client.delete(f"/admin/variants/{random_id()}"))


def test_403_customer_and_staff_cannot_change_the_catalog(api, staff, customer):
    shop = api.seed.variant()
    expect_forbidden(api.client.get("/admin/products", headers=customer.headers))
    expect_forbidden(api.client.post("/admin/categories", headers=customer.headers, json={"Name": "A", "Slug": "a"}))
    expect_forbidden(api.client.post("/admin/categories", headers=staff.headers, json={"Name": "A", "Slug": "a"}))
    expect_forbidden(api.client.patch(f"/admin/products/{shop['product_id']}", headers=staff.headers,
                                      json={"Name": "Staff đổi tên"}))
    expect_forbidden(api.client.delete(f"/admin/variants/{shop['variant_id']}", headers=staff.headers))


def test_404_unknown_or_hidden_products(api, admin):
    draft = api.seed.variant(status="Draft")
    expect(api.client.get(f"/products/{random_id()}"), 404)
    expect(api.client.get("/products/slug/khong-ton-tai"), 404)
    expect(api.client.get(f"/products/{draft['product_id']}"), 404)  # Draft products are not public
    assert expect(api.client.get(f"/admin/products/{draft['product_id']}", headers=admin.headers), 200)["Status"] == \
        "Draft"
    expect(api.client.patch(f"/admin/products/{random_id()}", headers=admin.headers, json={"Name": "x"}), 404)
    expect(api.client.post("/admin/variants", headers=admin.headers, json={
        "ProductId": random_id(), "Sku": "SKU-NONE", "VariantName": "x", "Price": "1.00"}), 404)


def test_409_duplicate_slug_and_sku(api, admin):
    catalog = new_catalog(api, admin)
    expect(api.client.post("/admin/categories", headers=admin.headers, json={
        "Name": "Trùng", "Slug": catalog["category"]["Slug"]}), 409, "category_slug_exists")
    expect(api.client.post("/admin/brands", headers=admin.headers, json={
        "Name": "Trùng", "Slug": catalog["brand"]["Slug"]}), 409, "brand_slug_exists")
    expect(api.client.post("/admin/variants", headers=admin.headers, json={
        "ProductId": catalog["product"]["ProductId"], "Sku": catalog["variant"]["Sku"], "VariantName": "Khác",
        "Price": "1.00"}), 409, "sku_exists")


def test_422_validation(api, admin):
    shop = api.seed.variant()
    base = {"CategoryId": shop["category_id"], "BrandId": shop["brand_id"], "Name": "Máy", "Slug": f"may-{tag()}",
            "WarrantyMonths": 12, "Status": "Active"}
    expect_validation(api.client.post("/admin/products", headers=admin.headers, json={**base, "Status": "Selling"}),
                      "Status")
    expect_validation(api.client.post("/admin/products", headers=admin.headers, json={**base, "CategoryId": "x"}),
                      "CategoryId")
    expect_validation(api.client.post("/admin/products", headers=admin.headers, json={**base, "StockQuantity": 5}),
                      "StockQuantity")  # unknown fields are rejected, stock is not set here
    expect_validation(api.client.post("/admin/variants", headers=admin.headers, json={
        "ProductId": shop["product_id"], "Sku": "SKU-NEG", "VariantName": "x", "Price": "-1"}), "Price")
    expect_validation(api.client.get("/products", params={"page_size": 101}), "page_size")


def test_business_rules_catalog_integrity(api, admin):
    shop = api.seed.variant(stock=5)
    expect(api.client.delete(f"/admin/categories/{shop['category_id']}", headers=admin.headers), 204)
    expect(api.client.delete(f"/admin/brands/{shop['brand_id']}", headers=admin.headers), 204)
    expect(api.client.get(f"/categories/{shop['category_id']}", headers=admin.headers,
                          params={"active_only": False}), 404)
    expect(api.client.get(f"/brands/{shop['brand_id']}", headers=admin.headers,
                          params={"active_only": False}), 404)
    # Serial tracking can only change while the variant has no stock.
    expect(api.client.patch(f"/admin/variants/{shop['variant_id']}", headers=admin.headers,
                            json={"IsSerialTracked": True}), 400, "serial_tracking_change_requires_zero_stock")
