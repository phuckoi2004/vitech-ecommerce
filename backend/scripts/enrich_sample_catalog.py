"""Apply reviewed child categories and product descriptions without changing schema.

Dry-run by default. Every product keeps its ID, SKU, price and inventory history.
An unexpected description or category aborts the complete transaction. An apply
snapshot is stored under the ignored output folder before any data is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import func, select, text

BACKEND = Path(__file__).resolve().parents[1]
WORKSPACE = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal
from app.models import Brand, Category, Product, ProductImage, ProductVariant, StockAdjustment, User
from app.schemas.catalog import CategoryCreate, CategoryUpdate, ProductUpdate
from app.services import Actor
from app.services.catalog import CategoryService, ProductService

DATA = BACKEND / 'data'
MODELS = (Category, Product, ProductVariant, ProductImage, Brand, StockAdjustment)
IMAGE_HOSTS = {'cdn2.cellphones.com.vn', 'cdn.hstatic.net'}


def sha(value):
    return hashlib.sha256((value or '').encode('utf-8')).hexdigest()


class DescriptionCheck(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images, self.headings = [], 0

    def handle_starttag(self, tag, attrs):
        if tag not in {'p', 'strong', 'h2', 'img'}:
            raise ValueError(f'Unexpected description element: {tag}')
        if tag == 'h2':
            self.headings += 1
        if tag == 'img':
            attrs = dict(attrs)
            if set(attrs) != {'src', 'alt'} or not attrs['alt']:
                raise ValueError('Description images need only src and nonempty alt')
            url = urlparse(attrs['src'])
            if url.scheme != 'https' or url.hostname not in IMAGE_HOSTS:
                raise ValueError('Unreviewed description image host')
            self.images.append(attrs['src'])
        elif attrs:
            raise ValueError('Unexpected HTML attributes')


def manifests():
    seed = json.loads((DATA / 'sample-catalog-2026-10-17.json').read_text(encoding='utf-8'))
    descriptions = json.loads((DATA / 'catalog-descriptions-2026-10-17.json').read_text(encoding='utf-8'))
    groups = json.loads((DATA / 'catalog-child-categories-2026-10-17.json').read_text(encoding='utf-8'))
    originals = {row['sku']: row for row in seed['products']}
    assert len(originals) == len(descriptions['products']) == 200
    assert {row['sku'] for row in descriptions['products']} == set(originals)
    assert Counter(group['parent_slug'] for group in groups['categories']) == {
        'dien-thoai': 10, 'laptop': 10, 'may-tinh-bang': 10, 'tai-nghe': 10}
    assert len({group['slug'] for group in groups['categories']}) == 40
    assert len(groups['assignments']) == len({row['product_slug'] for row in groups['assignments']}) == 121
    assert {row['child_slug'] for row in groups['assignments']} == {row['slug'] for row in groups['categories']}
    parents = {row['slug']: row['parent_slug'] for row in groups['categories']}
    for row in groups['assignments']:
        assert row['parent_slug'] == parents[row['child_slug']]
        if row['sku']:
            original = originals[row['sku']]
            assert row['product_slug'] == original['slug'] and row['parent_slug'] == original['category_slug']
    for row in descriptions['products']:
        original = originals[row['sku']]
        assert row['slug'] == original['slug'] and row['name'] == original['name']
        assert row['source_url'] == original['source_url']
        assert row['previous_description_sha256'] == sha(original['description'])
        check = DescriptionCheck()
        check.feed(row['description'])
        assert check.headings >= 2 and check.images and set(check.images) <= set(row['images'])
        assert row['description'] != original['description']
    return descriptions, groups


def fingerprint(item):
    values = {column.key: getattr(item, column.key) for column in item.__mapper__.column_attrs}
    return json.loads(json.dumps(values, default=str, ensure_ascii=False))


def snapshot(db):
    return {model.__tablename__: {
        str(getattr(item, model.__mapper__.primary_key[0].key)): fingerprint(item)
        for item in db.scalars(select(model)).all()
    } for model in MODELS}


def run(apply=False):
    descriptions, groups = manifests()
    description_by_slug = {row['slug']: row for row in descriptions['products']}
    assignment_by_slug = {row['product_slug']: row for row in groups['assignments']}
    folder = WORKSPACE / 'output/catalog-enrichment-20261017'
    folder.mkdir(parents=True, exist_ok=True)
    result = {'apply': apply, 'created_categories': 0, 'updated_categories': 0,
              'updated_descriptions': 0, 'reassigned_products': 0, 'unchanged_products': 0}
    with SessionLocal() as db:
        actor_row = db.execute(select(User.UserId, User.Role).where(
            User.Role == 'Admin', User.AccountStatus == 'Active', User.IsDeleted.is_(False)
        ).order_by(User.CreatedAt).limit(1)).first()
        if not actor_row:
            raise ValueError('No active Admin for the existing catalog services')
        actor = Actor(actor_row.UserId, actor_row.Role)
        categories, products = CategoryService(db), ProductService(db)
        with products.transaction():
            if apply:
                db.execute(text('SELECT pg_advisory_xact_lock(2026101740)'))
            before = snapshot(db)
            category_by_slug = {item.Slug: item for item in db.scalars(select(Category))}
            variant_by_sku = {item.Sku: item for item in db.scalars(select(ProductVariant))}
            slugs = set(description_by_slug) | set(assignment_by_slug)
            query = select(Product).where(Product.Slug.in_(slugs))
            if apply:
                query = query.with_for_update()
            product_by_slug = {item.Slug: item for item in db.scalars(query)}
            if set(product_by_slug) != slugs:
                raise ValueError('Missing or renamed product; no data changed')

            # Validate the entire batch before its first write, including reruns.
            for slug, product in product_by_slug.items():
                if product.IsDeleted or product.Status != 'Active':
                    raise ValueError('Product is no longer active: ' + slug)
                row = description_by_slug.get(slug)
                if row:
                    variant = variant_by_sku.get(row['sku'])
                    if not variant or variant.ProductId != product.ProductId or product.Name != row['name']:
                        raise ValueError('SKU, product identity or name changed: ' + slug)
                    if sha(product.Description) not in {row['previous_description_sha256'], sha(row['description'])}:
                        raise ValueError('Description has been edited since preparation: ' + slug)
                assignment = assignment_by_slug.get(slug)
                if assignment:
                    parent = category_by_slug[assignment['parent_slug']]
                    child = category_by_slug.get(assignment['child_slug'])
                    allowed = {parent.CategoryId} | ({child.CategoryId} if child else set())
                    if product.CategoryId not in allowed:
                        raise ValueError('Product category has been changed: ' + slug)
            for group in groups['categories']:
                parent = category_by_slug[group['parent_slug']]
                if parent.ParentCategoryId or not parent.IsActive:
                    raise ValueError('Expected an active root category')
                child = category_by_slug.get(group['slug'])
                if child and (child.Name != group['name'] or child.ParentCategoryId != parent.CategoryId or not child.IsActive):
                    raise ValueError('Category slug belongs to a different group: ' + group['slug'])
                if group.get('existing_category_id') and (not child or str(child.CategoryId) != group['existing_category_id']):
                    raise ValueError('Original battery category was changed; no duplicate will be created')

            if apply:
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                backup = folder / f'before-{stamp}.json'
                backup.write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding='utf-8')
                result['backup'] = str(backup.relative_to(WORKSPACE))
            planned_categories = dict(category_by_slug)
            edited_existing_categories = set()
            for group in groups['categories']:
                child = category_by_slug.get(group['slug'])
                if not child:
                    result['created_categories'] += 1
                    if apply:
                        created = categories.create_category(actor, CategoryCreate(
                            ParentCategoryId=category_by_slug[group['parent_slug']].CategoryId,
                            Name=group['name'], Slug=group['slug'], Description=group['description'],
                            ImageUrl=group['image_url'], DisplayOrder=group['display_order'], IsActive=True))
                        planned_categories[group['slug']] = db.get(Category, created.CategoryId)
                else:
                    values = {key: value for key, value in {
                        'Description': group['description'], 'DisplayOrder': group['display_order']
                    }.items() if getattr(child, key) != value}
                    if values:
                        result['updated_categories'] += 1
                        edited_existing_categories.add(str(child.CategoryId))
                        if apply:
                            categories.update_category(actor, child.CategoryId, CategoryUpdate(**values))
            updated_product_ids = set()
            for slug, product in product_by_slug.items():
                values = {}
                row = description_by_slug.get(slug)
                if row and product.Description != row['description']:
                    result['updated_descriptions'] += 1
                    values['Description'] = row['description']
                assignment = assignment_by_slug.get(slug)
                if assignment:
                    child = planned_categories.get(assignment['child_slug'])
                    if child is None or product.CategoryId != child.CategoryId:
                        result['reassigned_products'] += 1
                        if child:
                            values['CategoryId'] = child.CategoryId
                changed = bool(values) or (assignment and child is None)
                if changed:
                    updated_product_ids.add(str(product.ProductId))
                    if apply:
                        products.update_product(actor, product.ProductId, ProductUpdate(**values))
                else:
                    result['unchanged_products'] += 1
            if apply:
                db.flush()
                after = snapshot(db)
                for table in before:
                    if table != 'Categories' and set(after[table]) != set(before[table]):
                        raise ValueError('Unexpected row creation/deletion: ' + table)
                    for item_id, old in before[table].items():
                        current = after[table][item_id]
                        ignore = ({'Description', 'CategoryId', 'UpdatedAt'}
                                  if table == 'Products' and item_id in updated_product_ids
                                  else {'Description', 'DisplayOrder'}
                                  if table == 'Categories' and item_id in edited_existing_categories else set())
                        if {k: v for k, v in old.items() if k not in ignore} != {k: v for k, v in current.items() if k not in ignore}:
                            raise ValueError('Unexpected change, transaction rolled back: ' + table)
                for group in groups['categories']:
                    child = planned_categories[group['slug']]
                    actual = db.scalar(select(func.count()).select_from(Product).where(
                        Product.CategoryId == child.CategoryId, Product.IsDeleted.is_(False), Product.Status == 'Active'))
                    expected = sum(row['child_slug'] == group['slug'] for row in groups['assignments'])
                    if actual != expected or actual < 1:
                        raise ValueError('Wrong or empty child category: ' + group['slug'])
                result['verified_nonempty_child_categories'] = 40
                result['verified_unchanged_stock_and_prices'] = True
                result['totals'] = {table: len(rows) for table, rows in after.items()}
        # Only publish success after the outer service transaction has committed.
        result_path = folder / ('apply-result.json' if apply else 'dry-run.json')
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    arguments = parser.parse_args()
    try:
        print(json.dumps(run(arguments.apply), ensure_ascii=False, indent=2))
    except Exception as exc:
        # Connection errors may include credentials; emit no connection details.
        print('Catalog enrichment aborted: ' + (str(exc) if isinstance(exc, (ValueError, AssertionError)) else type(exc).__name__), file=sys.stderr)
        raise SystemExit(1) from None
