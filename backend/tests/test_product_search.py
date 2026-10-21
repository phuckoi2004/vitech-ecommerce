"""Customer keyword search (docs/customer-search.md) through the real router, service and SQL on isolated SQLite."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.search_text import fold, is_marked, words
from app.models import Brand, Category, Product, ProductImage, ProductVariant
from app.routers.catalog import router
from tests.test_admin_product_list import catalog  # noqa: F401


def test_fold_and_words():
    assert fold("  Điện  THOẠI ") == "dien thoai"
    assert fold("Đồng hồ Ưu đãi") == "dong ho uu dai"
    assert words("  iPhone   17  iphone ") == ["iphone", "17"]
    assert is_marked("cơ") and not is_marked("co") and not is_marked("s25")


@pytest.fixture
def shop(catalog):
    client, session, products, _ = catalog
    client.app.include_router(router)
    for product in products:
        product.Status = "Inactive"  # the fixture's "Máy i" products stay out of these searches
    phones = session.get(Category, products[0].CategoryId)  # "Điện thoại"
    flagship = Category(Name="Điện thoại cao cấp", Slug="cao-cap", ParentCategoryId=phones.CategoryId)
    keyboards = Category(Name="Bàn phím", Slug="ban-phim")
    speakers = Category(Name="Loa", Slug="loa")
    samsung, jbl, aula = Brand(Name="SAMSUNG", Slug="samsung"), Brand(Name="JBL", Slug="jbl"), Brand(Name="Aula", Slug="aula")
    session.add_all([flagship, keyboards, speakers, samsung, jbl, aula]); session.flush()
    rows = [
        ("Samsung Galaxy S25 Ultra 12GB 256GB", flagship, samsung),
        ("Điện thoại Samsung Galaxy A57", phones, samsung),
        ("Bàn phím cơ Aula F75", keyboards, aula),
        ("Bàn phím có dây Aula AG60", keyboards, aula),
        ("Loa Bluetooth Charge 5", speakers, jbl),
        ("iPhone 17 Pro 256GB", phones, samsung),
        ("Ốp lưng 100% silicon", phones, samsung),
    ]
    for index, (name, category, brand) in enumerate(rows):
        product = Product(CategoryId=category.CategoryId, BrandId=brand.BrandId, Name=name, Slug=f"tim-{index}",
                          WarrantyMonths=12, Status="Active")
        session.add(product); session.flush()
        session.add(ProductVariant(ProductId=product.ProductId, Sku=f"TIM-{index}", VariantName="Mặc định", Price=1000000))
    session.commit()
    return client


def found(client, keyword, **params):
    response = client.get("/products", params={"keyword": keyword, "page_size": 50, **params})
    assert response.status_code == 200, response.text
    return [row["Name"] for row in response.json()["Items"]]


@pytest.mark.parametrize("keyword, expected", [
    # Words in any order, with or without marks, matched in the name, brand or category (and its parent).
    ("samsung s25", ["Samsung Galaxy S25 Ultra 12GB 256GB"]),
    ("s25 SAMSUNG", ["Samsung Galaxy S25 Ultra 12GB 256GB"]),
    ("dien thoai cao cap", ["Samsung Galaxy S25 Ultra 12GB 256GB"]),
    ("loa jbl", ["Loa Bluetooth Charge 5"]),
    ("  iphone   17  ", ["iPhone 17 Pro 256GB"]),
    ("iphone17", ["iPhone 17 Pro 256GB"]),
    # A word typed with marks keeps them: "cơ" (mechanical) is not "có" (has).
    ("bàn phím cơ", ["Bàn phím cơ Aula F75"]),
    ("ban phim co", ["Bàn phím cơ Aula F75", "Bàn phím có dây Aula AG60"]),
    ("100%", ["Ốp lưng 100% silicon"]),
    ("op lung", ["Ốp lưng 100% silicon"]),
    ("xyz", []),
])
def test_keyword_matches(shop, keyword, expected):
    assert sorted(found(shop, keyword)) == sorted(expected)


def test_relevance_puts_the_phrase_in_the_name_first(shop):
    # Every phone matches "điện thoại" through its category; the one with the phrase in its name comes first.
    names = found(shop, "điện thoại")
    assert names[0] == "Điện thoại Samsung Galaxy A57"
    assert set(names) == {"Điện thoại Samsung Galaxy A57", "Samsung Galaxy S25 Ultra 12GB 256GB", "iPhone 17 Pro 256GB",
                          "Ốp lưng 100% silicon"}
    # An explicit sort still wins over relevance.
    assert found(shop, "samsung", sort="newest")[0] == "Ốp lưng 100% silicon"



def filters(client, **params):
    response = client.get("/products/filters", params=params)
    assert response.status_code == 200, response.text
    data = response.json()
    return ({row["Name"]: row["ProductCount"] for row in data["Categories"]},
            {row["Name"]: row["ProductCount"] for row in data["Brands"]})


def test_search_filters_list_root_categories_and_brands_found_most_first(shop):
    categories, brands = filters(shop)
    assert list(categories.items()) == [("Điện thoại", 4), ("Bàn phím", 2), ("Loa", 1)]  # "cao cấp" rolls up
    assert list(brands.items()) == [("SAMSUNG", 4), ("Aula", 2), ("JBL", 1)]
    assert filters(shop, keyword="ban phim co") == ({"Bàn phím": 2}, {"Aula": 2})
    assert filters(shop, keyword="xyz") == ({}, {})


def test_search_filters_ignore_their_own_choice_so_the_customer_can_switch(shop, catalog):
    session = catalog[1]
    phones = session.scalars(select(Category).where(Category.Slug == "dien-thoai")).one()
    aula = session.scalars(select(Brand).where(Brand.Slug == "aula")).one()
    assert filters(shop, category_id=phones.CategoryId) == ({"Điện thoại": 4, "Bàn phím": 2, "Loa": 1}, {"SAMSUNG": 4})
    assert filters(shop, brand_id=aula.BrandId) == ({"Bàn phím": 2}, {"SAMSUNG": 4, "Aula": 2, "JBL": 1})


def test_search_filters_skip_hidden_categories_and_reject_reversed_prices(shop, catalog):
    session = catalog[1]
    flagship = session.scalars(select(Category).where(Category.Slug == "cao-cap")).one()
    flagship.IsActive = False
    session.commit()
    categories, brands = filters(shop, keyword="samsung")
    assert categories == {"Điện thoại": 3}  # the S25 sits in a hidden child category
    assert brands == {"SAMSUNG": 4}  # ...but the search itself still finds it, as GET /products does
    assert filters(shop, category_id=flagship.CategoryId)[1] == {}
    assert shop.get("/products/filters", params={"min_price": 20, "max_price": 10}).status_code == 400


def test_suggestions_offer_category_pages_and_products_as_their_cards_show_them(shop, catalog):
    session = catalog[1]
    phone = session.scalars(select(Product).where(Product.Name == "Điện thoại Samsung Galaxy A57")).one()
    session.scalars(select(ProductVariant).where(ProductVariant.ProductId == phone.ProductId)).one().CompareAtPrice = 1200000
    session.add(ProductImage(ProductId=phone.ProductId, ImageUrl="https://cdn.example/a57.png", IsDefault=True))
    session.commit()
    samsung = session.scalars(select(Brand).where(Brand.Slug == "samsung")).one()

    data = shop.get("/products/suggestions", params={"keyword": "dien thoai"}).json()
    # The phrase is in the A57's name, so it leads both lists and lends its photo to the category suggestions.
    assert data["Searches"] == [
        {"Label": "Điện thoại", "CategorySlug": "dien-thoai", "BrandId": None, "ImageUrl": "https://cdn.example/a57.png"},
        {"Label": "Điện thoại SAMSUNG", "CategorySlug": "dien-thoai", "BrandId": str(samsung.BrandId),
         "ImageUrl": "https://cdn.example/a57.png"},
    ]
    first, *others = data["Products"]
    assert (first["Name"], first["Slug"], first["ImageUrl"]) == ("Điện thoại Samsung Galaxy A57", "tim-1", "https://cdn.example/a57.png")
    # Without a promotion the stored list price is not struck through, on the card or here.
    assert Decimal(first["Price"]) == 1000000 and first["OriginalPrice"] is None
    assert len(others) == 3 and all(Decimal(row["Price"]) == 1000000 and row["OriginalPrice"] is None for row in others)


@pytest.mark.parametrize("keyword, searches", [
    ("samsung", ["Điện thoại SAMSUNG"]),  # a brand alone: no bare category
    ("dien thoai cao cap", ["Điện thoại cao cấp", "Điện thoại", "Điện thoại SAMSUNG"]),  # the sub-category first
    ("bàn phím cơ", ["Bàn phím", "Bàn phím Aula"]),
    ("loa", ["Loa", "Loa JBL"]),
    ("xyz", []),
    ("   ", []),
])
def test_suggested_searches(shop, keyword, searches):
    response = shop.get("/products/suggestions", params={"keyword": keyword})
    assert response.status_code == 200, response.text
    assert [row["Label"] for row in response.json()["Searches"]] == searches
