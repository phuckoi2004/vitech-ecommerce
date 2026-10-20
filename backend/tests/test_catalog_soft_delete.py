"""Exercise real catalog repositories: hidden rows remain internal; deleted rows have no direct access."""
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Brand, Category
from app.schemas import BrandUpdate, CategoryUpdate
from app.services import Actor, NotFoundError, PermissionDeniedError
from app.services.catalog import BrandService, CategoryService


@pytest.fixture
def catalog():
    engine = create_engine("sqlite://")
    for model in (Category, Brand):
        model.__table__.create(engine)
    with Session(engine) as session:
        rows = []
        for model, pk in ((Category, "CategoryId"), (Brand, "BrandId")):
            row = model(**{pk: uuid.uuid4(), "Name": "Existing", "Slug": "existing", "IsActive": True})
            session.add(row)
            rows.append(row)
        session.commit()
        yield session, rows
    engine.dispose()


@pytest.mark.parametrize("index,service_cls,model,pk,update", [
    (0, CategoryService, Category, "CategoryId", CategoryUpdate),
    (1, BrandService, Brand, "BrandId", BrandUpdate),
])
def test_hide_and_delete_have_different_visibility(catalog, index, service_cls, model, pk, update):
    session, rows = catalog
    service = service_cls(session)
    row = rows[index]
    row_id = getattr(row, pk)
    kind = "category" if index == 0 else "brand"
    plural = "categories" if index == 0 else "brands"
    admin, staff = Actor(uuid.uuid4(), "Admin"), Actor(uuid.uuid4(), "Staff")
    getattr(service, "update_" + kind)(admin, row_id, update(IsActive=False))
    assert len(getattr(service, "list_" + plural)(actor=staff)) == 1
    assert getattr(service, "list_" + plural)(active_only=True) == []
    with pytest.raises(PermissionDeniedError):
        getattr(service, "delete_" + kind)(staff, row_id)
    getattr(service, "delete_" + kind)(admin, row_id)
    assert session.scalar(select(model).where(getattr(model, pk) == row_id)).IsDeleted
    for actor in (admin, staff):
        assert getattr(service, "list_" + plural)(actor=actor) == []
        with pytest.raises(NotFoundError):
            getattr(service, "get_" + kind)(row_id, actor=actor)
        with pytest.raises(NotFoundError):
            getattr(service, "get_" + kind + "_by_slug")("existing", actor=actor)
    with pytest.raises(NotFoundError):
        getattr(service, "update_" + kind)(admin, row_id, update(IsActive=True))
    assert getattr(service, "list_" + plural)(active_only=True) == []


def test_deleted_category_prunes_public_tree_but_retains_children(catalog):
    session, (root, _) = catalog
    child = Category(CategoryId=uuid.uuid4(), Name="child", Slug="child", ParentCategoryId=root.CategoryId)
    session.add(child)
    session.commit()
    service = CategoryService(session)
    service.delete_category(Actor(uuid.uuid4(), "Admin"), root.CategoryId)
    assert service.categories.visible_tree_ids(root.CategoryId) == []
    assert session.get(Category, child.CategoryId).ParentCategoryId == root.CategoryId
    service.update_category(Actor(uuid.uuid4(), "Admin"), child.CategoryId,
                            CategoryUpdate(Name="child renamed", ParentCategoryId=root.CategoryId))
    assert child.Name == "child renamed"
