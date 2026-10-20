"""Price imports must be read-only by default and atomic when applied."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import ProductVariant
from scripts.reprice_catalog_from_market import apply_plan
from tests.test_automatic_pricing import pricing_shop  # noqa: F401
from tests.test_promotion_lifecycle import shop  # noqa: F401


def plan_for(session, variant_ids):
    references, rows = {}, []
    for variant_id in variant_ids:
        variant = session.get(ProductVariant, variant_id)
        product = variant.product
        target = variant.Price - Decimal('100000')
        references[product.Slug] = dict(Slug=product.Slug, SourceUrl='https://cellphones.com.vn/example.html',
            CheckedAt=datetime.now(timezone.utc).isoformat(), SalePrice=str(target), Colors=[])
        rows.append(dict(ProductVariantId=str(variant_id), ProductId=str(product.ProductId), Sku=variant.Sku,
            Color=variant.Color, Storage=variant.Storage, Slug=product.Slug, ProductName=product.Name,
            BeforePrice=str(variant.Price), MarketPrice=str(target), SourceColor=None))
    return dict(Batch='market-pricing-2026-10-19', References=list(references.values()), Variants=rows)


def test_dry_run_does_not_change_prices_or_inventory(pricing_shop, tmp_path):
    s = pricing_shop
    with Session(s['engine']) as session:
        variant_id = s['variant'].ProductVariantId
        plan = plan_for(session, [variant_id])
        result = apply_plan(session, plan, folder=tmp_path)
        session.expire_all()
        variant = session.get(ProductVariant, variant_id)
        assert result['StatusCounts'] == {'update': 1}
        assert variant.Price == Decimal(plan['Variants'][0]['BeforePrice'])
        assert variant.CostPrice == 31000000 and variant.StockQuantity == 10
        assert list(tmp_path.iterdir()) == []


def test_apply_changes_only_price_and_rerun_is_idempotent(pricing_shop, tmp_path):
    s = pricing_shop
    with Session(s['engine']) as session:
        variant_id = s['variant'].ProductVariantId
        plan = plan_for(session, [variant_id])
        result = apply_plan(session, plan, apply=True, folder=tmp_path)
        assert result['UpdatedVariants'] == 1
        session.expire_all()
        variant = session.get(ProductVariant, variant_id)
        assert variant.Price == 34900000 and variant.CostPrice == 31000000 and variant.StockQuantity == 10
        rerun = apply_plan(session, plan, apply=True, folder=tmp_path)
        assert rerun['UpdatedVariants'] == 0 and rerun['StatusCounts'] == {'already-current': 1}


def test_stale_price_aborts_the_entire_batch_before_writes(pricing_shop, tmp_path):
    s = pricing_shop
    with Session(s['engine']) as session:
        first, second = s['variant'].ProductVariantId, s['other'].ProductVariantId
        plan = plan_for(session, [first, second])
        session.get(ProductVariant, second).Price += 1000
        session.commit()
        with pytest.raises(ValueError, match='Price changed after preparation'):
            apply_plan(session, plan, apply=True, folder=tmp_path)
        assert session.get(ProductVariant, first).Price == Decimal(plan['Variants'][0]['BeforePrice'])
        assert list(tmp_path.iterdir()) == []


def test_public_reference_below_cost_is_not_applied(pricing_shop, tmp_path):
    s = pricing_shop
    with Session(s['engine']) as session:
        variant_id = s['variant'].ProductVariantId
        plan = plan_for(session, [variant_id])
        plan['Variants'][0]['MarketPrice'] = '30000000'
        plan['References'][0]['SalePrice'] = '30000000'
        result = apply_plan(session, plan, apply=True, folder=tmp_path)
        assert result['StatusCounts'] == {'price-floor-review': 1}
        assert result['UpdatedVariants'] == 0
        assert session.get(ProductVariant, variant_id).Price == 35000000
