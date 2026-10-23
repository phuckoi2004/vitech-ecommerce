"""Give every published SKU without Serial/IMEI tracking sample serials for the units it already holds.

Dry-run by default. --apply locks each SKU, turns on IsSerialTracked and registers sample codes
VT-SN-<SKU>-001… as Available, one per unit in stock plus one per unit of Pending orders that has no device yet
(those units get a code at confirmation). Stock, cost and Opening history stay unchanged, as in the Admin
stock edit. The whole batch is one transaction: any error rolls everything back. Reruns skip SKUs that are
already tracked. The codes are sample data for testing, not real device numbers.

Orders past Pending keep their unnumbered units: the report counts those lines, because warranty and return
requests for a tracked SKU ask for a device code those lines do not have.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select

BACKEND = Path(__file__).resolve().parents[1]
WORKSPACE = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal
from app.models import Order, OrderItem, Product, ProductVariant
from app.services.inventory import InventoryService

BATCH = 'sample-serials-2026-10-23'
OUTPUT = WORKSPACE / 'output' / BATCH
PREFIX = 'VT-SN-'
UNNUMBERED_STATUSES = ('Confirmed', 'Processing', 'Shipping', 'Delivered', 'Completed')


def serial_numbers(sku, start, count):
    return [f'{PREFIX}{sku}-{n:03d}' for n in range(start, start + count)]


def candidates(db):
    """Untracked SKUs of products that are not deleted, in lock order (ProductVariantId)."""
    return list(db.scalars(
        select(ProductVariant).join(Product, Product.ProductId == ProductVariant.ProductId).where(
            ProductVariant.IsDeleted.is_(False), Product.IsDeleted.is_(False),
            ProductVariant.IsSerialTracked.is_(False),
        ).order_by(ProductVariant.ProductVariantId)))


def unnumbered_lines(db, variant_ids):
    """Order lines past Pending per SKU; they were sold without a device code."""
    if not variant_ids:
        return {}
    rows = db.execute(select(OrderItem.ProductVariantId, Order.OrderStatus, func.count()).join(
        Order, Order.OrderId == OrderItem.OrderId).where(
        OrderItem.ProductVariantId.in_(variant_ids), Order.OrderStatus.in_(UNNUMBERED_STATUSES),
    ).group_by(OrderItem.ProductVariantId, Order.OrderStatus))
    lines = {}
    for variant_id, status, count in rows:
        lines.setdefault(variant_id, {})[status] = count
    return lines


def plan_variant(service, variant):
    """Codes this SKU needs: stock plus Pending units without a device, minus codes already Available."""
    serials = service.serials
    needed = (variant.StockQuantity + serials.count_unassigned_order_units(variant.ProductVariantId)
              - serials.count_available(variant.ProductVariantId))
    start = serials.count_by_variant(variant.ProductVariantId) + 1
    return serial_numbers(variant.Sku, start, max(needed, 0))


def backfill_variant(service, variant_id):
    """Inside the caller's transaction: lock, recheck, register codes, turn tracking on. None = already tracked."""
    variant = service._lock_variant(variant_id)
    if variant.IsSerialTracked:
        return None
    numbers = plan_variant(service, variant)
    service._register_serials(variant_id, numbers)
    variant.IsSerialTracked = True
    service.variants.flush()
    return numbers


def run(service, *, apply):
    db = service.session
    variants = candidates(db)
    lines = unnumbered_lines(db, [v.ProductVariantId for v in variants])
    rows = []
    if apply:
        with service.transaction():
            for variant in variants:
                numbers = backfill_variant(service, variant.ProductVariantId)
                if numbers is not None:
                    rows.append((variant, numbers))
    else:
        rows = [(variant, plan_variant(service, variant)) for variant in variants]
    report_rows = [{
        'Sku': variant.Sku, 'VariantName': variant.VariantName, 'StockQuantity': variant.StockQuantity,
        'IsActive': variant.IsActive, 'NewSerials': len(numbers),
        'FirstSerial': numbers[0] if numbers else '', 'LastSerial': numbers[-1] if numbers else '',
        'UnnumberedOrderLines': sum(lines.get(variant.ProductVariantId, {}).values()),
    } for variant, numbers in rows]
    status_lines = Counter()
    for counts in lines.values():
        status_lines.update(counts)
    # Rechecked after commit; orders placed meanwhile may legitimately move a SKU, so this is reported, not raised.
    mismatched = [variant.Sku for variant, _ in rows if apply and service.serials.count_available(
        variant.ProductVariantId) != variant.StockQuantity + service.serials.count_unassigned_order_units(
        variant.ProductVariantId)]
    report = {
        'Batch': BATCH, 'Applied': apply, 'Variants': len(rows), 'MismatchedAfterApply': mismatched,
        'Serials': sum(len(numbers) for _, numbers in rows),
        'VariantsWithoutStock': sum(1 for _, numbers in rows if not numbers),
        'UnnumberedOrderLines': dict(status_lines),
        'Rows': report_rows,
    }
    return report, [(variant.Sku, number) for variant, numbers in rows for number in numbers]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with SessionLocal() as session:
        report, serials = run(InventoryService(session), apply=args.apply)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    name = 'applied' if args.apply else 'preview'
    (OUTPUT / f'{name}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                                         encoding='utf-8')
    with (OUTPUT / f'{name}-serials.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['Sku', 'SerialNumber'])
        writer.writerows(serials)
    print(json.dumps({k: v for k, v in report.items() if k != 'Rows'}, ensure_ascii=True))


if __name__ == '__main__':
    main()
