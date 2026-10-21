"""Homepage captions must come from currently purchasable automatic prices."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import Category, Product, ProductVariant, Promotion
from tests.test_automatic_pricing import pricing_shop, program, coupon  # noqa: F401
from tests.test_promotion_lifecycle import shop, ok  # noqa: F401


def offers(shop):
    return {row["CategoryId"]: row for row in ok(shop["client"].get("/pricing/category-offers"))}


def test_offer_includes_descendants_uses_best_price_and_excludes_coupon(pricing_shop):
    s = pricing_shop
    program(s, amount="1000000")
    program(s)
    coupon(s, amount="3000000")
    with Session(s["engine"]) as session:
        product = session.get(Product, s["variant"].ProductId)
        root_id = product.CategoryId
        child = Category(CategoryId=uuid.uuid4(), ParentCategoryId=root_id,
                         Name="Danh mục con", Slug="offer-child", DisplayOrder=1, IsActive=True)
        session.add(child)
        session.flush()
        product.CategoryId = child.CategoryId
        session.commit()
    row = offers(s)[str(root_id)]
    assert row["AvailableProductCount"] == 1
    assert Decimal(row["MaxDiscountAmount"]) == 2000000
    assert Decimal(row["MaxDiscountPercent"]) == Decimal("5.71")
    assert "CostPrice" not in row and "ProductVariantId" not in row


@pytest.mark.parametrize("unavailable", ["expired", "future", "draft", "cost", "stock", "variant", "product", "category"])
def test_offer_does_not_advertise_unavailable_or_unsafe_discounts(pricing_shop, unavailable):
    s = pricing_shop
    promotion = program(s)
    with Session(s["engine"]) as session:
        variant = session.get(ProductVariant, s["variant"].ProductVariantId)
        product = session.get(Product, variant.ProductId)
        root_id = product.CategoryId
        row = session.get(Promotion, uuid.UUID(promotion["PromotionId"]))
        now = s["now"]["value"]
        if unavailable == "expired":
            row.EndDate = now - timedelta(minutes=1)
        elif unavailable == "future":
            row.StartDate = now + timedelta(minutes=1)
        elif unavailable == "draft":
            row.Status = "Draft"
        elif unavailable == "cost":
            variant.CostPrice = Decimal("34000000")
        elif unavailable == "stock":
            variant.StockQuantity = 0
        elif unavailable == "variant":
            variant.IsActive = False
        elif unavailable == "product":
            product.IsDeleted = True
        else:
            session.get(Category, root_id).IsActive = False
        session.commit()
    data = offers(s)
    if unavailable == "category":
        assert str(root_id) not in data
    else:
        assert Decimal(data[str(root_id)]["MaxDiscountAmount"]) == 0
        assert Decimal(data[str(root_id)]["MaxDiscountPercent"]) == 0


def test_empty_active_category_returns_zero_without_sample_marketing_values(pricing_shop):
    s = pricing_shop
    with Session(s["engine"]) as session:
        root_id = uuid.uuid4()
        session.add(Category(CategoryId=root_id, Name="Chưa có sản phẩm", Slug="empty-offer",
                             DisplayOrder=99, IsActive=True))
        session.commit()
    assert offers(s)[str(root_id)] == dict(CategoryId=str(root_id), AvailableProductCount=0,
                                         MaxDiscountAmount="0.00", MaxDiscountPercent="0.00")
