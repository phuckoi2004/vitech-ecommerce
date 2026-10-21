"""Real variant-list repository/service/routes on isolated SQLite, with PostgreSQL SQL checks.

These tests never connect to the application's database. Multiple variants on one product are
intentional: the admin table must paginate SKUs and retain each variant's own price and stock.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql

from app.models import Brand, Category, Product, ProductImage, ProductVariant
from app.repositories.catalog import ProductVariantRepository
from tests.test_admin_product_list import catalog  # noqa: F401 -- shared isolated SQLite fixture
from tests.test_query_shapes import RecordingSession


def add_variant(session, product, *, sku="PHONE-WHITE-256", name="White 256GB", price=9000000,
                stock=7, **values):
    variant = ProductVariant(ProductId=product.ProductId, Sku=sku, VariantName=name,
                             Price=Decimal(price), StockQuantity=stock, MinStockLevel=3, **values)
    session.add(variant)
    session.commit()
    return variant


def test_one_row_per_sku_keeps_price_stock_and_parent_information(catalog):
    client, session, products, _ = catalog
    product = products[2]
    extra = add_variant(session, product)
    session.add_all([
        ProductImage(ProductId=product.ProductId, ImageUrl="https://example.com/other.png", DisplayOrder=0),
        ProductImage(ProductId=product.ProductId, ImageUrl="https://example.com/default.png",
                     DisplayOrder=5, IsDefault=True),
    ])
    session.commit()
    data = client.get("/admin/variants", params={"keyword": product.Name}).json()
    assert data["Total"] == 2
    rows = {row["Sku"]: row for row in data["Items"]}
    assert set(rows) == {"SKU-2", "PHONE-WHITE-256"}
    assert Decimal(rows["SKU-2"]["Price"]) == 3000000
    assert rows["SKU-2"]["StockQuantity"] == 2
    assert rows["SKU-2"]["IsLowStock"] is True
    assert Decimal(rows[extra.Sku]["Price"]) == 9000000
    assert rows[extra.Sku]["StockQuantity"] == 7
    assert rows[extra.Sku]["IsLowStock"] is False
    assert rows[extra.Sku]["ProductVariantId"] == str(extra.ProductVariantId)
    assert len({row["ProductVariantId"] for row in data["Items"]}) == 2
    for row in rows.values():
        assert row["ProductId"] == str(product.ProductId)
        assert row["Name"] == product.Name
        assert row["Category"]["CategoryId"] == str(product.CategoryId)
        assert row["Brand"]["BrandId"] == str(product.BrandId)
        assert row["ThumbnailUrl"] == "https://example.com/default.png"
        assert "Skus" not in row and "MinPrice" not in row and "MaxPrice" not in row


def test_filters_and_total_apply_to_variants_before_pagination(catalog):
    client, session, products, _ = catalog
    for i in range(4):
        add_variant(session, products[2], sku=f"SIBLING-{i}", name=f"Sibling {i}",
                    price=2000000 + i * 1000000, stock=4)
    filters = {"min_price": 2000000, "max_price": 5000000, "stock": "in_stock", "page_size": 3}
    first = client.get("/admin/variants", params=filters).json()
    second = client.get("/admin/variants", params={**filters, "page": 2}).json()
    third = client.get("/admin/variants", params={**filters, "page": 3}).json()
    assert first["Total"] == second["Total"] == third["Total"] == 8
    assert [len(page["Items"]) for page in (first, second, third)] == [3, 3, 2]
    rows = [row for page in (first, second, third) for row in page["Items"]]
    assert len({row["ProductVariantId"] for row in rows}) == 8
    assert len({row["ProductId"] for row in rows}) == 4
    assert all(2000000 <= Decimal(row["Price"]) <= 5000000 for row in rows)
    assert all(row["StockQuantity"] > 0 for row in rows)
    assert client.get("/admin/variants", params={**filters, "page": 4}).json()["Items"] == []


def test_search_matches_sku_name_and_variant_name_without_returning_siblings(catalog):
    client, session, products, _ = catalog
    product = products[2]
    extra = add_variant(session, product, sku="USER-SET-256", name="Unique Sapphire 256GB")
    for term in ("USER-SET-256", "user-set", "Sapphire", "sapphire 256"):
        data = client.get("/admin/variants", params={"keyword": term}).json()
        assert data["Total"] == 1
        assert data["Items"][0]["ProductVariantId"] == str(extra.ProductVariantId)
    assert client.get("/admin/variants", params={"keyword": product.Name}).json()["Total"] == 2
    assert client.get("/admin/variants", params={"keyword": "SKU-2"}).json()["Total"] == 1
    assert client.get("/admin/variants", params={"keyword": "   "}).json()["Total"] == 13
    extra.VariantName = r"Literal 50%_x\shade"
    session.commit()
    for literal in ("%_", r"\shade"):
        assert client.get("/admin/variants", params={"keyword": literal}).json()["Total"] == 1


def test_deleted_variants_deleted_parents_and_bare_products_are_hidden(catalog):
    client, session, products, _ = catalog
    add_variant(session, products[1], sku="DELETED-SKU", IsDeleted=True)
    add_variant(session, products[2], sku="DELETED-PARENT-SKU")
    products[2].IsDeleted = True
    session.add(Product(CategoryId=products[0].CategoryId, BrandId=products[0].BrandId,
                        Name="Bare product", Slug="bare-product", Status="Draft", WarrantyMonths=0))
    session.commit()
    data = client.get("/admin/variants").json()
    assert data["Total"] == 11
    assert "DELETED-SKU" not in {row["Sku"] for row in data["Items"]}
    assert str(products[2].ProductId) not in {row["ProductId"] for row in data["Items"]}
    assert all(row["Name"] != "Bare product" for row in data["Items"])
    assert client.get("/admin/variants", params={"keyword": "DELETED"}).json()["Total"] == 0


def test_inactive_variants_are_visible_and_status_filters_combine_parent_and_variant(catalog):
    client, session, products, _ = catalog
    inactive = add_variant(session, products[0], sku="HIDDEN-FROM-SALE", IsActive=False)
    products[1].Status = "Inactive"
    products[2].Status = "Draft"
    products[3].Status = "Discontinued"
    session.commit()
    unfiltered = client.get("/admin/variants").json()
    assert unfiltered["Total"] == 13
    assert next(row for row in unfiltered["Items"] if row["Sku"] == inactive.Sku)["IsActive"] is False
    active = client.get("/admin/variants", params={"status": "Active"}).json()
    assert active["Total"] == 9
    assert all(row["Status"] == "Active" and row["IsActive"] for row in active["Items"])
    inactive_rows = client.get("/admin/variants", params={"status": "Inactive"}).json()
    assert inactive_rows["Total"] == 2
    assert {row["Sku"] for row in inactive_rows["Items"]} == {inactive.Sku, "SKU-1"}
    for status, sku in (("Draft", "SKU-2"), ("Discontinued", "SKU-3")):
        data = client.get("/admin/variants", params={"status": status}).json()
        assert data["Total"] == 1 and data["Items"][0]["Sku"] == sku


def test_stock_filter_uses_each_variants_stock_and_threshold(catalog):
    client, session, products, _ = catalog
    add_variant(session, products[1], sku="EMPTY-SIBLING", stock=0)
    add_variant(session, products[1], sku="NO-THRESHOLD", stock=1).MinStockLevel = 0
    session.commit()
    low = client.get("/admin/variants", params={"stock": "low_stock"}).json()
    assert low["Total"] == 3
    assert {row["Sku"] for row in low["Items"]} == {"SKU-1", "SKU-2", "SKU-3"}
    out = client.get("/admin/variants", params={"stock": "out_of_stock"}).json()
    assert out["Total"] == 2
    assert {row["Sku"] for row in out["Items"]} == {"SKU-0", "EMPTY-SIBLING"}
    assert all(row["StockQuantity"] == 0 and not row["IsLowStock"] for row in out["Items"])


def test_dashboard_stock_links_share_the_active_product_list_scope(catalog):
    client, session, products, _ = catalog
    add_variant(session, products[1], sku="EMPTY-ACTIVE", stock=0)
    add_variant(session, products[1], sku="HIDDEN-EMPTY", stock=0, IsActive=False)
    add_variant(session, products[1], sku="DELETED-EMPTY", stock=0, IsDeleted=True)
    hidden_parent = add_variant(session, products[0], sku="PARENT-DELETED", stock=0)
    products[0].IsDeleted = True
    session.commit()
    def read(stock):
        response = client.get("/admin/variants", params={"status": "Active", "stock": stock})
        assert response.status_code == 200
        return response.json()
    low, empty = read('low_stock'), read('out_of_stock')
    assert 'EMPTY-ACTIVE' in {row['Sku'] for row in empty['Items']}
    assert all(row['StockQuantity'] > 0 and row['IsLowStock'] for row in low['Items'])
    assert all(row['StockQuantity'] == 0 for row in empty['Items'])
    assert not {'HIDDEN-EMPTY', 'DELETED-EMPTY', hidden_parent.Sku} & {row['Sku'] for row in low['Items'] + empty['Items']}


def test_category_and_brand_filters_do_not_include_unrelated_variants(catalog):
    client, session, products, _ = catalog
    category = Category(Name="Other", Slug="other")
    brand = Brand(Name="Other", Slug="other")
    session.add_all([category, brand]); session.flush()
    product = Product(CategoryId=category.CategoryId, BrandId=brand.BrandId,
                      Name="Other product", Slug="other-product", Status="Active", WarrantyMonths=0)
    session.add(product); session.flush()
    add_variant(session, product, sku="OTHER-BLACK")
    add_variant(session, product, sku="OTHER-WHITE")
    for filters in ({"category_id": str(category.CategoryId)}, {"brand_id": str(brand.BrandId)}):
        data = client.get("/admin/variants", params=filters).json()
        assert data["Total"] == 2
        assert {row["Sku"] for row in data["Items"]} == {"OTHER-BLACK", "OTHER-WHITE"}
    assert client.get("/admin/variants", params={"category_id": str(category.CategoryId),
                                               "brand_id": str(products[0].BrandId)}).json()["Total"] == 0


def test_read_roles_and_variant_write_roles_are_enforced(catalog):
    client, session, products, actor = catalog
    variant = session.query(ProductVariant).filter_by(ProductId=products[0].ProductId).one()
    actor["role"] = "Staff"
    assert client.get("/admin/variants").status_code == 200
    assert client.patch(f"/admin/variants/{variant.ProductVariantId}", json={"Sku": "NO"}).status_code == 403
    assert client.delete(f"/admin/variants/{variant.ProductVariantId}").status_code == 403
    actor["role"] = "Customer"
    assert client.get("/admin/variants").status_code == 403
    actor["role"] = "Admin"
    assert client.get("/admin/variants").status_code == 200


def test_variant_edit_and_delete_leave_sibling_and_parent_unchanged(catalog):
    client, session, products, _ = catalog
    parent = products[2]
    sibling = session.query(ProductVariant).filter_by(ProductId=parent.ProductId).one()
    target = add_variant(session, parent)
    response = client.patch(f"/admin/variants/{target.ProductVariantId}",
                            json={"Sku": "EDITED-BY-USER", "Price": "1234567.00", "IsActive": False})
    assert response.status_code == 200, response.text
    edited = response.json()
    assert edited["Sku"] == "EDITED-BY-USER"
    assert Decimal(edited["Price"]) == Decimal("1234567")
    assert edited["StockQuantity"] == 7 and edited["IsActive"] is False
    session.refresh(sibling); session.refresh(parent)
    assert sibling.Sku == "SKU-2" and sibling.Price == 3000000
    assert sibling.StockQuantity == 2 and sibling.IsActive and not sibling.IsDeleted
    assert parent.Status == "Active" and not parent.IsDeleted
    assert client.delete(f"/admin/variants/{target.ProductVariantId}").status_code == 204
    session.refresh(target); session.refresh(sibling); session.refresh(parent)
    assert target.IsDeleted and not sibling.IsDeleted and not parent.IsDeleted
    remaining = client.get("/admin/variants", params={"keyword": parent.Name}).json()
    assert remaining["Total"] == 1 and remaining["Items"][0]["Sku"] == "SKU-2"


def test_new_variant_has_user_sku_and_duplicate_sku_is_rejected(catalog):
    client, session, products, _ = catalog
    payload = {"ProductId": str(products[2].ProductId), "Sku": "USER-BLUE-512",
               "VariantName": "Blue 512GB", "Price": "16000000"}
    created = client.post("/admin/variants", json=payload)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["Sku"] == payload["Sku"] and row["ProductVariantId"] != payload["Sku"]
    assert row["StockQuantity"] == 0
    assert client.post("/admin/variants", json=payload).status_code == 409
    another = session.query(ProductVariant).filter_by(Sku="SKU-2").one()
    duplicate = client.patch(f"/admin/variants/{another.ProductVariantId}", json={"Sku": payload["Sku"]})
    assert duplicate.status_code == 409
    session.refresh(another)
    assert another.Sku == "SKU-2"


@pytest.mark.parametrize("query,code", [({"stock": "invalid"}, 422), ({"status": "invalid"}, 422),
                                       ({"min_price": -1}, 422), ({"page": 0}, 422),
                                       ({"page_size": 101}, 422), ({"min_price": 20, "max_price": 10}, 400)])
def test_invalid_variant_filters_are_rejected(catalog, query, code):
    client, _, _, _ = catalog
    assert client.get("/admin/variants", params=query).status_code == code


def test_variant_page_uses_bounded_queries(catalog):
    client, session, _, _ = catalog
    session.expunge_all()
    statements = []
    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(session.bind, "before_cursor_execute", record)
    try:
        response = client.get("/admin/variants", params={"page_size": 8})
        assert response.status_code == 200, response.text
        assert len(response.json()["Items"]) == 8
        assert len(statements) == 3  # page with parent/category/brand joins, batched images, count
    finally:
        event.remove(session.bind, "before_cursor_execute", record)


def test_postgres_variant_list_and_count_share_filters_and_page_is_variant_based():
    session = RecordingSession()
    repository = ProductVariantRepository(session)
    filters = {"keyword": "SKU_1", "min_price": Decimal("10"), "max_price": Decimal("20"),
               "stock": "low_stock", "category_id": uuid.uuid4(), "brand_id": uuid.uuid4(), "status": "Active"}
    repository.list_catalog(**filters, offset=8, limit=8)
    repository.count_catalog(**filters)
    listing, count = session.statements
    def literal_sql(statement):
        return " ".join(str(statement.compile(dialect=postgresql.dialect(),
                                              compile_kwargs={"literal_binds": True})).split())
    listing_sql, count_sql = literal_sql(listing), literal_sql(count)
    list_where = listing_sql.split(" WHERE ", 1)[1].split(" ORDER BY ", 1)[0]
    assert list_where == count_sql.split(" WHERE ", 1)[1]
    assert '"ProductVariants"."IsDeleted" IS false' in list_where
    assert '"Products"."IsDeleted" IS false' in list_where
    assert '"ProductVariants"."IsActive" IS true' in list_where
    assert '"ProductVariants"."Price" >= 10' in list_where
    assert '"ProductVariants"."StockQuantity" <= "ProductVariants"."MinStockLevel"' in list_where
    assert 'FROM "ProductVariants" JOIN "Products"' in listing_sql
    assert "GROUP BY" not in listing_sql and "sum(" not in listing_sql and "min(" not in listing_sql
    assert 'LIMIT 8 OFFSET 8' in listing_sql
    assert len(listing._with_options) == 3
