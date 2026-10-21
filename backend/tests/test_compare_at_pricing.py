"""The stored list price is kept for reference only: a price is struck through only when a promotion lowers it."""
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import ProductVariant
from app.services import Actor, BusinessRuleError
from app.services.catalog import ProductVariantService
from app.schemas.catalog import ProductVariantUpdate
from tests.test_automatic_pricing import pricing_shop, program, coupon, preview  # noqa: F401
from tests.test_promotion_lifecycle import shop, ok  # noqa: F401


def set_prices(s, *, listed='34990000', sale='30990000'):
    with Session(s['engine']) as session:
        variant = session.get(ProductVariant, s['variant'].ProductVariantId)
        variant.Price = Decimal(sale)
        variant.CompareAtPrice = Decimal(listed)
        variant.CostPrice = Decimal('28000000')
        session.commit()


def test_without_a_promotion_the_list_price_is_not_struck_through(pricing_shop):
    s = pricing_shop
    set_prices(s)
    detail = ok(s['client'].get(f'/products/{s["variant"].ProductId}'))['Variants'][0]
    assert Decimal(detail['OriginalPrice']) == Decimal(detail['SalePrice']) == Decimal(detail['Price']) == 30990000
    assert Decimal(detail['DiscountAmount']) == Decimal(detail['DiscountPercent']) == 0
    quote = ok(preview(s, quantity=2))
    assert Decimal(quote['OriginalSubtotal']) == Decimal(quote['Total']) == 61980000
    assert Decimal(quote['AutomaticDiscount']) == 0
    assert 'CostPrice' not in detail


def test_extra_automatic_and_coupon_use_actual_selling_price(pricing_shop):
    s = pricing_shop
    set_prices(s)
    program(s, amount='1000000')
    coupon(s, amount='300000')
    quote = ok(preview(s, 'TEST300'))
    assert Decimal(quote['OriginalSubtotal']) == 30990000
    assert Decimal(quote['Subtotal']) == 29990000
    assert Decimal(quote['AutomaticDiscount']) == 1000000
    assert Decimal(quote['CouponDiscount']) == 300000
    assert Decimal(quote['Total']) == 29690000


def test_high_list_price_does_not_bypass_cost_floor_or_price_filter(pricing_shop):
    s = pricing_shop
    set_prices(s)
    program(s, amount='1000000')
    with Session(s['engine']) as session:
        session.get(ProductVariant, s['variant'].ProductVariantId).CostPrice = Decimal('30500000')
        session.commit()
    result = ok(s['client'].get('/products', params={'min_price': 30990000, 'max_price': 30990000}))
    assert result['Total'] == 1
    assert Decimal(ok(preview(s))['Total']) == 30990000
    assert ok(s['client'].get('/products', params={'min_price': 34990000}))['Total'] == 0


def test_admin_rejects_comparison_price_below_sale(pricing_shop):
    s = pricing_shop
    set_prices(s)
    with Session(s['engine']) as session:
        with pytest.raises(BusinessRuleError, match='niêm yết'):
            ProductVariantService(session).update_variant(Actor(s['admin'].UserId, 'Admin'),
                s['variant'].ProductVariantId, ProductVariantUpdate(CompareAtPrice=100))
