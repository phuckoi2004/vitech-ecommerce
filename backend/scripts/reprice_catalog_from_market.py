"""Apply the reviewed 19/10/2026 retail price references to existing catalog SKUs.

Dry-run by default. Changes only Price through ProductVariantService. A strict
before-price/identity check detects stale plans; reruns leave applied prices alone.
Cost and inventory never change. Existing Automatic offers still run afterwards.
"""
import argparse
import csv
import json
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

from sqlalchemy import select, text

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.database import SessionLocal
from app.models import ProductVariant, User
from app.schemas.catalog import ProductVariantUpdate
from app.services import Actor
from app.services.catalog import ProductVariantService
from app.services.pricing import PricingService, variant_price
from scripts.enrich_sample_catalog import snapshot

MANIFEST = BACKEND / 'data/market-pricing-2026-10-19.json'
DEFAULT_OUTPUT = BACKEND.parent / 'output/market-pricing-20261019'


def apply_plan(session, manifest, *, apply=False, folder=DEFAULT_OUTPUT):
    if manifest['Batch'] != 'market-pricing-2026-10-19':
        raise ValueError('Unexpected price batch')
    references = {r['Slug']: r for r in manifest['References']}
    rows = manifest['Variants']
    if len({r['ProductVariantId'] for r in rows}) != len(rows):
        raise ValueError('Duplicate SKU in price plan')
    for reference in references.values():
        if urlparse(reference['SourceUrl']).hostname not in {'cellphones.com.vn', 'gearvn.com'}:
            raise ValueError('Unreviewed price source')
        checked = datetime.fromisoformat(reference['CheckedAt'])
        if abs((datetime.now(timezone.utc) - checked).total_seconds()) > 3 * 86400:
            raise ValueError('Price evidence is stale; collect and review it again')
    service = ProductVariantService(session)
    report = dict(Apply=apply, MatchedProducts=len(references), ReviewedVariants=len(rows), UpdatedVariants=0,
                  StatusCounts={}, Rows=[])
    with service.transaction():
        if apply and session.bind.dialect.name == 'postgresql':
            session.execute(text('SELECT pg_advisory_xact_lock(2026101901)'))
        query = select(ProductVariant).where(ProductVariant.ProductVariantId.in_([
            uuid.UUID(r['ProductVariantId']) for r in rows])).order_by(ProductVariant.ProductVariantId)
        if apply:
            query = query.with_for_update()
        variants = {str(v.ProductVariantId): v for v in session.scalars(query)}
        before = snapshot(session) if apply else None
        pricing = PricingService(session)
        promotions, now = pricing.automatic_promotions(), pricing.now()
        actor = None
        if apply:
            user = session.scalar(select(User).where(User.Role == 'Admin', User.AccountStatus == 'Active',
                                                    User.IsDeleted.is_(False)).order_by(User.CreatedAt).limit(1))
            if user is None:
                raise ValueError('No active Admin for the catalog service')
            actor = Actor(user.UserId, 'Admin')
        changes = []
        for row in rows:
            variant = variants.get(row['ProductVariantId'])
            if variant is None or str(variant.ProductId) != row['ProductId'] or variant.Sku != row['Sku']:
                raise ValueError('SKU identity changed: ' + row['Sku'])
            if (variant.Color, variant.Storage, variant.product.Slug, variant.product.Name) != (
                    row['Color'], row['Storage'], row['Slug'], row['ProductName']):
                raise ValueError('SKU configuration changed: ' + row['Sku'])
            if variant.IsDeleted or not variant.IsActive or variant.product.IsDeleted or variant.product.Status != 'Active':
                raise ValueError('SKU is no longer sellable: ' + row['Sku'])
            if row['MarketPrice'] is None:
                status = 'unmatched-color'
            else:
                target = Decimal(row['MarketPrice']).quantize(Decimal('.01'))
                if not target.is_finite() or target <= 0:
                    raise ValueError('Invalid public price')
                if variant.Price not in (Decimal(row['BeforePrice']), target):
                    raise ValueError('Price changed after preparation: ' + row['Sku'])
                reference = references[row['Slug']]
                if row['SourceColor'] is not None:
                    source = next(c for c in reference['Colors'] if c['Color'] == row['SourceColor'])
                else:
                    source = reference
                if Decimal(str(source['SalePrice'])) != target:
                    raise ValueError('Target differs from source evidence: ' + row['Sku'])
                if variant.CostPrice <= 0 or target < variant.CostPrice:
                    status = 'price-floor-review'
                elif target == variant.Price:
                    status = 'already-current'
                else:
                    status = 'update'
                    changes.append((variant, target))
            report['Rows'].append(dict(**row, Status=status))
        # Validate the complete plan before the first write.
        if apply:
            folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            path = folder / f'before-{stamp}.json'
            path.write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding='utf-8')
            report['BeforeSnapshot'] = str(path)
            for variant, target in changes:
                service.update_variant(actor, variant.ProductVariantId, ProductVariantUpdate(Price=target))
                report['UpdatedVariants'] += 1
            after = snapshot(session)
            changed_ids = {str(v.ProductVariantId): str(target) for v, target in changes}
            for table, records in before.items():
                if set(records) != set(after[table]):
                    raise ValueError('Unexpected catalog row creation/deletion')
                for record_id, original in records.items():
                    expected = dict(original)
                    if table == 'ProductVariants' and record_id in changed_ids:
                        expected['Price'] = changed_ids[record_id]
                    if expected != after[table][record_id]:
                        raise ValueError('Unexpected change outside Price; rolling back')
        for row in report['Rows']:
            variant = variants[row['ProductVariantId']]
            if not apply and row['Status'] == 'update':
                proposed = SimpleNamespace(Price=Decimal(row['MarketPrice']).quantize(Decimal('.01')),
                                           CostPrice=variant.CostPrice, product=variant.product)
                price = variant_price(proposed, promotions, now)
            else:
                price = variant_price(variant, promotions, now)
            row.update(FinalPrice=str(price['SalePrice']), DiscountPercent=str(price['DiscountPercent']))
            if Decimal(row['FinalPrice']) < variant.CostPrice:
                raise ValueError('Price below cost; rolling back')
        report['StatusCounts'] = dict(Counter(row['Status'] for row in report['Rows']))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--manifest', type=Path, default=MANIFEST)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    with SessionLocal() as session:
        report = apply_plan(session, manifest, apply=args.apply, folder=args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    name = 'applied' if args.apply else 'preview'
    (args.output / f'{name}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    fields = ['ProductName', 'Sku', 'Color', 'Storage', 'BeforePrice', 'MarketPrice', 'FinalPrice',
              'DiscountPercent', 'Status', 'SourceVariantUrl']
    with (args.output / f'{name}.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(report['Rows'])
    print(json.dumps({k: v for k, v in report.items() if k != 'Rows'}, ensure_ascii=True))


if __name__ == '__main__':
    main()
