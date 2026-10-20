"""A product list page shows the banners for its own category, judged by where each banner links (isolated SQLite)."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import JSON, MetaData, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import Banner, Brand, Category, Product, User
from app.services.content import ContentService


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def functions(connection, _):
        connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)
        connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat(" "))

    metadata = MetaData()
    for model in (User, Category, Brand, Product, Banner):
        table = model.__table__.to_metadata(metadata)
        if model is Product:
            table.c.Specifications.type = JSON()
    metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_category_pages_get_their_own_banners_first_and_never_another_categorys(session):
    phones = Category(Name="Điện thoại", Slug="dien-thoai")
    laptops = Category(Name="Laptop", Slug="laptop")
    session.add_all([phones, laptops]); session.flush()
    iphone = Category(Name="iPhone 18", Slug="iphone-18", ParentCategoryId=phones.CategoryId)
    gaming = Category(Name="Laptop gaming", Slug="laptop-gaming", ParentCategoryId=laptops.CategoryId)
    session.add_all([iphone, gaming]); session.flush()
    honor = Product(CategoryId=phones.CategoryId, BrandId=uuid.uuid4(), Name="HONOR 600S", Slug="honor-600s", WarrantyMonths=12, Status="Active")
    session.add(honor); session.flush()
    author = uuid.uuid4()
    for order, (title, link) in enumerate([
        ("iPhone 18", "/danh-muc/iphone-18"), ("HONOR", "/san-pham/honor-600s"), ("Điện thoại", "/danh-muc/dien-thoai?brand=x"),
        ("Laptop", "/danh-muc/laptop"), ("Mã giảm giá", "/tin-tuc/san-sale"), ("Không link", None), ("Gaming", "/danh-muc/laptop-gaming"),
    ], start=1):
        session.add(Banner(Title=title, ImageUrl=f"https://cdn.example/{order}.jpg", LinkUrl=link, DisplayOrder=order,
                           IsActive=True, CreatedByUserId=author, CreatedAt=datetime.now(timezone.utc)))
    session.commit()
    content = ContentService(session)

    def titles(category=None):
        return [banner.Title for banner in content.list_display_banners(category_id=category and category.CategoryId)]

    assert titles() == ["iPhone 18", "HONOR", "Điện thoại", "Laptop", "Mã giảm giá", "Không link", "Gaming"]
    # The category itself, then its sub-categories and products, then banners for no category in particular.
    assert titles(phones) == ["Điện thoại", "iPhone 18", "HONOR", "Mã giảm giá", "Không link"]
    # A sub-category also gets its parent's banner, after its own.
    assert titles(iphone) == ["iPhone 18", "Điện thoại", "Mã giảm giá", "Không link"]
    assert titles(laptops) == ["Laptop", "Gaming", "Mã giảm giá", "Không link"]
    assert titles(gaming) == ["Gaming", "Laptop", "Mã giảm giá", "Không link"]
