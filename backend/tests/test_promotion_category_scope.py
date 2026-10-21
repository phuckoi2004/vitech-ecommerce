"""A sub-category created or moved under a promoted category joins that promotion (isolated SQLite)."""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PromotionCategory
from app.schemas.catalog import CategoryCreate, CategoryUpdate
from app.schemas.promotion import PromotionCreate
from app.services.catalog import CategoryService
from app.services.promotion import PromotionService
from tests.test_promotion_lifecycle import shop  # noqa: F401


def test_new_and_moved_sub_categories_join_promotions_aimed_at_their_parent(shop):
    now, actor = shop["now"]["value"], shop["current"]["actor"]
    with Session(shop["engine"]) as session:
        categories = CategoryService(session, clock=lambda: now)
        promotions = PromotionService(session, clock=lambda: now)
        phones = categories.create_category(actor, CategoryCreate(Name="Điện thoại", Slug="dien-thoai"))
        battery = categories.create_category(actor, CategoryCreate(Name="Điện thoại pin trâu", Slug="pin-trau", ParentCategoryId=phones.CategoryId))
        other = categories.create_category(actor, CategoryCreate(Name="Laptop", Slug="laptop"))

        def program(name, category_ids, status="Scheduled"):
            return promotions.create_promotion(actor, PromotionCreate(
                Name=name, Status=status, DiscountType="Percentage", DiscountValue="5", MinOrderValue="0",
                StartDate=now - timedelta(hours=1), EndDate=now + timedelta(days=3), CategoryIds=category_ids)).PromotionId

        whole = program("Cả điện thoại", [phones.CategoryId, battery.CategoryId])
        only_battery = program("Chỉ pin trâu", [battery.CategoryId])
        cancelled = program("Đã hủy", [phones.CategoryId])
        promotions.cancel_promotion(actor, cancelled)

        iphone = categories.create_category(actor, CategoryCreate(Name="iPhone 18", Slug="iphone-18", ParentCategoryId=phones.CategoryId))
        gaming = categories.create_category(actor, CategoryCreate(Name="Laptop gaming", Slug="laptop-gaming", ParentCategoryId=other.CategoryId))
        pro = categories.create_category(actor, CategoryCreate(Name="Gaming Pro", Slug="gaming-pro", ParentCategoryId=gaming.CategoryId))
        categories.update_category(actor, gaming.CategoryId, CategoryUpdate(ParentCategoryId=phones.CategoryId))

        def scope(promotion_id):
            return set(session.scalars(select(PromotionCategory.CategoryId).where(PromotionCategory.PromotionId == promotion_id)))

        assert scope(whole) == {phones.CategoryId, battery.CategoryId, iphone.CategoryId, gaming.CategoryId, pro.CategoryId}
        assert scope(only_battery) == {battery.CategoryId}
        assert scope(cancelled) == {phones.CategoryId}
