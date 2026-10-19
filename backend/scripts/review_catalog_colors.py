"""Apply reviewed colour/photo fixes and rewritten descriptions to existing items.

No product/SKU or inventory creation. Defaults to dry-run. A pre-write snapshot and
strict comparison protect prices, stock, technical specifications and existing edits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select, text

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.core.catalog_media import media_settings, technical_specifications, variant_images
from app.database import SessionLocal
from app.models import Category, Product, ProductImage, ProductVariant, StockAdjustment, User
from app.schemas.catalog import ProductImageUpdate, ProductUpdate, ProductVariantUpdate
from app.schemas.catalog_item import CatalogItemImage, CatalogVariantWrite
from app.services import Actor
from app.services.catalog import ProductImageService, ProductService, ProductVariantService
from app.services.catalog_item import CatalogItemService

# Keep the complete snapshots catalog-only; never include user records or secrets.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_sample_catalog import snapshot

ROOT = BACKEND.parent
MANIFEST = BACKEND / 'data/catalog-review-2026-10-18.json'
FOLDER = ROOT / 'output/catalog-review-20261018'
IMAGE_HOSTS = {'cdn2.cellphones.com.vn', 'cdn.hstatic.net', 'cdn2.fptshop.com.vn'}
S26 = 'samsung-galaxy-s26-4e299bca994342df93a324d7e6fbc5d5'


def sha(value):
    return hashlib.sha256((value or '').encode()).hexdigest()


def desired_media(row):
    return {'ImageUrls': [row['image_url']], 'DefaultImageUrl': row['image_url']}


class CheckHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.headings = self.images = 0

    def handle_starttag(self, tag, attrs):
        if tag not in {'h2', 'p', 'strong', 'img'}:
            raise ValueError('Unexpected description tag')
        if tag == 'img':
            values = dict(attrs)
            url = urlparse(values.get('src', ''))
            if set(values) != {'src', 'alt'} or not values['alt'] or url.scheme != 'https' or url.hostname not in IMAGE_HOSTS:
                raise ValueError('Unreviewed description image')
            self.images += 1
        elif attrs:
            raise ValueError('Unexpected description attribute')
        if tag == 'h2':
            self.headings += 1


def read_manifest():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    descriptions, fixes = manifest['descriptions'], manifest['media_fixes']
    assert len(descriptions) == len({row['product_id'] for row in descriptions}) == 201
    assert len(fixes) == len({row['variant_id'] for row in fixes}) == 170
    for row in descriptions:
        check = CheckHTML()
        check.feed(row['description'])
        if check.headings != row['section_count'] or check.headings < 2 or not check.images:
            raise ValueError('Incomplete description: ' + row['product_slug'])
    for row in fixes:
        url = urlparse(row['image_url'])
        if url.scheme != 'https' or url.hostname not in IMAGE_HOSTS:
            raise ValueError('Unreviewed colour image')
    return manifest


def run(apply=False):
    manifest = read_manifest()
    FOLDER.mkdir(parents=True, exist_ok=True)
    result = {'apply': apply, 'updated_descriptions': 0, 'updated_variant_media': 0,
              'corrected_color_labels': 0, 'new_gallery_images': 0, 'removed_wrong_model_images': 0,
              'updated_default_images': 0}
    with SessionLocal() as db:
        actor_row = db.execute(select(User.UserId, User.Role).where(
            User.Role == 'Admin', User.AccountStatus == 'Active', User.IsDeleted.is_(False)
        ).order_by(User.CreatedAt).limit(1)).first()
        if not actor_row:
            raise ValueError('No active Admin for catalog services')
        actor = Actor(actor_row.UserId, actor_row.Role)
        products, images, items = ProductService(db), ProductImageService(db), CatalogItemService(db)
        variant_service = ProductVariantService(db)
        with products.transaction():
            if apply:
                db.execute(text('SELECT pg_advisory_xact_lock(2026101861)'))
            query = select(Product).where(Product.ProductId.in_([uuid.UUID(row['product_id']) for row in manifest['descriptions']])).order_by(Product.ProductId)
            if apply:
                query = query.with_for_update()
            by_id = {str(item.ProductId): item for item in db.scalars(query)}
            variant_query = select(ProductVariant).order_by(ProductVariant.ProductVariantId)
            if apply:
                variant_query = variant_query.with_for_update()
            variants = {str(item.ProductVariantId): item for item in db.scalars(variant_query)}
            before = snapshot(db)
            for row in manifest['descriptions']:
                product = by_id.get(row['product_id'])
                if product is None or product.Slug != row['product_slug'] or product.Name != row['name']:
                    raise ValueError('Product identity changed: ' + row['product_slug'])
                if product.IsDeleted or product.Status != 'Active':
                    raise ValueError('Product is no longer active')
                if sha(product.Description) not in {row['before_sha256'], sha(row['description'])}:
                    raise ValueError('Description was edited after preparation: ' + row['product_slug'])
            for row in manifest['media_fixes']:
                product, variant = by_id[row['product_id']], variants.get(row['variant_id'])
                if variant is None or variant.Sku != row['sku'] or str(variant.ProductId) != row['product_id'] or variant.IsDeleted:
                    raise ValueError('Variant identity changed: ' + row['sku'])
                if variant.Color not in {row['before_color'], row['color']}:
                    raise ValueError('Colour was edited after preparation: ' + row['sku'])
                config = media_settings(product).get('Variants', {}).get(row['variant_id'])
                if config != row['previous_media'] and config != desired_media(row):
                    raise ValueError('Colour photos were edited after preparation: ' + row['sku'])
                default_id = media_settings(product).get('DefaultVariantId')
                if row['is_default'] and default_id and default_id != row['variant_id']:
                    raise ValueError('Default colour was changed after preparation')
            if apply:
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                backup = FOLDER / f'before-apply-{stamp}.json'
                backup.write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding='utf-8')
                result['backup'] = str(backup.relative_to(ROOT))
            for media_index, row in enumerate(manifest['media_fixes'], 1):
                product, variant = by_id[row['product_id']], variants[row['variant_id']]
                current = media_settings(product).get('Variants', {}).get(row['variant_id'])
                image_list = images.images.list_by_product(product.ProductId)
                saved_image = next((image for image in image_list if image.ImageUrl == row['image_url']), None)
                if saved_image is None:
                    result['new_gallery_images'] += 1
                if variant.Color != row['color']:
                    result['corrected_color_labels'] += 1
                if current != desired_media(row) or variant.Color != row['color']:
                    result['updated_variant_media'] += 1
                    if apply:
                        if variant.Color != row['color']:
                            variant_service.update_variant(actor, variant.ProductVariantId, ProductVariantUpdate(
                                Color=row['color'], VariantName=' · '.join(filter(None, [row['color'], variant.Storage]))))
                        # The full variant form also trims legacy Storage text.
                        # This review changes only colour/media, so leave every
                        # existing configuration field byte-for-byte intact.
                        media_data = CatalogVariantWrite(
                            Sku=variant.Sku, Color=row['color'], Storage=variant.Storage, Price=variant.Price,
                            MinStockLevel=variant.MinStockLevel, IsActive=variant.IsActive,
                            IsSerialTracked=variant.IsSerialTracked,
                            VariantImageUrls=[row['image_url']], DefaultImageUrl=row['image_url'],
                            IsDefaultVariant=row['is_default'], AdditionalImages=[CatalogItemImage(ImageUrl=row['image_url'])])
                        items._save_media(product, variant.ProductVariantId, media_data)
                        original = before['ProductVariants'][row['variant_id']]
                        db.refresh(variant)
                        changed = {column.key: {'before': original[column.key], 'after': str(getattr(variant, column.key))
                                   if not isinstance(getattr(variant, column.key), (int, bool, type(None))) else getattr(variant, column.key)}
                                   for column in variant.__mapper__.column_attrs
                                   if column.key not in {'Color', 'VariantName'}
                                   and original[column.key] != (str(getattr(variant, column.key))
                                   if not isinstance(getattr(variant, column.key), (int, bool, type(None))) else getattr(variant, column.key))}
                        if changed:
                            (FOLDER / 'unexpected-variant-change.json').write_text(json.dumps({
                                'variant_id': row['variant_id'], 'sku': variant.Sku, 'changes': changed}, ensure_ascii=False, indent=2), encoding='utf-8')
                            raise ValueError('Unexpected variant field: ' + ', '.join(changed))
                        saved_image = next(image for image in images.images.list_by_product(product.ProductId) if image.ImageUrl == row['image_url'])
                if row['is_default'] and (saved_image is None or not saved_image.IsDefault):
                    result['updated_default_images'] += 1
                    if apply:
                        images.update_image(actor, product.ProductId, saved_image.ProductImageId, ProductImageUpdate(IsDefault=True))
                if apply and media_index % 40 == 0:
                    print('Colour photos updated:', media_index, '/', len(manifest['media_fixes']), flush=True)
            # Remove only the two objectively wrong Ultra gallery records from S26.
            # Existing user uploads and remote storage objects are preserved.
            wrong_images = [image for image in db.scalars(select(ProductImage).join(Product))
                            if image.product.Slug == S26 and 'galaxy-s26-ultra' in image.ImageUrl]
            result['removed_wrong_model_images'] = len(wrong_images)
            removed_ids = {str(image.ProductImageId) for image in wrong_images}
            if apply:
                for image in wrong_images:
                    images.delete_image(actor, image.ProductId, image.ProductImageId)
            for index, row in enumerate(manifest['descriptions'], 1):
                product = by_id[row['product_id']]
                if product.Description != row['description']:
                    result['updated_descriptions'] += 1
                    if apply:
                        products.update_product(actor, product.ProductId, ProductUpdate(Description=row['description']))
                if apply and index % 50 == 0:
                    print('Descriptions updated:', index, '/', len(manifest['descriptions']), flush=True)
            if apply:
                db.flush()
                after = snapshot(db)
                for table in ('Categories', 'Brands', 'StockAdjustments'):
                    if after[table] != before[table]:
                        raise ValueError('Unexpected change: ' + table)
                if set(after['Products']) != set(before['Products']) or set(after['ProductVariants']) != set(before['ProductVariants']):
                    raise ValueError('Unexpected product or SKU creation/deletion')
                for row_id, old in before['ProductVariants'].items():
                    current = after['ProductVariants'][row_id]
                    allowed = {'Color', 'VariantName'} if row_id in {row['variant_id'] for row in manifest['media_fixes']} else set()
                    if {k: v for k, v in old.items() if k not in allowed} != {k: v for k, v in current.items() if k not in allowed}:
                        changed = {key: {'before': old.get(key), 'after': current.get(key)}
                                   for key in old if key not in allowed and old.get(key) != current.get(key)}
                        (FOLDER / 'unexpected-variant-change.json').write_text(json.dumps({
                            'variant_id': row_id, 'sku': old['Sku'], 'changes': changed}, ensure_ascii=False, indent=2), encoding='utf-8')
                        raise ValueError('Price, stock or variant changed unexpectedly')
                for row_id, old in before['Products'].items():
                    current = after['Products'][row_id]
                    allowed = {'Description', 'Specifications', 'UpdatedAt'}
                    if {k: v for k, v in old.items() if k not in allowed} != {k: v for k, v in current.items() if k not in allowed}:
                        raise ValueError('Product identity, category or business data changed')
                    if technical_specifications(current['Specifications']) != technical_specifications(old['Specifications']):
                        raise ValueError('Technical specifications changed unexpectedly')
                for row_id, old in before['ProductImages'].items():
                    if row_id in removed_ids:
                        continue
                    current = after['ProductImages'][row_id]
                    if {k: v for k, v in old.items() if k != 'IsDefault'} != {k: v for k, v in current.items() if k != 'IsDefault'}:
                        raise ValueError('Existing image changed unexpectedly')
                for row in manifest['media_fixes']:
                    product = by_id[row['product_id']]
                    selected, thumbnail = variant_images(product, uuid.UUID(row['variant_id']), images.images.list_by_product(product.ProductId))
                    if thumbnail != row['image_url'] or [image.ImageUrl for image in selected] != [row['image_url']]:
                        raise ValueError('Colour/photo mismatch remains')
                result['verified_existing_prices_stock_and_history'] = True
                result['totals'] = {table: len(rows) for table, rows in after.items()}
        # Outer service transaction has committed successfully.
        (FOLDER / ('apply-result.json' if apply else 'dry-run.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    try:
        print(json.dumps(run(parser.parse_args().apply), ensure_ascii=False, indent=2))
    except Exception as exc:
        print('Catalog review aborted: ' + (str(exc) if isinstance(exc, (ValueError, AssertionError)) else type(exc).__name__), file=sys.stderr)
        raise SystemExit(1) from None
