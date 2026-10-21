"""Repositories cho ShippingMethods, Orders, OrderItems, OrderStatusHistories.

Không tính tiền, không đổi trạng thái, không kiểm tra quyền.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload, selectinload

from app.models import Order, OrderItem, OrderStatusHistory, PaymentMethod, ProductVariant, ShippingMethod, User

from .base import BaseRepository


class ShippingMethodRepository(BaseRepository[ShippingMethod]):
    model = ShippingMethod

    def get_by_code(self, code: str) -> ShippingMethod | None:
        return self.get_one(ShippingMethod.Code == code)

    def exists_by_code(self, code: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [ShippingMethod.Code == code]
        if exclude_id is not None:
            conditions.append(ShippingMethod.ShippingMethodId != exclude_id)
        return self.exists(*conditions)

    def list_methods(self, *, is_active: bool | None = None) -> list[ShippingMethod]:
        conditions = [] if is_active is None else [ShippingMethod.IsActive.is_(is_active)]
        return self.get_all(*conditions, order_by=(ShippingMethod.BaseFee, ShippingMethod.Name))


class OrderRepository(BaseRepository[Order]):
    model = Order

    def exists_by_shipping_method(self, shipping_method_id: uuid.UUID) -> bool:
        """Có đơn hàng (mọi trạng thái) tham chiếu phương thức vận chuyển (FK RESTRICT)."""
        return self.exists(Order.ShippingMethodId == shipping_method_id)

    def get_by_code(self, order_code: str) -> Order | None:
        return self.get_one(Order.OrderCode == order_code)

    def exists_by_code(self, order_code: str) -> bool:
        return self.exists(Order.OrderCode == order_code)

    def customer_used_coupon(self, customer_id: uuid.UUID, coupon_id: uuid.UUID) -> bool:
        """Khách đã có đơn chưa hủy dùng coupon này."""
        return self.exists(Order.CustomerId == customer_id, Order.CouponId == coupon_id, Order.OrderStatus != "Cancelled")

    def get_by_id_and_customer(self, order_id: uuid.UUID, customer_id: uuid.UUID) -> Order | None:
        return self.get_one(Order.OrderId == order_id, Order.CustomerId == customer_id)

    def get_detail(self, order_id: uuid.UUID) -> Order | None:
        """Order kèm Items và StatusHistories (cho OrderDetailResponse)."""
        stmt = (
            select(Order)
            .where(Order.OrderId == order_id)
            .options(
                selectinload(Order.items).selectinload(OrderItem.product_variant),
                selectinload(Order.items).selectinload(OrderItem.review),
                selectinload(Order.status_histories),
            )
        )
        return self.session.scalars(stmt).one_or_none()

    def _filters(
        self,
        customer_id: uuid.UUID | None,
        assigned_staff_id: uuid.UUID | None,
        order_status: str | Sequence[str] | None,
        payment_status: str | None,
        ordered_from: datetime | None,
        ordered_to: datetime | None,
        order_code_contains: str | None = None,
        keyword: str | None = None,
        product_id: uuid.UUID | None = None,
    ) -> list:
        conditions = []
        if keyword:
            escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            conditions.append(or_(
                Order.OrderCode.ilike(pattern, escape="\\"),
                Order.customer.has(or_(
                    User.FullName.ilike(pattern, escape="\\"),
                    User.PhoneNumber.ilike(pattern, escape="\\"),
                )),
            ))
        if product_id is not None:
            # Đơn có ít nhất một dòng thuộc sản phẩm này (qua biến thể).
            conditions.append(Order.OrderId.in_(
                select(OrderItem.OrderId)
                .join(ProductVariant, ProductVariant.ProductVariantId == OrderItem.ProductVariantId)
                .where(ProductVariant.ProductId == product_id)
            ))
        if order_code_contains:
            # Tìm theo mã đơn, không phân biệt hoa thường; escape ký tự đặc biệt của LIKE.
            escaped = order_code_contains.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append(Order.OrderCode.ilike(f"%{escaped}%", escape="\\"))
        if customer_id is not None:
            conditions.append(Order.CustomerId == customer_id)
        if assigned_staff_id is not None:
            conditions.append(Order.AssignedStaffId == assigned_staff_id)
        if isinstance(order_status, str):
            conditions.append(Order.OrderStatus == order_status)
        elif order_status:
            conditions.append(Order.OrderStatus.in_(order_status))
        if payment_status is not None:
            conditions.append(Order.PaymentStatus == payment_status)
        if ordered_from is not None:
            conditions.append(Order.OrderedAt >= ordered_from)
        if ordered_to is not None:
            conditions.append(Order.OrderedAt < ordered_to)
        return conditions

    def list_orders(
        self,
        *,
        customer_id: uuid.UUID | None = None,
        assigned_staff_id: uuid.UUID | None = None,
        order_status: str | Sequence[str] | None = None,
        payment_status: str | None = None,
        ordered_from: datetime | None = None,
        ordered_to: datetime | None = None,
        order_code_contains: str | None = None,
        keyword: str | None = None,
        product_id: uuid.UUID | None = None,
        offset: int | None = None,
        limit: int | None = None,
        with_items: bool = False,
    ) -> list[Order]:
        """ordered_from bao gồm, ordered_to không bao gồm (khoảng [from, to)); order_status một hoặc nhiều giá trị.

        product_id: đơn có dòng thuộc sản phẩm này. with_items: nạp sẵn Items kèm biến thể, sản phẩm và review
        (CustomerOrderSummary).
        """
        options = (
            (selectinload(Order.items).selectinload(OrderItem.product_variant).selectinload(ProductVariant.product),
             selectinload(Order.items).selectinload(OrderItem.review))
            if with_items else ()
        )
        return self.get_all(
            *self._filters(
                customer_id, assigned_staff_id, order_status, payment_status, ordered_from, ordered_to, order_code_contains,
                keyword=keyword, product_id=product_id,
            ),
            order_by=(Order.OrderedAt.desc(), Order.OrderId),
            offset=offset,
            limit=limit,
            options=options,
        )

    def count_orders(
        self,
        *,
        customer_id: uuid.UUID | None = None,
        assigned_staff_id: uuid.UUID | None = None,
        order_status: str | Sequence[str] | None = None,
        payment_status: str | None = None,
        ordered_from: datetime | None = None,
        ordered_to: datetime | None = None,
        order_code_contains: str | None = None,
        keyword: str | None = None,
        product_id: uuid.UUID | None = None,
    ) -> int:
        return self.count(
            *self._filters(
                customer_id, assigned_staff_id, order_status, payment_status, ordered_from, ordered_to, order_code_contains,
                keyword=keyword, product_id=product_id,
            )
        )

    def list_expired_unpaid_order_ids(
        self,
        *,
        ordered_before: datetime,
        order_status: str,
        payment_statuses: tuple[str, ...],
        excluded_payment_method_code: str,
        limit: int,
    ) -> list[uuid.UUID]:
        """Id các đơn chưa thanh toán đã quá hạn (OrderedAt <= ordered_before), trừ phương thức ``excluded_payment_method_code``.

        Không khóa dòng; Service khóa từng đơn và kiểm tra lại điều kiện trước khi xử lý.
        """
        stmt = (
            select(Order.OrderId)
            .join(PaymentMethod, PaymentMethod.PaymentMethodId == Order.PaymentMethodId)
            .where(
                Order.OrderStatus == order_status,
                Order.PaymentStatus.in_(payment_statuses),
                Order.OrderedAt <= ordered_before,
                PaymentMethod.Code != excluded_payment_method_code,
            )
            .order_by(Order.OrderedAt, Order.OrderId)
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def list_by_customer(
        self, customer_id: uuid.UUID, *, offset: int | None = None, limit: int | None = None
    ) -> list[Order]:
        return self.list_orders(customer_id=customer_id, offset=offset, limit=limit)


class OrderItemRepository(BaseRepository[OrderItem]):
    model = OrderItem

    def list_by_order(self, order_id: uuid.UUID) -> list[OrderItem]:
        return self.get_all(OrderItem.OrderId == order_id, order_by=(OrderItem.ProductName, OrderItem.OrderItemId))

    def get_with_order(self, order_item_id: uuid.UUID) -> OrderItem | None:
        """OrderItem kèm Order (Service dùng để kiểm tra khách hàng/trạng thái đơn)."""
        stmt = select(OrderItem).where(OrderItem.OrderItemId == order_item_id).options(joinedload(OrderItem.order))
        return self.session.scalars(stmt).one_or_none()

    def get_by_id_and_customer(self, order_item_id: uuid.UUID, customer_id: uuid.UUID) -> OrderItem | None:
        """OrderItem thuộc một đơn của khách hàng (JOIN Orders)."""
        stmt = (
            select(OrderItem)
            .join(OrderItem.order)
            .where(OrderItem.OrderItemId == order_item_id, Order.CustomerId == customer_id)
        )
        return self.session.scalars(stmt).one_or_none()

    def exists_by_id(self, order_item_id: uuid.UUID) -> bool:
        return self.exists(OrderItem.OrderItemId == order_item_id)


class OrderStatusHistoryRepository(BaseRepository[OrderStatusHistory]):
    model = OrderStatusHistory

    def list_by_order(self, order_id: uuid.UUID) -> list[OrderStatusHistory]:
        return self.get_all(
            OrderStatusHistory.OrderId == order_id,
            order_by=(OrderStatusHistory.ChangedAt, OrderStatusHistory.OrderStatusHistoryId),
        )
