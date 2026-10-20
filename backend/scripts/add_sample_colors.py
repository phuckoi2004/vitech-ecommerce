"""Add the reviewed colour options to the sample catalog.

Dry-run by default. The existing SKU of each product becomes its default colour and keeps its ID, price, stock
and history; every other colour becomes a new SKU with its own photo and a sample Opening of 10 units at 80% of
its reference price. A product whose SKU, colour or variants changed since preparation is skipped, never
overwritten. Rerunning skips colours that already exist. A snapshot is stored before any data is changed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select, text

BACKEND = Path(__file__).resolve().parents[1]
WORKSPACE = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal
from app.models import Product, ProductImage, ProductVariant, StockAdjustment, User
from app.schemas.catalog import ProductVariantUpdate
from app.schemas.catalog_item import CatalogItemCreate, CatalogItemImage
from app.schemas.inventory import StockOpeningCreate
from app.services import Actor
from app.services.catalog import ProductVariantService
from app.services.catalog_item import CatalogItemService
from app.services.inventory import InventoryService

BATCH = 'catalog-colors-2026-10-18'
MANIFEST = BACKEND / 'data' / f'{BATCH}.json'
MODELS = (Product, ProductVariant, ProductImage, StockAdjustment)
IMAGE_HOST = 'https://cdn2.cellphones.com.vn/'


def key(value):
    return unicodedata.normalize('NFC', value or '').strip().casefold()


def sku_for(base, color, taken):
    ascii_name = unicodedata.normalize('NFD', color.replace('Đ', 'D').replace('đ', 'd')).encode('ascii', 'ignore').decode()
    code = re.sub(r'[^A-Z0-9]+', '-', ascii_name.upper()).strip('-') or 'MAU'
    code = code[:50 - len(base) - 4].strip('-')
    sku, index = f'{base}-{code}', 2
    while sku in taken:
        sku, index = f'{base}-{code}{index}', index + 1
    taken.add(sku)
    return sku


def variant_name(color, storage):
    return ' · '.join(filter(None, [color, storage]))


def fingerprint(item):
    values = {column.key: getattr(item, column.key) for column in item.__mapper__.column_attrs}
    return json.loads(json.dumps(values, default=str, ensure_ascii=False))


def snapshot(db):
    return {model.__tablename__: {
        str(getattr(item, model.__mapper__.primary_key[0].key)): fingerprint(item)
        for item in db.scalars(select(model)).all()
    } for model in MODELS}


def plan(db, manifest):
    """Planned writes per product; anything changed since preparation is reported, not touched."""
    by_slug = {item.Slug: item for item in db.scalars(select(Product).where(
        Product.Slug.in_([row['slug'] for row in manifest['products']])))}
    variants = {}
    for variant in db.scalars(select(ProductVariant).where(ProductVariant.IsDeleted.is_(False))):
        variants.setdefault(variant.ProductId, []).append(variant)
    taken = set(db.scalars(select(ProductVariant.Sku)))
    planned, skipped = [], []
    for row in manifest['products']:
        product = by_slug.get(row['slug'])
        if product is None or product.IsDeleted or product.Status != 'Active':
            skipped.append({'slug': row['slug'], 'reason': 'Sản phẩm không còn đang bán'})
            continue
        own = variants.get(product.ProductId, [])
        base = next((item for item in own if item.Sku == row['sku']), None)
        prefix = row['sku'] + '-'
        if base is None or any(item is not base and not item.Sku.startswith(prefix) for item in own):
            skipped.append({'slug': row['slug'], 'reason': 'SKU gốc hoặc danh sách biến thể đã thay đổi'})
            continue
        if base.Color and key(base.Color) != key(row['base_color']):
            skipped.append({'slug': row['slug'], 'reason': f'Biến thể đang có màu khác: {base.Color}'})
            continue
        existing = {key(item.Color) for item in own if item.Color} | {key(base.Color or row['base_color'])}
        additions = []
        for option in row['colors']:
            if key(option['color']) in existing:
                continue
            url = option['image_url']
            if url and not url.startswith(IMAGE_HOST):
                raise ValueError('Unreviewed image host: ' + url)
            price = Decimal(option['price'])
            if price <= 0:
                raise ValueError('Invalid price: ' + row['slug'])
            additions.append({'color': option['color'], 'price': price, 'image_url': url,
                              'sku': sku_for(row['sku'], option['color'], taken)})
        rename = not base.Color or base.VariantName != variant_name(base.Color, base.Storage)
        if rename or additions:
            planned.append({'product': product, 'base': base, 'color': base.Color or row['base_color'],
                            'rename': rename, 'additions': additions})
    return planned, skipped


def run(apply=False):
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    folder = WORKSPACE / 'output' / BATCH
    folder.mkdir(parents=True, exist_ok=True)
    reason = f'{BATCH}: tồn mẫu 10 đơn vị cho màu mới; giá vốn mẫu = 80% giá tham khảo, không phải giá nhập thực tế.'
    result = {'apply': apply}
    with SessionLocal() as db:
        actor_row = db.execute(select(User.UserId, User.Role).where(
            User.Role == 'Admin', User.AccountStatus == 'Active', User.IsDeleted.is_(False)
        ).order_by(User.CreatedAt).limit(1)).first()
        if not actor_row:
            raise ValueError('No active Admin for the catalog services')
        actor = Actor(actor_row.UserId, actor_row.Role)
        items, variants, inventory = CatalogItemService(db), ProductVariantService(db), InventoryService(db)
        with items.transaction():
            if apply:
                db.execute(text('SELECT pg_advisory_xact_lock(2026101850)'))
            before = snapshot(db)
            planned, skipped = plan(db, manifest)
            result.update(products=len(planned), colored_existing_variants=sum(item['rename'] for item in planned),
                          new_variants=sum(len(item['additions']) for item in planned),
                          skipped=skipped + manifest['skipped'])
            if apply:
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                backup = folder / f'before-{stamp}.json'
                backup.write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding='utf-8')
                result['backup'] = str(backup.relative_to(WORKSPACE))
                created = []
                for item in planned:
                    base = item['base']
                    if item['rename']:
                        variants.update_variant(actor, base.ProductVariantId, ProductVariantUpdate(
                            Color=item['color'], VariantName=variant_name(item['color'], base.Storage)))
                    for option in item['additions']:
                        url = option['image_url']
                        saved = items.create_item(actor, CatalogItemCreate(
                            ProductId=item['product'].ProductId, Sku=option['sku'], Color=option['color'],
                            Storage=base.Storage, Price=option['price'], MinStockLevel=base.MinStockLevel, IsActive=True,
                            IsSerialTracked=False, AdditionalImages=[CatalogItemImage(ImageUrl=url)] if url else [],
                            VariantImageUrls=[url] if url else None, DefaultImageUrl=url))
                        inventory.declare_opening(actor, saved.ProductVariantId, StockOpeningCreate(
                            Quantity=10, UnitCost=(option['price'] * Decimal('0.80')).quantize(Decimal('0.01')),
                            Reason=reason))
                        created.append(str(saved.ProductVariantId))
                db.flush()
                after = snapshot(db)
                # Existing SKUs keep price, stock and cost; only the colour and its display name may change.
                for variant_id, old in before['ProductVariants'].items():
                    current = after['ProductVariants'][variant_id]
                    if {k: v for k, v in old.items() if k not in {'Color', 'VariantName'}} != \
                            {k: v for k, v in current.items() if k not in {'Color', 'VariantName'}}:
                        raise ValueError('Existing variant changed, transaction rolled back: ' + variant_id)
                for table in ('ProductImages', 'StockAdjustments'):
                    if any(after[table].get(item_id) != old for item_id, old in before[table].items()):
                        raise ValueError('Existing row changed, transaction rolled back: ' + table)
                for variant_id in created:
                    variant = after['ProductVariants'][variant_id]
                    if variant['StockQuantity'] != 10 or variant['IsDeleted']:
                        raise ValueError('New variant without its sample stock: ' + variant_id)
                result['totals'] = {table: len(rows) for table, rows in after.items()}
        # Only publish success after the outer service transaction has committed.
        result_path = folder / ('apply-result.json' if apply else 'dry-run.json')
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    outcome = run(parser.parse_args().apply)
    print(json.dumps({k: v for k, v in outcome.items() if k != 'skipped'} | {'skipped': len(outcome['skipped'])},
                     ensure_ascii=False, indent=2))
