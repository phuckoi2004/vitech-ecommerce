from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import ProductVariant, Promotion
from scripts.apply_retail_prices_and_sample_costs import BATCH, run, sample_cost_reduction
from tests.test_automatic_pricing import pricing_shop, program  # noqa: F401
from tests.test_promotion_lifecycle import shop  # noqa: F401


@pytest.mark.parametrize('sale,reduction', [
    (99000, 50000), (499999, 50000), (500000, 100000), (1999999, 100000),
    (2000000, 300000), (5000000, 500000), (10000000, 1000000), (20000000, 1500000),
])
def test_cost_reduction_tiers(sale, reduction):
    assert sample_cost_reduction(sale) == reduction


def plan_for(session, variant_id):
    variant = session.get(ProductVariant, variant_id)
    product = variant.product
    return dict(Batch=BATCH, CancelTestPromotions=[], Variants=[dict(
        ProductId=str(product.ProductId), ProductVariantId=str(variant_id), ProductName=product.Name,
        Slug=product.Slug, Sku=variant.Sku, Color=variant.Color, Storage=variant.Storage,
        BeforePrice=str(variant.Price), BeforeListPrice=None, BeforeCostPrice=str(variant.CostPrice),
        SalePrice='30990000', ListPrice='34990000', CostPrice='29500000',
        Reference=dict(SalePrice='30990000', ListPrice='34990000',
                       CheckedAt=datetime.now(timezone.utc).isoformat(), SourceUrl='https://cellphones.com.vn/example.html'))])


def test_preview_never_changes_list_sale_or_cost(pricing_shop):
    s = pricing_shop
    with Session(s['engine']) as session:
        plan = plan_for(session, s['variant'].ProductVariantId)
        report = run(session, plan)
        session.expire_all()
        variant = session.get(ProductVariant, s['variant'].ProductVariantId)
        assert (variant.Price, variant.CompareAtPrice, variant.CostPrice) == (35000000, None, 31000000)
        assert report['Rows'][0]['DiscountPercent'] == '0.00'  # a list price alone shows no discount to customers
        assert report['CostChanges'] == 1 and variant.StockQuantity == 10


def test_apply_is_atomic_and_cost_is_lowered_only_once(pricing_shop, tmp_path):
    s = pricing_shop
    p = program(s, Name='[TEST] public-pricing-test-v1 correction fixture')
    with Session(s['engine']) as session:
        plan = plan_for(session, s['variant'].ProductVariantId)
        plan['CancelTestPromotions'] = [dict(PromotionId=p['PromotionId'], Name=p['Name'])]
        first = run(session, plan, apply=True, folder=tmp_path)
        assert first['CancelledTestPromotions'] == 1 and first['CostChanges'] == 1
        session.expire_all()
        variant = session.get(ProductVariant, s['variant'].ProductVariantId)
        assert (variant.Price, variant.CompareAtPrice, variant.CostPrice) == (30990000, 34990000, 29500000)
        assert variant.StockQuantity == 10
        import uuid
        assert session.get(Promotion, uuid.UUID(p['PromotionId'])).Status == 'Cancelled'
        second = run(session, plan, apply=True, folder=tmp_path)
        assert second['Changes'] == 0 and second['CancelledTestPromotions'] == 0
        assert variant.CostPrice == 29500000


def test_stale_cost_aborts_before_any_mutation(pricing_shop):
    s = pricing_shop
    with Session(s['engine']) as session:
        plan = plan_for(session, s['variant'].ProductVariantId)
        variant = session.get(ProductVariant, s['variant'].ProductVariantId)
        variant.CostPrice -= 1000
        session.commit()
        with pytest.raises(ValueError, match='changed after review'):
            run(session, plan, apply=True)
        session.expire_all()
        assert session.get(ProductVariant, s['variant'].ProductVariantId).CompareAtPrice is None


def test_cannot_cancel_coupon_or_other_business_program(pricing_shop):
    s = pricing_shop
    p = program(s, Name='Chương trình khác')
    with Session(s['engine']) as session:
        plan = plan_for(session, s['variant'].ProductVariantId)
        plan['CancelTestPromotions'] = [dict(PromotionId=p['PromotionId'], Name=p['Name'])]
        with pytest.raises(ValueError, match='earlier test automatic'):
            run(session, plan, apply=True)
