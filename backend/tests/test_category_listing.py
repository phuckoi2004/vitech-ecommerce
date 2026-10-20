"""Category listing (docs/customer-category-listing.md): specification criteria, sorts and listing filters.

Rules run on free-text specifications, so the unit tests use values copied from the sample catalog. The API tests
run the real router, service and SQL on the isolated SQLite catalog of test_admin_product_list.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.catalog_facets import KEYBOARDS, LAPTOPS, MICE, PHONES, POWER_BANKS, ProductFacts, facet_group
from app.models import Brand, Category, ProductVariant
from app.routers.catalog import router
from tests.test_admin_product_list import catalog  # noqa: F401


def matching(group, key, name, specs, storages=()):
    facts = ProductFacts.of(name, specs, storages)
    return [option.value for option in group.facet(key).options if option.matches(facts)]


# ------------------------------------------------------------------ rules


def test_phone_chip_os_and_network_read_the_written_specifications():
    assert matching(PHONES, "chip", "iPhone 17 Pro", {"Chipset": "Chip A19 Pro"}) == ["apple-a"]
    assert matching(PHONES, "chip", "Nubia Neo 5", {"Chipset": "MediaTek D7400"}) == ["dimensity"]
    assert matching(PHONES, "chip", "Galaxy", {"Chipset": "Snapdragon® 8 Elite Gen 5"}) == ["snapdragon"]
    # No OS written: a Snapdragon phone is still an Android phone; an iPhone is recognised by its name.
    assert matching(PHONES, "os", "Samsung Galaxy S25 Plus", {"Chipset": "Snapdragon 8 Elite"}) == ["android"]
    assert matching(PHONES, "os", "iPhone 17 256GB", {"Chipset": "Apple A19"}) == ["ios"]
    assert matching(PHONES, "network", "Galaxy A57 5G", {"Hỗ trợ mạng": "4G"}) == ["5g"]
    assert matching(PHONES, "network", "Redmi", {"Hỗ trợ mạng": "4G"}) == ["4g"]
    assert matching(PHONES, "nfc", "Itel P55 Plus NFC", {}) == ["yes"]
    assert matching(PHONES, "nfc", "Máy", {"Công nghệ NFC": "Không"}) == ["no"]


def test_memory_sizes_use_variant_storage_and_terabytes():
    assert matching(PHONES, "ram", "Máy", {"Dung lượng RAM": "12 GB"}) == ["12gb", "from-12gb"]
    assert matching(PHONES, "ram", "Máy", {"Dung lượng RAM": "2GB"}) == ["under-3gb"]
    # Each visible variant's storage counts; the specification is only the fallback.
    assert matching(PHONES, "storage", "Máy", {"Bộ nhớ trong": "128 GB"}, ["256 GB", "1 TB"]) == ["256gb", "1tb"]
    assert matching(PHONES, "storage", "Máy", {"Bộ nhớ trong": "128 GB"}) == ["128gb"]
    assert matching(LAPTOPS, "storage", "Laptop", {"Ổ cứng": "512GB SSD M.2 PCIe (Nâng cấp tối đa 2TB)"}) == ["512gb"]


def test_refresh_rate_ignores_touch_sampling():
    specs = {"Tính năng màn hình": "Cảm ứng 240Hz, 100% DCI-P3, Độ sáng tối đa 1200 nits"}
    assert matching(PHONES, "refresh-rate", "OPPO Reno15", specs) == []
    specs = {"Tính năng màn hình": "Tần số quét 144 Hz; Tần số cảm ứng tức thì 3049 Hz"}
    assert matching(PHONES, "refresh-rate", "Nubia", specs) == ["from-144hz"]
    specs = {"Tính năng màn hình": "Công nghệ ProMotion với tốc độ làm mới thích ứng lên đến 120Hz"}
    assert matching(PHONES, "refresh-rate", "iPhone", specs) == ["120hz"]


def test_numbers_with_thousands_separators_and_decimals():
    assert matching(POWER_BANKS, "capacity", "Pin", {"Dung lượng pin": "10.000 mAh"}) == ["10000"]
    assert matching(POWER_BANKS, "capacity", "Pin", {"Dung lượng pin": "60.000 mAh"}) == ["over-20000"]
    assert matching(POWER_BANKS, "power", "Pin", {"Công suất sạc": "Có dây: 20W; Không dây: 15W"}) == ["20-45w"]
    assert matching(MICE, "dpi", "Chuột", {"Độ phân giải": "800/1200/1600/2000/4000 DPI"}) == ["2000-10000"]


def test_wireless_is_not_mistaken_for_wired():
    assert matching(KEYBOARDS, "connection", "Phím", {"Kết nối": "Không dây 2.4GHz"}) == ["wireless"]
    assert matching(KEYBOARDS, "connection", "Phím", {"Kết nối": "Bluetooth; Kết nối có dây qua cổng Type-C"}) == [
        "wired", "bluetooth"]


def test_groups_follow_the_root_category_slug():
    assert facet_group("dien-thoai") is PHONES
    assert facet_group("laptop") is LAPTOPS
    assert facet_group("danh-muc-moi").facets == ()
    assert [price.value for price in facet_group("danh-muc-moi").price_ranges][0] == "under-5"


# ------------------------------------------------------------------ API


@pytest.fixture
def listing(catalog):
    client, session, products, _ = catalog
    client.app.include_router(router)
    return client, session, products


def names(response):
    assert response.status_code == 200, response.text
    return [row["Name"] for row in response.json()["Items"]]


def test_sorts_order_the_whole_result_before_pagination(listing):
    client, session, products = listing
    for index, product in enumerate(products):
        product.SoldQuantity = (index * 7) % 12
        product.ReviewCount = 0
    variant = session.scalar(select(ProductVariant).where(ProductVariant.ProductId == products[0].ProductId))
    variant.CompareAtPrice = Decimal(4000000)  # a list price alone is no discount: only promotions count
    session.commit()
    category_id = products[0].CategoryId

    def first(sort, size=3):
        return names(client.get("/products", params={"category_id": category_id, "sort": sort, "page_size": size}))

    assert first("price_asc") == ["Máy 0", "Máy 1", "Máy 2"]
    assert first("price_desc") == ["Máy 11", "Máy 10", "Máy 9"]
    assert first("discount") == first("newest")
    assert first("best_selling") == [f"Máy {index}" for index in sorted(range(12), key=lambda i: (-((i * 7) % 12), -i))[:3]]
    second_page = names(client.get("/products", params={"sort": "price_asc", "page": 2, "page_size": 5}))
    assert second_page == ["Máy 5", "Máy 6", "Máy 7", "Máy 8", "Máy 9"]
    assert client.get("/products", params={"sort": "cheapest"}).status_code == 422


def test_in_stock_and_new_arrivals(listing):
    client, session, products = listing
    old = datetime.now(timezone.utc) - timedelta(days=45)
    for product in products[:4]:
        product.CreatedAt = old
    session.commit()
    # "Máy 0" has no stock (the fixture gives product i a stock of i).
    assert client.get("/products", params={"in_stock": True}).json()["Total"] == 11
    assert set(names(client.get("/products", params={"new_arrivals": True, "page_size": 20}))) == {
        f"Máy {index}" for index in range(4, 12)}


def test_spec_filters_or_within_a_criterion_and_across_criteria(listing):
    client, session, products = listing
    chips = ["Snapdragon 8 Gen 3", "Apple A18", "Exynos 1480", "Snapdragon 7s Gen 2"]
    rams = ["12 GB", None, "8 GB", "8 GB"]
    for product, chip, ram in zip(products, chips, rams):
        product.Specifications = {"Chipset": chip, **({"Dung lượng RAM": ram} if ram else {})}
    session.commit()
    category_id = products[0].CategoryId

    def search(*specs, **params):
        return client.get("/products", params={"category_id": category_id, "spec": list(specs), "page_size": 20, **params})

    assert set(names(search("chip:snapdragon"))) == {"Máy 0", "Máy 3"}
    assert set(names(search("chip:snapdragon", "chip:exynos"))) == {"Máy 0", "Máy 2", "Máy 3"}
    assert set(names(search("chip:snapdragon", "ram:8gb"))) == {"Máy 3"}
    assert search("chip:snapdragon", "ram:8gb").json()["Total"] == 1
    assert names(search("chip:snapdragon", sort="price_desc")) == ["Máy 3", "Máy 0"]
    assert search("chip:unisoc").json() == {"Items": [], "Total": 0, "Page": 1, "PageSize": 20}
    assert search("chip:nope").status_code == 400
    assert search("nope:snapdragon").json()["code"] == "invalid_filter"
    assert client.get("/products", params={"spec": "chip:snapdragon"}).status_code == 400


def test_filters_list_only_brands_prices_and_options_with_products_on_sale(listing):
    client, session, products = listing
    root = session.get(Category, products[0].CategoryId)
    child = Category(Name="Chơi game", Slug="choi-game", ParentCategoryId=root.CategoryId)
    hidden_child = Category(Name="Ẩn", Slug="an", ParentCategoryId=root.CategoryId, IsActive=False)
    other = Brand(Name="Khác", Slug="khac")
    unused = Brand(Name="Không bán", Slug="khong-ban")
    session.add_all([child, hidden_child, other, unused]); session.flush()
    products[0].CategoryId = child.CategoryId
    products[0].Specifications = {"Chipset": "Snapdragon 8 Gen 3"}
    products[1].Specifications = {"Chipset": "Apple A18"}
    products[1].BrandId = other.BrandId
    products[2].CategoryId = hidden_child.CategoryId
    products[2].Specifications = {"Chipset": "Exynos 1480"}  # in a hidden group: not counted
    products[3].Status = "Inactive"
    products[3].Specifications = {"Chipset": "Unisoc T606"}  # not on sale: not counted
    session.commit()

    data = client.get(f"/categories/{root.CategoryId}/filters").json()
    # Ten products count (Máy 2 is in a hidden group, Máy 3 is not on sale); "Không bán" has none.
    assert [(brand["Name"], brand["ProductCount"]) for brand in data["Brands"]] == [("Hãng", 9), ("Khác", 1)]
    # Máy i sells for i + 1 million.
    assert [(price["Value"], price["ProductCount"]) for price in data["PriceRanges"]] == [
        ("under-2", 1), ("2-4", 1), ("4-7", 2), ("7-13", 6)]
    assert data["PriceRanges"][0] == {"Value": "under-2", "Label": "Dưới 2 triệu", "ProductCount": 1,
                                      "MinPrice": None, "MaxPrice": "1999999.99"}
    chip = next(facet for facet in data["Facets"] if facet["Key"] == "chip")
    assert chip == {"Key": "chip", "Label": "Chip xử lý", "Options": [
        {"Value": "snapdragon", "Label": "Snapdragon", "ProductCount": 1},
        {"Value": "apple-a", "Label": "Apple A", "ProductCount": 1}]}
    assert {facet["Key"] for facet in data["Facets"]} <= {"chip", "os"}

    child_data = client.get(f"/categories/{child.CategoryId}/filters").json()
    assert [facet["Key"] for facet in child_data["Facets"]] == ["chip", "os"]  # the root's criteria
    assert client.get(f"/categories/{hidden_child.CategoryId}/filters").status_code == 404
    assert client.get(f"/categories/{uuid.uuid4()}/filters").status_code == 404
