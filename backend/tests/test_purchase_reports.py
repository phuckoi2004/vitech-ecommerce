"""Exercise purchase reports through the HTTP API and real SQL aggregation."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import insert, select, update

from app.models import ProductVariant, PurchaseOrder, PurchaseOrderItem, PurchaseReceipt, PurchaseReceiptItem, StockAdjustment, Supplier
from tests.test_statistics_reports import PERIOD, fetch, reports  # noqa: F401 (shared fixture)


@pytest.fixture
def purchases(reports):
    client, current, actors, first, other, statements = reports
    engine = current['engine']
    supplier, inactive = uuid.uuid4(), uuid.uuid4()
    timestamp = datetime(2026, 10, 1, tzinfo=timezone.utc)
    with engine.begin() as connection:
        for key, name, active in ((supplier, 'Supplier A', True), (inactive, 'Supplier B', False)):
            connection.execute(insert(Supplier).values(SupplierId=key, SupplierCode=str(key), Name=name,
                PhoneNumber='0900000000', Address='Address', IsActive=active))
        sibling = connection.execute(select(ProductVariant.ProductVariantId).where(
            ProductVariant.ProductId == first.ProductId,
            ProductVariant.ProductVariantId != first.ProductVariantId)).scalar_one()

        def order(code, status, lines, *, source=supplier, created=timestamp):
            key = uuid.uuid4()
            connection.execute(insert(PurchaseOrder).values(PurchaseOrderId=key, PurchaseOrderCode=code,
                SupplierId=source, CreatedByUserId=actors[1].user_id, Status=status,
                CreatedAt=created, TotalAmount=sum(Decimal(price) * qty for _, qty, _, price in lines),
                ClosedAt=timestamp if status == 'Closed' else None,
                CloseReason='Delivery shortage' if status == 'Closed' else None))
            for variant, qty, received, price in lines:
                connection.execute(insert(PurchaseOrderItem).values(PurchaseOrderItemId=uuid.uuid4(),
                    PurchaseOrderId=key, ProductVariantId=variant, OrderedQuantity=qty,
                    ReceivedQuantity=received, UnitPrice=Decimal(price), LineTotal=Decimal(price) * qty))
            return key

        order('PO-RECEIVING', 'Receiving', [(first.ProductVariantId, 3, 1, '10'), (sibling, 2, 1, '20'), (other.ProductVariantId, 5, 0, '30')])
        order('PO-COMPLETED', 'Completed', [(other.ProductVariantId, 2, 2, '40')], source=inactive,
            created=datetime(2026, 9, 30, 17, tzinfo=timezone.utc))
        order('PO-CLOSED', 'Closed', [(first.ProductVariantId, 4, 2, '15')])
        order('PO-CANCELLED', 'Cancelled', [(first.ProductVariantId, 10, 0, '1000')])
        order('PO-REJECTED', 'Rejected', [(other.ProductVariantId, 20, 0, '1000')])
        order('PO-PENDING', 'Pending', [(first.ProductVariantId, 1, 0, '5')])
        order('PO-APPROVED', 'Approved', [(other.ProductVariantId, 1, 0, '25')])
        order('PO-OUTSIDE', 'Completed', [(first.ProductVariantId, 100, 100, '100')],
            created=datetime(2026, 9, 30, 16, 59, 59, tzinfo=timezone.utc))
        order('PO-NOVEMBER', 'Pending', [(first.ProductVariantId, 2, 0, '7')],
            created=datetime(2026, 10, 31, 17, tzinfo=timezone.utc))
    statements.clear()
    return reports, supplier, inactive


def test_counts_each_purchase_once_and_keeps_planned_amount_separate_from_received(purchases):
    (client, _, _, _, _, statements), _, _ = purchases
    result = fetch(client, 'purchases')
    assert result['Total'] == 7
    summary = result['Summary']
    assert summary == dict(TotalOrders=7, InProgressOrders=3, CompletedOrders=1, ClosedOrders=1,
        CancelledOrders=1, RejectedOrders=1, OrderedQuantity=18, ReceivedQuantity=6, OrderedAmount='390.00')
    assert len(result['Chart']) == 31
    assert result['Chart'][0]['TotalOrders'] == 7
    assert sum(row['TotalOrders'] for row in result['Chart']) == 7
    assert all(row['TotalOrders'] == 0 for row in result['Chart'][1:])
    assert len({row['PurchaseOrderId'] for row in result['Items']}) == 7
    received = next(row for row in result['Items'] if row['PurchaseOrderCode'] == 'PO-RECEIVING')
    assert (received['OrderedQuantity'], received['ReceivedQuantity'], Decimal(received['OrderedAmount'])) == (10, 2, Decimal('220'))
    assert all(sql.lstrip().upper().startswith('SELECT') for sql in statements)


def test_supplier_and_product_filters_combine_without_duplicate_counts(purchases):
    (client, _, _, first, other, _), supplier, inactive = purchases
    result = fetch(client, 'purchases', supplier_id=str(supplier), product_id=str(first.ProductId))
    assert result['Total'] == 4
    assert result['Summary']['OrderedQuantity'] == 10  # cancelled lines excluded
    assert result['Summary']['ReceivedQuantity'] == 4
    assert Decimal(result['Summary']['OrderedAmount']) == Decimal('135')
    assert all(row['SupplierId'] == str(supplier) for row in result['Items'])
    assert len(result['Suppliers']) == 1
    mismatch = fetch(client, 'purchases', supplier_id=str(inactive), product_id=str(first.ProductId))
    assert mismatch['Total'] == 0 and mismatch['Items'] == []
    mismatch = fetch(client, 'purchases', category_id=str(first.product.CategoryId), brand_id=str(other.product.BrandId))
    assert mismatch['Total'] == 0
    assert fetch(client, 'purchases', category_id=str(first.product.CategoryId))['Summary']['OrderedQuantity'] == 10
    assert fetch(client, 'purchases', brand_id=str(first.product.BrandId))['Summary']['ReceivedQuantity'] == 4


def test_pagination_and_supplier_breakdown_cover_full_period_and_keep_inactive_suppliers(purchases):
    (client, _, _, _, _, statements), supplier, inactive = purchases
    first = fetch(client, 'purchases', page_size=2)
    second = fetch(client, 'purchases', page_size=2, page=2)
    assert first['Total'] == second['Total'] == 7
    assert len(first['Items']) == len(second['Items']) == 2
    assert first['Items'] == fetch(client, 'purchases', page_size=2)['Items']
    assert set(row['PurchaseOrderId'] for row in first['Items']).isdisjoint(row['PurchaseOrderId'] for row in second['Items'])
    assert first['Summary'] == second['Summary'] and first['Chart'] == second['Chart']
    assert first['Suppliers'] == second['Suppliers']
    assert [(row['SupplierId'], Decimal(row['OrderedAmount'])) for row in first['Suppliers']] == [(str(supplier), Decimal('310')), (str(inactive), Decimal('80'))]
    assert fetch(client, 'purchases', page=5, page_size=2)['Items'] == []
    options = client.get('/admin/statistics/report-options').json()['Suppliers']
    assert {row['Id'] for row in options} == {str(supplier), str(inactive)}
    assert all(set(row) == {'Id', 'Name'} for row in options)
    assert any('LIMIT' in sql and 'OFFSET' in sql for sql in statements)


def test_vietnam_creation_cohort_and_monthly_buckets(purchases):
    (client, current, _, _, _, _), _, _ = purchases
    daily = fetch(client, 'purchases', date_to='2026-10-01')
    assert daily['Total'] == 7 and len(daily['Chart']) == 1
    monthly = fetch(client, 'purchases', date_to='2026-11-30')
    assert [row['TotalOrders'] for row in monthly['Chart']] == [7, 1]
    assert monthly['Total'] == 8
    empty = fetch(client, 'purchases', date_from='2026-12-01', date_to='2026-12-31')
    assert empty['Total'] == 0 and empty['Items'] == [] and empty['Suppliers'] == []
    assert all(row['OrderedQuantity'] == row['TotalOrders'] == 0 for row in empty['Chart'])
    # Received quantities reflect current cumulative state, including receipts after the selected creation period.
    with current['engine'].begin() as connection:
        connection.execute(update(PurchaseOrderItem).values(ReceivedQuantity=PurchaseOrderItem.OrderedQuantity))
    assert fetch(client, 'purchases')['Summary']['ReceivedQuantity'] == 18


def test_purchase_report_authorization_and_query_validation(purchases):
    (client, current, actors, _, _, _), _, _ = purchases
    for actor in actors[1:]:
        current['actor'] = actor
        assert fetch(client, 'purchases')['Total'] == 7
    current['actor'] = actors[0]
    assert client.get('/admin/statistics/reports/purchases', params=PERIOD).status_code == 403
    current['actor'] = actors[1]
    for query in ({'supplier_id': 'bad'}, {'category_id': 'bad'}, {'page': 0}, {'page_size': 101}, {'date_from': 'bad'}):
        assert client.get('/admin/statistics/reports/purchases', params={**PERIOD, **query}).status_code == 422
    for query in ({'date_to': '2026-09-01'}, {'date_to': '2028-10-31'}):
        assert client.get('/admin/statistics/reports/purchases', params={**PERIOD, **query}).status_code == 400


def test_sales_quantities_use_actual_receipt_dates_and_current_stock_without_multiplying_sales(purchases):
    (client, current, actors, first, other, statements), _, _ = purchases
    with current['engine'].begin() as connection:
        old = connection.execute(select(PurchaseOrderItem.PurchaseOrderItemId, PurchaseOrderItem.PurchaseOrderId)
            .join(PurchaseOrder).where(PurchaseOrder.PurchaseOrderCode == 'PO-OUTSIDE')).one()
        receiving = connection.execute(select(PurchaseOrderItem.PurchaseOrderItemId, PurchaseOrderItem.PurchaseOrderId)
            .join(PurchaseOrder).where(PurchaseOrder.PurchaseOrderCode == 'PO-RECEIVING',
                PurchaseOrderItem.ProductVariantId != other.ProductVariantId)).all()
        for line, day, qty in [(old, datetime(2026, 9, 30, 16, 59, 59, tzinfo=timezone.utc), 2),
                (old, datetime(2026, 9, 30, 17, tzinfo=timezone.utc), 5),
                (old, datetime(2026, 10, 31, 17, tzinfo=timezone.utc), 93),
                *[(line, datetime(2026, 10, 20, tzinfo=timezone.utc), 1) for line in receiving]]:
            receipt_id = uuid.uuid4()
            connection.execute(insert(PurchaseReceipt).values(PurchaseReceiptId=receipt_id,
                PurchaseOrderId=line.PurchaseOrderId, ReceivedByUserId=actors[1].user_id, ReceivedAt=day))
            connection.execute(insert(PurchaseReceiptItem).values(PurchaseReceiptId=receipt_id,
                PurchaseOrderItemId=line.PurchaseOrderItemId, Quantity=qty, UnitPrice=10))
        connection.execute(update(ProductVariant).values(StockQuantity=7))
        connection.execute(update(ProductVariant).where(ProductVariant.ProductVariantId == first.ProductVariantId).values(StockQuantity=11))
        connection.execute(update(ProductVariant).where(ProductVariant.ProductVariantId == other.ProductVariantId).values(StockQuantity=9))
    statements.clear()
    result = fetch(client, 'revenue')
    row = next(row for row in result['Items'] if row['ProductId'] == str(first.ProductId))
    assert (row['ReceivedQuantity'], row['Quantity'], row['StockQuantity']) == (7, 3, 18)
    assert Decimal(row['Revenue']) == Decimal('245')
    assert Decimal(result['Summary']['Revenue']) == Decimal('445')
    other_row = next(row for row in result['Items'] if row['ProductId'] == str(other.ProductId))
    assert (other_row['ReceivedQuantity'], other_row['Quantity'], other_row['StockQuantity']) == (0, 1, 9)
    variants = fetch(client, 'revenue', group_by='variant')
    assert variants['Total'] == 3
    assert variants['Summary'] == result['Summary'] and variants['TopProducts'] == result['TopProducts']
    first_variant = next(row for row in variants['Items'] if row['ProductVariantId'] == str(first.ProductVariantId))
    sibling_variant = next(row for row in variants['Items'] if row['ProductId'] == str(first.ProductId) and row['ProductVariantId'] != str(first.ProductVariantId))
    assert (first_variant['ReceivedQuantity'], first_variant['Quantity'], first_variant['StockQuantity']) == (6, 2, 11)
    assert (sibling_variant['ReceivedQuantity'], sibling_variant['Quantity'], sibling_variant['StockQuantity']) == (1, 1, 7)
    assert first_variant['Sku'] == first.Sku and first_variant['VariantName'] == first.VariantName
    assert Decimal(first_variant['Revenue']) == Decimal('195')
    variant_pages = [fetch(client, 'revenue', group_by='variant', page_size=1, page=page) for page in (1, 2, 3)]
    assert len({page['Items'][0]['Key'] for page in variant_pages}) == 3
    assert all(page['Total'] == 3 and page['Summary'] == variants['Summary'] for page in variant_pages)
    filtered_variants = fetch(client, 'revenue', group_by='variant', product_id=str(first.ProductId))
    assert filtered_variants['Total'] == 2
    lines = client.get('/admin/statistics/reports/revenue/lines', params={**PERIOD,
        'product_id': str(first.ProductId), 'variant_id': str(first.ProductVariantId)}).json()
    assert lines['Total'] == 1 and lines['Items'][0]['Sku'] == first.Sku
    mismatch = client.get('/admin/statistics/reports/revenue/lines', params={**PERIOD,
        'product_id': str(first.ProductId), 'variant_id': str(other.ProductVariantId)})
    assert mismatch.status_code == 200 and mismatch.json()['Total'] == 0
    page = fetch(client, 'revenue', page=2, page_size=1)
    assert page['TopProducts'] == result['TopProducts']
    filtered = fetch(client, 'revenue', product_id=str(first.ProductId), brand_id=str(first.product.BrandId))
    assert filtered['Items'][0] == row
    day = fetch(client, 'revenue', product_id=str(first.ProductId), date_to='2026-10-01')
    assert day['Items'][0]['ReceivedQuantity'] == 5
    assert all(sql.lstrip().upper().startswith('SELECT') for sql in statements)
    with current['engine'].begin() as connection:
        connection.execute(update(ProductVariant).where(ProductVariant.ProductId == first.ProductId,
            ProductVariant.ProductVariantId != first.ProductVariantId).values(IsDeleted=True, StockQuantity=999))
    updated = fetch(client, 'revenue', product_id=str(first.ProductId))['Items'][0]
    assert updated['StockQuantity'] == 11 and updated['ReceivedQuantity'] == 7


def test_sales_imported_quantity_includes_opening_once_before_period_end(purchases):
    (client, current, actors, first, other, statements), _, _ = purchases
    with current['engine'].begin() as connection:
        sibling = connection.execute(select(ProductVariant.ProductVariantId).where(
            ProductVariant.ProductId == first.ProductId,
            ProductVariant.ProductVariantId != first.ProductVariantId)).scalar_one()
        for variant, before, after, day in [
                (first.ProductVariantId, 2, 10, datetime(2026, 9, 1, tzinfo=timezone.utc)),
                (sibling, 0, 4, datetime(2026, 10, 1, tzinfo=timezone.utc)),
                (other.ProductVariantId, 0, 50, datetime(2026, 10, 31, 17, tzinfo=timezone.utc))]:
            connection.execute(insert(StockAdjustment).values(StockAdjustmentId=uuid.uuid4(),
                ProductVariantId=variant, AdjustedByUserId=actors[2].user_id, AdjustmentType='Opening',
                QuantityBefore=before, QuantityAfter=after, QuantityChange=after-before,
                CostPriceBefore=10, CostPriceAfter=10, Reason='Opening stock', CreatedAt=day))
        line = connection.execute(select(PurchaseOrderItem.PurchaseOrderItemId, PurchaseOrderItem.PurchaseOrderId)
            .join(PurchaseOrder).where(PurchaseOrder.PurchaseOrderCode == 'PO-RECEIVING',
                PurchaseOrderItem.ProductVariantId == first.ProductVariantId)).one()
        for day in [datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 20, tzinfo=timezone.utc)]:
            receipt_id = uuid.uuid4()
            connection.execute(insert(PurchaseReceipt).values(PurchaseReceiptId=receipt_id,
                PurchaseOrderId=line.PurchaseOrderId, ReceivedByUserId=actors[1].user_id, ReceivedAt=day))
            connection.execute(insert(PurchaseReceiptItem).values(PurchaseReceiptId=receipt_id,
                PurchaseOrderItemId=line.PurchaseOrderItemId, Quantity=1, UnitPrice=10))
    statements.clear()
    result = fetch(client, 'revenue')
    first_row = next(row for row in result['Items'] if row['ProductId'] == str(first.ProductId))
    other_row = next(row for row in result['Items'] if row['ProductId'] == str(other.ProductId))
    assert first_row['ReceivedQuantity'] == 16  # 10 + 4 opening, two actual receipts; no join multiplication.
    assert first_row['Quantity'] == 3 and Decimal(first_row['Revenue']) == Decimal('245')
    assert other_row['ReceivedQuantity'] == 0  # A future opening must not enter October's report.
    variants = fetch(client, 'revenue', group_by='variant', product_id=str(first.ProductId))
    counts = {row['ProductVariantId']: row['ReceivedQuantity'] for row in variants['Items']}
    assert counts == {str(first.ProductVariantId): 12, str(sibling): 4}
    day = fetch(client, 'revenue', product_id=str(first.ProductId), date_to='2026-10-01')
    assert day['Items'][0]['ReceivedQuantity'] == 15
    filtered = fetch(client, 'revenue', product_id=str(first.ProductId), brand_id=str(first.product.BrandId))
    assert filtered['Items'][0] == first_row
    assert fetch(client, 'revenue', page_size=1, page=2)['TopProducts'] == result['TopProducts']
    assert all(sql.lstrip().upper().startswith('SELECT') for sql in statements)
