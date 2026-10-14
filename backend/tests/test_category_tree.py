"""The public category-tree filter uses real recursive SQL without a remote database."""

import uuid
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Category
from app.repositories import CategoryRepository
from app.services.catalog import ProductService


@pytest.fixture
def catalog_tree():
    engine = create_engine("sqlite://")
    Category.__table__.create(engine)
    with Session(engine) as session:
        def category(name, parent=None, active=True):
            row = Category(CategoryId=uuid.uuid4(), Name=name, Slug=name, ParentCategoryId=parent, IsActive=active)
            session.add(row)
            session.flush()
            return row
        root = category("root")
        child = category("child", root.CategoryId)
        grandchild = category("grandchild", child.CategoryId)
        hidden = category("hidden", root.CategoryId, False)
        behind_hidden = category("behind-hidden", hidden.CategoryId)
        other = category("other")
        yield session, root, child, grandchild, hidden, behind_hidden, other
    engine.dispose()


def test_active_tree_contains_descendants_and_prunes_hidden_branches(catalog_tree):
    session, root, child, grandchild, *_ = catalog_tree
    ids = CategoryRepository(session).visible_tree_ids(root.CategoryId)
    assert set(ids) == {root.CategoryId, child.CategoryId, grandchild.CategoryId}


def test_cycle_does_not_repeat_or_hang(catalog_tree):
    session, root, child, grandchild, *_ = catalog_tree
    root.ParentCategoryId = grandchild.CategoryId
    session.flush()
    assert set(CategoryRepository(session).visible_tree_ids(root.CategoryId)) == {
        root.CategoryId, child.CategoryId, grandchild.CategoryId,
    }


def test_missing_or_hidden_root_returns_no_ids(catalog_tree):
    session, _, _, _, hidden, *_ = catalog_tree
    repo = CategoryRepository(session)
    assert repo.visible_tree_ids(hidden.CategoryId) == []
    assert repo.visible_tree_ids(uuid.uuid4()) == []


def test_public_search_uses_identical_tree_for_count_and_pagination(catalog_tree):
    session, root, child, grandchild, *_ = catalog_tree
    service = ProductService(session)
    service.products = Mock()
    service.products.list_products.return_value = []
    service.products.count_products.return_value = 0
    service.search_products(category_id=root.CategoryId, include_descendants=True, page=2, page_size=5)
    listing = service.products.list_products.call_args.kwargs
    counting = service.products.count_products.call_args.kwargs
    assert set(listing["category_ids"]) == {root.CategoryId, child.CategoryId, grandchild.CategoryId}
    assert listing["category_ids"] == counting["category_ids"]
    assert listing["offset"] == 5 and listing["limit"] == 5


def test_missing_tree_does_not_fall_back_to_entire_catalog(catalog_tree):
    session, *_ = catalog_tree
    service = ProductService(session)
    service.products = Mock()
    result = service.search_products(category_id=uuid.uuid4(), include_descendants=True)
    assert result.Items == [] and result.Total == 0
    service.products.list_products.assert_not_called()


def test_default_search_remains_direct_category_only(catalog_tree):
    session, root, *_ = catalog_tree
    service = ProductService(session)
    service.products = Mock()
    service.products.list_products.return_value = []
    service.products.count_products.return_value = 0
    service.search_products(category_id=root.CategoryId)
    assert service.products.list_products.call_args.kwargs["category_ids"] == [root.CategoryId]
