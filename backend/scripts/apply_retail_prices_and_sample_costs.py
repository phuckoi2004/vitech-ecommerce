"""One reviewed test-data correction: retailer list/sale pairs and lower sample costs.

This is not an inventory receipt or an admin API for rewriting real purchase cost.
Normal catalog CRUD still rejects cost writes. Default is dry-run; --apply locks
the reviewed SKUs, saves before/after evidence and commits the whole batch once.
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

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.database import SessionLocal
from app.models import ProductVariant, Promotion, User
from app.services import Actor
from app.services.pricing import PricingService, variant_price
from app.services.promotion import PromotionService
from scripts.enrich_sample_catalog import snapshot

BATCH = 'retail-list-and-sample-cost-2026-10-19'
MANIFEST = BACKEND / 'data' / f'{BATCH}.json'
OUTPUT = BACKEND.parent / 'output/retail-list-cost-20261019'


def sample_cost_reduction(sale):
    """Deduct from existing cost, as explicitly requested; never infer wholesale cost."""
    sale = Decimal(str(sale))
    for ceiling, reduction in ((500000, 50000), (2000000, 100000), (5000000, 300000),
                               (10000000, 500000), (20000000, 1000000)):
        if sale < ceiling:
            return Decimal(reduction)
    return Decimal(1500000)


def run(session, plan, *, apply=False, folder=OUTPUT):
    if plan['Batch'] != BATCH:
        raise ValueError('Unexpected correction batch')
    rows = plan['Variants']
    if len({r['ProductVariantId'] for r in rows}) != len(rows):
        raise ValueError('Duplicate variant')
    report = dict(Apply=apply, Variants=len(rows), Changes=0, PriceChanges=0, ListPriceChanges=0,
                  CostChanges=0, CancelledTestPromotions=0, Rows=[])
    service = PricingService(session)
    with service.transaction():
        if apply and session.bind.dialect.name == 'postgresql':
            session.execute(text('SELECT pg_advisory_xact_lock(2026101902)'))
        query = select(ProductVariant).where(ProductVariant.ProductVariantId.in_([
            uuid.UUID(r['ProductVariantId']) for r in rows])).order_by(ProductVariant.ProductVariantId)
        if apply:
            query = query.with_for_update()
        variants = {str(v.ProductVariantId): v for v in session.scalars(query)}
        programs = {str(p.PromotionId): p for p in session.scalars(select(Promotion).where(
            Promotion.PromotionId.in_([uuid.UUID(p['PromotionId']) for p in plan['CancelTestPromotions']])))}
        for expected in plan['CancelTestPromotions']:
            p = programs.get(expected['PromotionId'])
            if p is None or p.Name != expected['Name'] or p.ApplyMode != 'Automatic' or not p.Name.startswith('[TEST] public-pricing-test-v1'):
                raise ValueError('Only the earlier test automatic programs may be cancelled')
        for row in rows:
            variant = variants.get(row['ProductVariantId'])
            if variant is None or str(variant.ProductId) != row['ProductId'] or (
                variant.Sku, variant.Color, variant.Storage, variant.product.Slug, variant.product.Name) != (
                row['Sku'], row['Color'], row['Storage'], row['Slug'], row['ProductName']):
                raise ValueError('Variant identity changed: ' + row['Sku'])
            if variant.IsDeleted or not variant.IsActive or variant.product.IsDeleted or variant.product.Status != 'Active':
                raise ValueError('Variant is no longer active')
            sale, cost = Decimal(row['SalePrice']), Decimal(row['CostPrice'])
            listed = Decimal(row['ListPrice']) if row['ListPrice'] is not None else None
            if not sale.is_finite() or not cost.is_finite() or not 0 < cost <= sale or (listed is not None and listed < sale):
                raise ValueError('Invalid sale/list/cost ordering')
            if Decimal(row['BeforeCostPrice']) - cost != sample_cost_reduction(sale):
                raise ValueError('Cost reduction differs from the approved tiers')
            for field, before, after in (
                ('Price', Decimal(row['BeforePrice']), sale),
                ('CompareAtPrice', Decimal(row['BeforeListPrice']) if row['BeforeListPrice'] is not None else None, listed),
                ('CostPrice', Decimal(row['BeforeCostPrice']), cost),
            ):
                if getattr(variant, field) not in (before, after):
                    raise ValueError('Price or cost changed after review: ' + row['Sku'])
            if row['Reference'] is not None:
                reference = row['Reference']
                checked = datetime.fromisoformat(reference['CheckedAt'])
                if abs((datetime.now(timezone.utc) - checked).total_seconds()) > 3 * 86400:
                    raise ValueError('Retail reference is stale')
                if sale != Decimal(str(reference['SalePrice'])) or listed != (
                    Decimal(str(reference['ListPrice'])) if reference['ListPrice'] else None):
                    raise ValueError('Prices do not match retail evidence')
        before = snapshot(session) if apply else None
        if apply:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / ('before-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
            path.write_text(json.dumps(dict(Catalog=before, Promotions=[dict(Id=str(p.PromotionId), Name=p.Name, Status=p.Status)
                                          for p in programs.values()]), ensure_ascii=False, indent=2), encoding='utf-8')
            report['BeforeSnapshot'] = str(path)
            admin = session.scalar(select(User).where(User.Role == 'Admin', User.AccountStatus == 'Active',
                                                      User.IsDeleted.is_(False)).order_by(User.CreatedAt).limit(1))
            if admin is None:
                raise ValueError('No active administrator')
            for p in programs.values():
                if p.Status != 'Cancelled':
                    PromotionService(session).cancel_promotion(Actor(admin.UserId, 'Admin'), p.PromotionId)
                    report['CancelledTestPromotions'] += 1
        remaining = [p for p in service.automatic_promotions() if str(p.PromotionId) not in programs]
        now = service.now()
        for row in rows:
            variant = variants[row['ProductVariantId']]
            sale, cost = Decimal(row['SalePrice']), Decimal(row['CostPrice'])
            listed = Decimal(row['ListPrice']) if row['ListPrice'] is not None else None
            changed = (variant.Price, variant.CompareAtPrice, variant.CostPrice) != (sale, listed, cost)
            report['PriceChanges'] += variant.Price != sale
            report['ListPriceChanges'] += variant.CompareAtPrice != listed
            report['CostChanges'] += variant.CostPrice != cost
            report['Changes'] += changed
            from types import SimpleNamespace
            proposed = SimpleNamespace(Price=sale, CompareAtPrice=listed, CostPrice=cost, product=variant.product)
            result = variant_price(proposed, remaining, now)
            if result['SalePrice'] != sale:
                raise ValueError('Another automatic program changes the requested retail sale price')
            report['Rows'].append(dict(**{k: v for k, v in row.items() if k != 'Reference'},
                                       DiscountPercent=str(result['DiscountPercent']), GrossProfit=str(sale-cost),
                                       SourceUrl=row['Reference']['SourceUrl'] if row['Reference'] else '', Changed=changed))
            if apply:
                # Explicit sample-data correction authorized by the user. Do not rewrite receipt/order snapshots.
                variant.Price = sale.quantize(Decimal('.01'))
                variant.CompareAtPrice = listed.quantize(Decimal('.01')) if listed is not None else None
                variant.CostPrice = cost.quantize(Decimal('.01'))
        if apply:
            session.flush()
            after = snapshot(session)
            targets = {r['ProductVariantId']: r for r in rows}
            for table, records in before.items():
                if set(records) != set(after[table]):
                    raise ValueError('Unexpected row creation or deletion')
                for record_id, original in records.items():
                    expected = dict(original)
                    if table == 'ProductVariants' and record_id in targets:
                        row = targets[record_id]
                        expected.update(Price=str(Decimal(row['SalePrice']).quantize(Decimal('.01'))),
                                        CompareAtPrice=str(Decimal(row['ListPrice']).quantize(Decimal('.01'))) if row['ListPrice'] else None,
                                        CostPrice=str(Decimal(row['CostPrice']).quantize(Decimal('.01'))))
                    if expected != after[table][record_id]:
                        raise ValueError('Unexpected catalog/inventory change; rolling back')
        report['CostReductions'] = dict(Counter(str(Decimal(r['BeforeCostPrice'])-Decimal(r['CostPrice'])) for r in rows))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    plan = json.loads(MANIFEST.read_text(encoding='utf-8'))
    with SessionLocal() as session:
        report = run(session, plan, apply=args.apply)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    name = 'applied' if args.apply else 'preview'
    (OUTPUT / f'{name}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    fields = ['ProductName', 'Sku', 'Color', 'Storage', 'BeforePrice', 'BeforeListPrice', 'BeforeCostPrice',
              'ListPrice', 'SalePrice', 'CostPrice', 'DiscountPercent', 'GrossProfit', 'SourceUrl', 'Changed']
    with (OUTPUT / f'{name}.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(report['Rows'])
    print(json.dumps({k:v for k,v in report.items() if k != 'Rows'}, ensure_ascii=True))


if __name__ == '__main__':
    main()
