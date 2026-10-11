"""Truy vấn tổng hợp chỉ đọc cho StatisticsService (đợt 5.6). Không ghi dữ liệu, không khóa dòng.

Quy ước chung:
- Khoảng thời gian nửa mở [start, end): gồm ``start``, KHÔNG gồm ``end`` (Service đổi ngày lịch Việt Nam sang UTC).
- Đơn ghi nhận doanh thu: OrderStatus IN (Delivered, Completed), DeliveredAt trong khoảng, và có ít nhất một giao dịch
  Payment Success. Payment/Refund được cộng theo từng đơn trong subquery TRƯỚC khi JOIN với Orders, nên một đơn có
  nhiều giao dịch không bị nhân bản dòng (không tính trùng).
- Chỉ Payment Success là tiền đã thu; chỉ Refund Success là tiền đã hoàn (Pending/Failed/Cancelled không tính).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import case, desc, exists, func, select
from sqlalchemy.orm import Session

from app.models import Order, OrderItem, PaymentTransaction, Product, ProductSerial, ProductVariant, ReturnRequest

REVENUE_ORDER_STATUSES = ("Delivered", "Completed")
TX_PAYMENT = "Payment"
TX_REFUND = "Refund"
TX_SUCCESS = "Success"
TX_PENDING = "Pending"
RETURN_TYPE = "Return"
RETURN_COMPLETED = "Completed"
_ZERO = Decimal("0")


class RevenueTotals(NamedTuple):
    order_count: int
    order_value: Decimal
    shipping_fee: Decimal
    collected: Decimal
    refunded: Decimal
    pending_refund: Decimal


class CogsTotals(NamedTuple):
    line_count: int
    unit_count: int
    known_cogs: Decimal
    lines_missing_cost: int


class TopProductRow(NamedTuple):
    product_variant_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    sku: str
    variant_name: str
    quantity: int
    revenue: Decimal


class InventoryRow(NamedTuple):
    product_variant_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    sku: str
    variant_name: str
    is_serial_tracked: bool
    stock_quantity: int
    min_stock_level: int


class StatisticsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------ đơn hàng

    def count_orders_by_status(self, start: datetime, end: datetime) -> dict[str, int]:
        """Số đơn theo OrderStatus, lọc theo OrderedAt trong [start, end)."""
        stmt = (
            select(Order.OrderStatus, func.count(Order.OrderId))
            .where(Order.OrderedAt >= start, Order.OrderedAt < end)
            .group_by(Order.OrderStatus)
        )
        return {status: int(count) for status, count in self.session.execute(stmt)}

    # ------------------------------------------------------------------ doanh thu

    @staticmethod
    def _transaction_totals(transaction_type: str, status: str):
        """Tổng tiền theo đơn của một loại giao dịch/trạng thái (một dòng mỗi OrderId)."""
        return (
            select(PaymentTransaction.OrderId.label("OrderId"), func.sum(PaymentTransaction.Amount).label("Amount"))
            .where(PaymentTransaction.TransactionType == transaction_type, PaymentTransaction.Status == status)
            .group_by(PaymentTransaction.OrderId)
            .subquery()
        )

    @staticmethod
    def _delivered_in(start: datetime, end: datetime) -> tuple:
        return (Order.OrderStatus.in_(REVENUE_ORDER_STATUSES), Order.DeliveredAt >= start, Order.DeliveredAt < end)

    @staticmethod
    def _has_successful_payment():
        return exists().where(
            PaymentTransaction.OrderId == Order.OrderId,
            PaymentTransaction.TransactionType == TX_PAYMENT,
            PaymentTransaction.Status == TX_SUCCESS,
        )

    def _revenue_order_ids(self, start: datetime, end: datetime):
        return select(Order.OrderId).where(*self._delivered_in(start, end), self._has_successful_payment())

    def revenue_totals(self, start: datetime, end: datetime) -> RevenueTotals:
        """Tổng giá trị đơn, tiền đã thu, đã hoàn, đang chờ hoàn của các đơn ghi nhận doanh thu trong khoảng."""
        paid = self._transaction_totals(TX_PAYMENT, TX_SUCCESS)
        refunded = self._transaction_totals(TX_REFUND, TX_SUCCESS)
        pending = self._transaction_totals(TX_REFUND, TX_PENDING)
        stmt = (
            select(
                func.count(Order.OrderId),
                func.coalesce(func.sum(Order.TotalAmount), 0),
                func.coalesce(func.sum(Order.ShippingFee), 0),
                func.coalesce(func.sum(paid.c.Amount), 0),
                func.coalesce(func.sum(refunded.c.Amount), 0),
                func.coalesce(func.sum(pending.c.Amount), 0),
            )
            .select_from(Order)
            .join(paid, paid.c.OrderId == Order.OrderId)  # INNER JOIN: chỉ đơn có Payment Success
            .outerjoin(refunded, refunded.c.OrderId == Order.OrderId)
            .outerjoin(pending, pending.c.OrderId == Order.OrderId)
            .where(*self._delivered_in(start, end))
        )
        count, value, shipping, collected, refunded_total, pending_total = self.session.execute(stmt).one()
        return RevenueTotals(int(count or 0), Decimal(value or _ZERO), Decimal(shipping or _ZERO),
                             Decimal(collected or _ZERO), Decimal(refunded_total or _ZERO), Decimal(pending_total or _ZERO))

    def count_delivered_without_payment(self, start: datetime, end: datetime) -> int:
        """Đơn đã giao trong khoảng nhưng chưa có Payment Success (không được tính doanh thu)."""
        stmt = select(func.count(Order.OrderId)).where(*self._delivered_in(start, end), ~self._has_successful_payment())
        return int(self.session.scalar(stmt) or 0)

    # ------------------------------------------------------------------ giá vốn

    def cogs_totals(self, start: datetime, end: datetime) -> CogsTotals:
        """Giá vốn theo snapshot OrderItems.UnitCost × Quantity của các đơn ghi nhận doanh thu; UnitCost = 0 = thiếu."""
        stmt = select(
            func.count(OrderItem.OrderItemId),
            func.coalesce(func.sum(OrderItem.Quantity), 0),
            func.coalesce(func.sum(case((OrderItem.UnitCost > 0, OrderItem.UnitCost * OrderItem.Quantity), else_=0)), 0),
            func.coalesce(func.sum(case((OrderItem.UnitCost == 0, 1), else_=0)), 0),
        ).where(OrderItem.OrderId.in_(self._revenue_order_ids(start, end)))
        lines, units, known, missing = self.session.execute(stmt).one()
        return CogsTotals(int(lines or 0), int(units or 0), Decimal(known or _ZERO), int(missing or 0))

    # ------------------------------------------------------------------ sản phẩm

    def top_products(self, start: datetime, end: datetime, *, rank_by: str, limit: int) -> list[TopProductRow]:
        """Biến thể bán chạy trong các đơn ghi nhận doanh thu: SL = Σ Quantity, doanh thu dòng = Σ LineTotal."""
        quantity = func.sum(OrderItem.Quantity).label("Quantity")
        revenue = func.sum(OrderItem.LineTotal).label("Revenue")
        primary, secondary = (quantity, revenue) if rank_by == "quantity" else (revenue, quantity)
        stmt = (
            select(ProductVariant.ProductVariantId, Product.ProductId, Product.Name, ProductVariant.Sku,
                   ProductVariant.VariantName, quantity, revenue)
            .select_from(OrderItem)
            .join(ProductVariant, ProductVariant.ProductVariantId == OrderItem.ProductVariantId)
            .join(Product, Product.ProductId == ProductVariant.ProductId)
            .where(OrderItem.OrderId.in_(self._revenue_order_ids(start, end)))
            .group_by(ProductVariant.ProductVariantId, Product.ProductId, Product.Name, ProductVariant.Sku,
                      ProductVariant.VariantName)
            .order_by(desc(primary), desc(secondary), ProductVariant.ProductVariantId)
            .limit(limit)
        )
        return [TopProductRow(v, p, name, sku, vname, int(q or 0), Decimal(r or _ZERO))
                for v, p, name, sku, vname, q, r in self.session.execute(stmt)]

    def returned_quantities(
        self, start: datetime, end: datetime, variant_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Số lượng đã trả lại (ReturnRequests Return đã Completed) của dòng đơn thuộc các đơn ghi nhận doanh thu."""
        if not variant_ids:
            return {}
        stmt = (
            select(OrderItem.ProductVariantId, func.sum(ReturnRequest.Quantity))
            .select_from(ReturnRequest)
            .join(OrderItem, OrderItem.OrderItemId == ReturnRequest.OrderItemId)
            .where(
                ReturnRequest.RequestType == RETURN_TYPE,
                ReturnRequest.Status == RETURN_COMPLETED,
                OrderItem.OrderId.in_(self._revenue_order_ids(start, end)),
                OrderItem.ProductVariantId.in_(variant_ids),
            )
            .group_by(OrderItem.ProductVariantId)
        )
        return {variant_id: int(total or 0) for variant_id, total in self.session.execute(stmt)}

    # ------------------------------------------------------------------ tồn kho

    def count_inventory_variants(self) -> int:
        return int(self.session.scalar(
            select(func.count(ProductVariant.ProductVariantId)).where(ProductVariant.IsDeleted.is_(False))) or 0)

    def list_inventory(self, *, offset: int, limit: int) -> list[InventoryRow]:
        """Biến thể chưa xóa với tồn khả dụng (StockQuantity) và ngưỡng cảnh báo."""
        stmt = (
            select(ProductVariant.ProductVariantId, Product.ProductId, Product.Name, ProductVariant.Sku,
                   ProductVariant.VariantName, ProductVariant.IsSerialTracked, ProductVariant.StockQuantity,
                   ProductVariant.MinStockLevel)
            .join(Product, Product.ProductId == ProductVariant.ProductId)
            .where(ProductVariant.IsDeleted.is_(False))
            .order_by(Product.Name, ProductVariant.Sku, ProductVariant.ProductVariantId)
            .offset(offset)
            .limit(limit)
        )
        return [InventoryRow(*row) for row in self.session.execute(stmt)]

    def stock_total(self) -> int:
        return int(self.session.scalar(
            select(func.coalesce(func.sum(ProductVariant.StockQuantity), 0)).where(ProductVariant.IsDeleted.is_(False)))
            or 0)

    def serial_status_counts(self, variant_ids: list[uuid.UUID] | None = None) -> dict[tuple[uuid.UUID, str], int]:
        """Số serial theo (biến thể, trạng thái) của biến thể chưa xóa; ``variant_ids`` để giới hạn trang hiện tại."""
        stmt = (
            select(ProductSerial.ProductVariantId, ProductSerial.Status, func.count(ProductSerial.ProductSerialId))
            .join(ProductVariant, ProductVariant.ProductVariantId == ProductSerial.ProductVariantId)
            .where(ProductVariant.IsDeleted.is_(False))
            .group_by(ProductSerial.ProductVariantId, ProductSerial.Status)
        )
        if variant_ids is not None:
            if not variant_ids:
                return {}
            stmt = stmt.where(ProductSerial.ProductVariantId.in_(variant_ids))
        return {(variant_id, status): int(count) for variant_id, status, count in self.session.execute(stmt)}

    def serial_status_totals(self) -> dict[str, int]:
        stmt = (
            select(ProductSerial.Status, func.count(ProductSerial.ProductSerialId))
            .join(ProductVariant, ProductVariant.ProductVariantId == ProductSerial.ProductVariantId)
            .where(ProductVariant.IsDeleted.is_(False))
            .group_by(ProductSerial.Status)
        )
        return {status: int(count) for status, count in self.session.execute(stmt)}
