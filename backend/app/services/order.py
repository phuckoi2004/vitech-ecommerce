"""Order service: đặt hàng, xem/tìm đơn, hủy đơn, xử lý trạng thái và lịch sử trạng thái.

Nguồn nghiệp vụ: docs/business-requirements.md mục 5 (Coupon), 6 (Đặt hàng), 7 (Xử lý đơn), 17 (Transaction).
Quyết định đã chốt:
- Coupon chỉ giảm trên các dòng thuộc Product/Category được gán cho Promotion (Promotion không gán
  gì = toàn đơn); tiền giảm phân bổ theo tỷ lệ vào OrderItems.DiscountAmount.
- Customer chỉ tự hủy khi đơn Pending.
- Staff/Admin chuyển trạng thái tuần tự từng bước; Cancelled chỉ trước Delivered
  (sau Delivered dùng ReturnRequest).
- Hủy đơn trước Shipping (hàng còn trong kho): hoàn tồn kho, nhả Serial/IMEI đang giữ ngay.
  Hủy khi đang Shipping (giao thất bại, hàng ở bên vận chuyển): KHÔNG hoàn tồn; mở hồ sơ ShipmentReturns chờ hàng
  quay về; Staff nhận lại và kiểm tra (``receive_shipment_return``): hàng đạt mới nhập lại tồn (serial Available),
  hàng hỏng không nhập tồn (serial Returned, không tự WrittenOff). Trả lượt coupon trong cả hai trường hợp.
  PaymentStatus chưa thanh toán (Pending/Failed) → Cancelled; đã Paid giữ nguyên (chưa hoàn), báo Staff/Admin và
  đơn nằm trong danh sách chờ hoàn tiền (PaymentService.list_orders_awaiting_refund).
  Mọi đường hủy (khách, Staff/Admin, hết hạn QR): yêu cầu thanh toán QR còn Pending → Cancelled (đợt 5.13), giữ mã
  cổng/QrData để đối soát. Việc này KHÔNG ngăn được khách vẫn chuyển khoản: tiền đến sau vẫn được PaymentService
  ghi nhận (Success + đối soát PaymentAfterCancellation, đơn giữ Cancelled), không tự hoàn tiền.
- COD: chỉ ghi nhận Paid khi Staff/Admin xác nhận giao hàng thành công VÀ đã thu tiền
  (``confirm_cod_delivery``: Shipping → Delivered, PaymentStatus Paid, PaymentTransaction Payment/Success
  trong cùng transaction). Chuyển trạng thái thông thường không được đưa đơn COD sang Delivered.
  Phương thức khác COD: phải Paid mới được chuyển Shipping
  (PaymentStatus Paid do PaymentService ghi nhận khi có xác nhận thanh toán).
- Serial/IMEI: KHÔNG tự chọn serial. Khi đóng gói (Processing), Staff quét/chọn serial của thiết bị thực tế
  (``assign_order_serials``: Available → Reserved, gắn OrderItemId; ``release_order_serial`` gỡ serial gán nhầm);
  chỉ chuyển Shipping khi mọi dòng quản lý serial đã gán đủ. Delivered → Sold + thời hạn bảo hành theo
  ``warranty_period``: bắt đầu = ngày lịch Việt Nam của thời điểm Delivered (UTC), hết hạn = bắt đầu + WarrantyMonths
  (OrderItems, chụp lúc mua) − 1 ngày (vượt cuối tháng đích thì lấy ngày cuối tháng); 0 tháng = không bảo hành.
- Completed → cập nhật Users.TotalSpent/TotalOrders và Products.SoldQuantity (số liệu lịch sử theo giá trị đơn, cộng
  một lần; trả hàng/hoàn tiền không điều chỉnh — chưa có quyết định về số liệu thuần).
  Không chuyển Completed khi đơn còn yêu cầu đổi/trả đang xử lý (RETURN_OPEN_STATUSES, đợt 5.9); ReturnService khóa
  Order trước khi tạo/chuyển trạng thái yêu cầu nên kiểm tra dưới khóa Order là nhất quán.
Quyền: thao tác Staff/Admin nhận Actor (do Router dựng từ JWT) và kiểm tra role tại Service;
thao tác của Customer kiểm tra quyền sở hữu đơn.
"""

import secrets
import string
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Order, OrderItem, Product, ProductVariant, User
from app.models.order import ORDER_STATUSES
from app.models.shipment import SHIPMENT_RETURN_AWAITING, SHIPMENT_RETURN_RECEIVED, SHIPMENT_RETURN_STATUSES
from app.repositories import (
    AddressRepository,
    CartItemRepository,
    CartRepository,
    OrderItemRepository,
    OrderRepository,
    OrderStatusHistoryRepository,
    PaymentMethodRepository,
    PaymentTransactionRepository,
    ProductRepository,
    ProductSerialRepository,
    ReturnRequestRepository,
    ShipmentReturnItemRepository,
    ShipmentReturnRepository,
    ProductVariantRepository,
    ShippingMethodRepository,
    UserRepository,
)
from app.schemas import (
    AdminOrderDetailResponse,
    AdminOrderResponse,
    AdminOrderStatusHistoryResponse,
    OrderAdminUpdate,
    OrderCancelRequest,
    OrderCreate,
    OrderDetailResponse,
    OrderItemResponse,
    OrderStatusHistoryResponse,
    OrderStatusUpdate,
    OrderSummary,
    PageResponse,
    ShipmentReturnReceive,
    ShipmentReturnResponse,
    OrderItemSerialsResponse,
    OrderSerialAssign,
)

from .actor import ADMIN_ONLY, CUSTOMER_ONLY, STAFF_OR_ADMIN, Actor, require_role
from .base import BaseService, utc_now
from .catalog import ProductVariantService, is_variant_sellable, normalize_serial_number
from .exceptions import BusinessRuleError, NotFoundError
from .promotion import CouponService, money as _money
from .user import NotificationService
from .warranty_period import delivery_warranty_period, vietnam_date

ORDER_PENDING = "Pending"
ORDER_PROCESSING = "Processing"
ORDER_SHIPPING = "Shipping"
ORDER_DELIVERED = "Delivered"
ORDER_COMPLETED = "Completed"
ORDER_CANCELLED = "Cancelled"
PAYMENT_PENDING = "Pending"
PAYMENT_PAID = "Paid"
PAYMENT_CANCELLED = "Cancelled"
# Chưa thanh toán: hủy đơn thì PaymentStatus → Cancelled.
UNPAID_PAYMENT_STATUSES = ("Pending", "Failed")
# PaymentMethods.Code của thanh toán khi nhận hàng.
PAYMENT_METHOD_COD = "COD"
# PaymentTransactions: giao dịch thu tiền COD khi xác nhận giao hàng thành công.
TX_PAYMENT = "Payment"
TX_SUCCESS = "Success"

SERIAL_AVAILABLE = "Available"
SERIAL_RESERVED = "Reserved"
SERIAL_SOLD = "Sold"
# Hàng trả về bị hỏng khi kiểm tra: đã về kho nhưng không nhập tồn khả dụng (không tự WrittenOff).
SERIAL_RETURNED = "Returned"

# Luồng xử lý tuần tự (Pending → Confirmed → Processing → Shipping → Delivered → Completed).
_FORWARD_FLOW = tuple(status for status in ORDER_STATUSES if status != ORDER_CANCELLED)
NEXT_STATUS = dict(zip(_FORWARD_FLOW, _FORWARD_FLOW[1:]))
# Mốc thời gian ghi nhận khi chuyển sang trạng thái tương ứng.
STATUS_TIMESTAMP = {
    "Confirmed": "ConfirmedAt",
    "Shipping": "ShippedAt",
    "Delivered": "DeliveredAt",
    "Completed": "CompletedAt",
    "Cancelled": "CancelledAt",
}
CUSTOMER_CANCELLABLE = (ORDER_PENDING,)
# Staff/Admin hủy trước Delivered; sau Delivered dùng ReturnRequest.
STAFF_CANCELLABLE = _FORWARD_FLOW[: _FORWARD_FLOW.index(ORDER_DELIVERED)]

STAFF_ROLES = ("Staff", "Admin")
ORDER_NOTIFICATION_TYPE = "Order"

# Đơn thanh toán QR (không phải COD) hết hạn sau 15 phút tính từ Orders.OrderedAt nếu chưa thanh toán.
QR_PAYMENT_TTL = timedelta(minutes=15)
QR_EXPIRED_REASON = "Hết hạn thanh toán QR (15 phút)"
TX_PENDING = "Pending"
TX_CANCELLED = "Cancelled"


def qr_payment_deadline(order: Order) -> datetime:
    return order.OrderedAt + QR_PAYMENT_TTL


def warranty_start_date(delivered_at: datetime) -> date:
    """Ngày bắt đầu bảo hành của máy ban đầu = ngày lịch Việt Nam của thời điểm Delivered (giữ tên cũ)."""
    return vietnam_date(delivered_at)


def order_item_cogs(item: OrderItem) -> Decimal:
    """COGS của một dòng đơn = UnitCost (snapshot lúc bán) × Quantity."""
    return _money(item.UnitCost * item.Quantity)


@dataclass
class _Line:
    cart_item_id: uuid.UUID
    variant: ProductVariant
    quantity: int
    unit_price: Decimal
    unit_cost: Decimal
    gross: Decimal
    discount: Decimal = Decimal("0")

    @property
    def product_id(self) -> uuid.UUID:
        return self.variant.ProductId

    @property
    def category_id(self) -> uuid.UUID:
        return self.variant.product.CategoryId


class OrderService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.orders = OrderRepository(session)
        self.order_items = OrderItemRepository(session)
        self.histories = OrderStatusHistoryRepository(session)
        self.users = UserRepository(session)
        self.addresses = AddressRepository(session)
        self.carts = CartRepository(session)
        self.cart_items = CartItemRepository(session)
        self.variants = ProductVariantRepository(session)
        self.products = ProductRepository(session)
        self.serials = ProductSerialRepository(session)
        self.shipment_returns = ShipmentReturnRepository(session)
        self.shipment_return_items = ShipmentReturnItemRepository(session)
        self.returns = ReturnRequestRepository(session)
        self.shipping_methods = ShippingMethodRepository(session)
        self.payment_methods = PaymentMethodRepository(session)
        self.payment_transactions = PaymentTransactionRepository(session)
        self.coupon_service = CouponService(session, clock=clock)
        self.variant_service = ProductVariantService(session, clock=clock)
        self.notifications = NotificationService(session, clock=clock)

    # ==================================================================
    # Đặt hàng
    # ==================================================================

    def create_order(self, actor: Actor, data: OrderCreate) -> OrderDetailResponse:
        """Customer tạo đơn từ các CartItem đang được chọn trong giỏ của chính mình.

        Trong MỘT transaction: khóa biến thể (FOR UPDATE, thứ tự id) → kiểm tra còn bán và tồn kho →
        tính giá ở server → áp coupon (khóa coupon) → tạo Order, OrderItems → trừ tồn kho →
        xóa CartItem đã đặt → ghi OrderStatusHistory → tạo thông báo. Lỗi ở bất kỳ bước nào: rollback toàn bộ.
        """
        require_role(actor, *CUSTOMER_ONLY)
        customer_id = actor.user_id
        with self.transaction():
            customer = self._get_customer(customer_id)
            cart = self.carts.get_by_user(customer_id)
            selected = self.cart_items.list_by_cart(cart.CartId, is_selected=True) if cart else []
            if not selected:
                raise BusinessRuleError("Giỏ hàng chưa có sản phẩm được chọn", code="cart_empty")

            shipping = self.shipping_methods.get_by_id(data.ShippingMethodId)
            if shipping is None or not shipping.IsActive:
                raise NotFoundError("Phương thức vận chuyển không hợp lệ", code="shipping_method_not_available")
            payment = self.payment_methods.get_by_id(data.PaymentMethodId)
            if payment is None or not payment.IsActive:
                raise NotFoundError("Phương thức thanh toán không hợp lệ", code="payment_method_not_available")
            receiver = self._receiver(customer_id, data)

            # Khóa biến thể theo thứ tự ProductVariantId rồi mới kiểm tra/tính toán.
            locked = {
                v.ProductVariantId: v
                for v in self.variants.get_many_by_ids_for_update({i.ProductVariantId for i in selected})
            }
            lines = self._build_lines(selected, locked)
            subtotal = sum((line.gross for line in lines), Decimal("0"))

            coupon = None
            discount = Decimal("0")
            if data.CouponCode:
                coupon, discount = self.coupon_service.apply_coupon_to_order(data.CouponCode, lines, subtotal)

            shipping_fee = shipping.BaseFee
            order = self.orders.create(
                {
                    "OrderCode": self._new_order_code(),
                    "CustomerId": customer.UserId,
                    "AddressId": receiver["AddressId"],
                    "ShippingMethodId": shipping.ShippingMethodId,
                    "PaymentMethodId": payment.PaymentMethodId,
                    "CouponId": coupon.CouponId if coupon else None,
                    "Subtotal": subtotal,
                    "ShippingFee": shipping_fee,
                    "DiscountAmount": discount,
                    "TotalAmount": subtotal - discount + shipping_fee,
                    "OrderStatus": ORDER_PENDING,
                    "PaymentStatus": PAYMENT_PENDING,
                    "ReceiverName": receiver["ReceiverName"],
                    "ReceiverPhone": receiver["ReceiverPhone"],
                    "ShippingAddress": receiver["ShippingAddress"],
                    "CustomerNote": data.CustomerNote,
                }
            )
            self.orders.flush()

            for line in lines:
                variant = line.variant
                self.order_items.create(
                    {
                        "OrderId": order.OrderId,
                        "ProductVariantId": variant.ProductVariantId,
                        "ProductName": variant.product.Name,
                        "Sku": variant.Sku,
                        "VariantInfo": _variant_info(variant),
                        "WarrantyMonths": variant.product.WarrantyMonths,
                        "Quantity": line.quantity,
                        "UnitPrice": line.unit_price,
                        "UnitCost": line.unit_cost,
                        "DiscountAmount": line.discount,
                        "LineTotal": line.gross - line.discount,
                    }
                )

            self.variant_service.change_stock({line.variant.ProductVariantId: -line.quantity for line in lines})
            for item in selected:
                self.cart_items.delete(item)
            self._record_history(order, None, ORDER_PENDING, changed_by=customer.UserId)
            self.notifications.notify(
                customer.UserId,
                title="Đặt hàng thành công",
                content=f"Đơn hàng {order.OrderCode} đã được tạo.",
                notification_type=ORDER_NOTIFICATION_TYPE,
                reference_type="Order",
                reference_id=order.OrderId,
            )
            self.orders.flush()
            return OrderDetailResponse.model_validate(self.orders.get_detail(order.OrderId))

    # ==================================================================
    # Customer: xem / tìm / hủy
    # ==================================================================

    def get_order(self, actor: Actor, order_id: uuid.UUID) -> OrderDetailResponse:
        """Customer xem đơn của chính mình (đơn của người khác: không tìm thấy)."""
        require_role(actor, *CUSTOMER_ONLY)
        order = self.orders.get_detail(order_id)
        if order is None or order.CustomerId != actor.user_id:
            raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
        return OrderDetailResponse.model_validate(order)

    def list_customer_orders(self, actor: Actor, *, page: int = 1, page_size: int = 20) -> PageResponse[OrderSummary]:
        return self.search_customer_orders(actor, page=page, page_size=page_size)

    def search_customer_orders(
        self,
        actor: Actor,
        *,
        order_code: str | None = None,
        order_status: str | None = None,
        ordered_from: datetime | None = None,
        ordered_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PageResponse[OrderSummary]:
        """Lịch sử đơn của khách hàng; lọc theo mã đơn, trạng thái, khoảng thời gian [from, to)."""
        require_role(actor, *CUSTOMER_ONLY)
        self._check_status_value(order_status)
        offset, limit = self._page_args(page, page_size)
        filters = {
            "customer_id": actor.user_id,
            "order_status": order_status,
            "ordered_from": ordered_from,
            "ordered_to": ordered_to,
            "order_code_contains": order_code.strip() if order_code and order_code.strip() else None,
        }
        orders = self.orders.list_orders(**filters, offset=offset, limit=limit)
        return PageResponse[OrderSummary](
            Items=[OrderSummary.model_validate(o) for o in orders],
            Total=self.orders.count_orders(**filters),
            Page=page,
            PageSize=page_size,
        )

    def get_order_status_history(self, actor: Actor, order_id: uuid.UUID) -> list[OrderStatusHistoryResponse]:
        require_role(actor, *CUSTOMER_ONLY)
        order = self.orders.get_by_id_and_customer(order_id, actor.user_id)
        if order is None:
            raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
        return [OrderStatusHistoryResponse.model_validate(h) for h in self.histories.list_by_order(order_id)]

    def get_customer_order_item(self, actor: Actor, order_item_id: uuid.UUID) -> OrderItemResponse:
        """Dòng đơn hàng thuộc đơn của khách hàng (dùng cho đánh giá/bảo hành/đổi trả)."""
        require_role(actor, *CUSTOMER_ONLY)
        item = self.order_items.get_by_id_and_customer(order_item_id, actor.user_id)
        if item is None:
            raise NotFoundError("Không tìm thấy dòng đơn hàng", code="order_item_not_found")
        return OrderItemResponse.model_validate(item)

    def cancel_customer_order(self, actor: Actor, order_id: uuid.UUID, data: OrderCancelRequest) -> OrderDetailResponse:
        """Khách hàng tự hủy đơn của mình khi đơn còn Pending."""
        require_role(actor, *CUSTOMER_ONLY)
        with self.transaction():
            order = self.orders.get_by_id_for_update(order_id)
            if order is None or order.CustomerId != actor.user_id:
                raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
            if order.OrderStatus not in CUSTOMER_CANCELLABLE:
                raise BusinessRuleError(
                    f"Không thể hủy đơn ở trạng thái {order.OrderStatus}", code="order_not_cancellable"
                )
            self._cancel(order, changed_by=actor.user_id, reason=data.CancelReason, note=None)
            self.orders.flush()
            return OrderDetailResponse.model_validate(self.orders.get_detail(order_id))

    # ==================================================================
    # Staff / Admin
    # ==================================================================

    def admin_list_orders(
        self,
        actor: Actor,
        *,
        order_code: str | None = None,
        customer_id: uuid.UUID | None = None,
        assigned_staff_id: uuid.UUID | None = None,
        order_status: str | None = None,
        payment_status: str | None = None,
        ordered_from: datetime | None = None,
        ordered_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PageResponse[AdminOrderResponse]:
        require_role(actor, *STAFF_OR_ADMIN)
        self._check_status_value(order_status)
        offset, limit = self._page_args(page, page_size)
        filters = {
            "customer_id": customer_id,
            "assigned_staff_id": assigned_staff_id,
            "order_status": order_status,
            "payment_status": payment_status,
            "ordered_from": ordered_from,
            "ordered_to": ordered_to,
            "order_code_contains": order_code.strip() if order_code and order_code.strip() else None,
        }
        orders = self.orders.list_orders(**filters, offset=offset, limit=limit)
        return PageResponse[AdminOrderResponse](
            Items=[AdminOrderResponse.model_validate(o) for o in orders],
            Total=self.orders.count_orders(**filters),
            Page=page,
            PageSize=page_size,
        )

    def admin_get_order(self, actor: Actor, order_id: uuid.UUID) -> AdminOrderDetailResponse:
        require_role(actor, *STAFF_OR_ADMIN)
        order = self.orders.get_detail(order_id)
        if order is None:
            raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
        return AdminOrderDetailResponse.model_validate(order)

    def admin_get_order_status_history(self, actor: Actor, order_id: uuid.UUID) -> list[AdminOrderStatusHistoryResponse]:
        require_role(actor, *STAFF_OR_ADMIN)
        if self.orders.get_by_id(order_id) is None:
            raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
        return [AdminOrderStatusHistoryResponse.model_validate(h) for h in self.histories.list_by_order(order_id)]

    def get_order_cogs(self, actor: Actor, order_id: uuid.UUID) -> Decimal:
        """Tổng COGS của đơn = Σ UnitCost × Quantity (UnitCost là snapshot lúc bán). Chỉ Admin (số liệu thống kê)."""
        require_role(actor, *ADMIN_ONLY)
        if self.orders.get_by_id(order_id) is None:
            raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
        return sum((order_item_cogs(i) for i in self.order_items.list_by_order(order_id)), Decimal("0"))

    def update_order_status(
        self, actor: Actor, order_id: uuid.UUID, data: OrderStatusUpdate
    ) -> AdminOrderDetailResponse:
        """Staff/Admin chuyển trạng thái: đi tuần tự từng bước, hoặc Cancelled khi chưa Delivered.

        Kèm theo: Shipping yêu cầu đã Paid (trừ COD) và đã gán đủ Serial/IMEI (``assign_order_serials``);
        Delivered bán Serial/IMEI; Completed cần không còn yêu cầu đổi/trả đang xử lý, rồi cập nhật thống kê.
        Đơn COD sang Delivered phải dùng ``confirm_cod_delivery`` (xác nhận đã thu tiền).
        """
        require_role(actor, *STAFF_OR_ADMIN)
        with self.transaction():
            order = self.orders.get_by_id_for_update(order_id)
            if order is None:
                raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
            current, target = order.OrderStatus, data.OrderStatus
            if target == ORDER_CANCELLED:
                if current not in STAFF_CANCELLABLE:
                    raise BusinessRuleError(f"Không thể hủy đơn ở trạng thái {current}", code="order_not_cancellable")
                self._cancel(order, changed_by=actor.user_id, reason=data.CancelReason, note=data.Note)
            else:
                if NEXT_STATUS.get(current) != target:
                    raise BusinessRuleError(
                        f"Không thể chuyển trạng thái từ {current} sang {target}", code="invalid_status_transition"
                    )
                if data.CancelReason is not None:
                    raise BusinessRuleError("CancelReason chỉ dùng khi hủy đơn", code="cancel_reason_not_allowed")
                if target == ORDER_DELIVERED and self._is_cod(order):
                    raise BusinessRuleError(
                        "Đơn COD chỉ chuyển Delivered khi xác nhận giao hàng và đã thu tiền",
                        code="cod_delivery_requires_collection",
                    )
                self._move_to(order, target, changed_by=actor.user_id, note=data.Note)
            self.orders.flush()
            return AdminOrderDetailResponse.model_validate(self.orders.get_detail(order_id))

    def confirm_cod_delivery(
        self, actor: Actor, order_id: uuid.UUID, *, note: str | None = None
    ) -> AdminOrderDetailResponse:
        """Staff/Admin xác nhận đơn COD đã giao thành công VÀ đã thu đủ tiền.

        Trong MỘT transaction: Shipping → Delivered, bán Serial/IMEI, PaymentStatus Pending → Paid và tạo
        PaymentTransaction (Payment, Success, Amount = Orders.TotalAmount lấy ở server). Gọi lặp bị chặn
        bởi kiểm tra trạng thái trên dòng đơn đã khóa, nên không tạo giao dịch trùng.
        Giao không thành công/khách không trả tiền: không gọi hàm này (xử lý bằng hủy đơn).
        """
        require_role(actor, *STAFF_OR_ADMIN)
        with self.transaction():
            order = self.orders.get_by_id_for_update(order_id)
            if order is None:
                raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
            if not self._is_cod(order):
                raise BusinessRuleError("Đơn không thanh toán khi nhận hàng (COD)", code="payment_method_not_cod")
            if order.OrderStatus != ORDER_SHIPPING:
                raise BusinessRuleError(
                    f"Chỉ xác nhận giao COD cho đơn đang giao (hiện tại: {order.OrderStatus})",
                    code="invalid_status_transition",
                )
            if order.PaymentStatus != PAYMENT_PENDING:
                raise BusinessRuleError(
                    f"Trạng thái thanh toán không hợp lệ để ghi nhận thu COD: {order.PaymentStatus}",
                    code="cod_payment_not_pending",
                )
            now = self.now()
            self._move_to(order, ORDER_DELIVERED, changed_by=actor.user_id, note=note)
            order.PaymentStatus = PAYMENT_PAID
            self.payment_transactions.create(
                {
                    "OrderId": order.OrderId,
                    "PaymentMethodId": order.PaymentMethodId,
                    "TransactionType": TX_PAYMENT,
                    "Amount": order.TotalAmount,
                    "Status": TX_SUCCESS,
                    "PaidAt": now,
                }
            )
            self.orders.flush()
            return AdminOrderDetailResponse.model_validate(self.orders.get_detail(order_id))

    def update_order_admin_info(self, actor: Actor, order_id: uuid.UUID, data: OrderAdminUpdate) -> AdminOrderDetailResponse:
        """Staff/Admin phân công nhân viên phụ trách và ghi chú nội bộ."""
        require_role(actor, *STAFF_OR_ADMIN)
        with self.transaction():
            order = self.orders.get_by_id(order_id)
            if order is None:
                raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
            values = data.model_dump(exclude_unset=True)
            staff_id = values.get("AssignedStaffId")
            if staff_id is not None:
                staff = self.users.get_by_id(staff_id)
                if staff is None or staff.IsDeleted or staff.Role not in STAFF_ROLES:
                    raise BusinessRuleError("Nhân viên phụ trách không hợp lệ", code="invalid_assigned_staff")
            self.orders.update(order, values)
            self.orders.flush()
            return AdminOrderDetailResponse.model_validate(self.orders.get_detail(order_id))

    # ==================================================================
    # Đóng gói: gán Serial/IMEI thực tế
    # ==================================================================

    def get_order_serials(self, actor: Actor, order_id: uuid.UUID) -> list[OrderItemSerialsResponse]:
        require_role(actor, *STAFF_OR_ADMIN)
        if self.orders.get_by_id(order_id) is None:
            raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
        return self._serial_summary(order_id)

    def assign_order_serials(
        self, actor: Actor, order_id: uuid.UUID, data: OrderSerialAssign
    ) -> list[OrderItemSerialsResponse]:
        """Staff/Admin quét/chọn Serial/IMEI của thiết bị thực tế khi đóng gói (đơn Processing).

        Có thể quét dần nhiều lần nhưng mỗi lần là nguyên tử: kiểm tra toàn bộ (đúng dòng đơn, biến thể quản lý serial,
        không vượt số lượng, serial đúng biến thể, Available và chưa gắn đơn) rồi mới ghi; lỗi thì không gán serial nào.
        Khóa đơn rồi khóa serial (thứ tự SerialNumber): hai nhân viên gán cùng serial → người sau thấy serial không
        còn Available. Không tự chọn serial thay cho bước xác nhận thiết bị vật lý.
        """
        require_role(actor, *STAFF_OR_ADMIN)
        requested: dict[uuid.UUID, list[str]] = {}
        for entry in data.Items:
            if entry.OrderItemId in requested:
                raise BusinessRuleError("Một dòng đơn chỉ khai một lần", code="duplicate_assign_line")
            requested[entry.OrderItemId] = [normalize_serial_number(s) for s in entry.SerialNumbers]
        numbers = [n for values in requested.values() for n in values]
        repeated = sorted({n for n in numbers if numbers.count(n) > 1})
        if repeated:
            raise BusinessRuleError(f"Serial/IMEI bị trùng trong yêu cầu: {repeated}", code="duplicate_serial_in_request")

        with self.transaction():
            order = self.orders.get_by_id_for_update(order_id)
            if order is None:
                raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
            if order.OrderStatus != ORDER_PROCESSING:
                raise BusinessRuleError(
                    "Chỉ gán Serial/IMEI khi đơn đang đóng gói (Processing)", code="order_not_packing"
                )
            items = {i.OrderItemId: i for i in self.order_items.list_by_order(order_id)}
            unknown = [str(i) for i in requested if i not in items]
            if unknown:
                raise NotFoundError(f"Dòng đơn không thuộc đơn hàng: {sorted(unknown)}", code="order_item_not_found")
            for order_item_id, values in requested.items():
                item = items[order_item_id]
                variant = self.variants.get_by_id(item.ProductVariantId)
                if variant is None or not variant.IsSerialTracked:
                    raise BusinessRuleError(f"Sản phẩm {item.Sku} không quản lý Serial/IMEI", code="serials_not_allowed")
                assigned = sum(
                    1 for s in self.serials.list_by_order_item(order_item_id) if s.Status == SERIAL_RESERVED
                )
                if assigned + len(values) > item.Quantity:
                    raise BusinessRuleError(
                        f"Dòng {item.Sku} cần {item.Quantity} Serial/IMEI (đã gán {assigned})", code="too_many_serials"
                    )
            locked = {s.SerialNumber: s for s in self.serials.list_by_serial_numbers_for_update(numbers)}
            missing = sorted(n for n in numbers if n not in locked)
            if missing:
                raise NotFoundError(f"Không tìm thấy Serial/IMEI: {missing}", code="serial_not_found")
            for order_item_id, values in requested.items():
                for number in values:
                    serial = locked[number]
                    if serial.ProductVariantId != items[order_item_id].ProductVariantId:
                        raise BusinessRuleError(
                            f"Serial/IMEI {number} không thuộc sản phẩm của dòng đơn", code="serial_variant_mismatch"
                        )
                    if serial.Status != SERIAL_AVAILABLE or serial.OrderItemId is not None:
                        raise BusinessRuleError(
                            f"Serial/IMEI {number} không còn khả dụng (đã gán hoặc rời kho)", code="serial_not_available"
                        )
            for order_item_id, values in requested.items():
                for number in values:
                    locked[number].Status = SERIAL_RESERVED
                    locked[number].OrderItemId = order_item_id
            self.serials.flush()
            return self._serial_summary(order_id)

    def release_order_serial(self, actor: Actor, order_id: uuid.UUID, serial_number: str) -> list[OrderItemSerialsResponse]:
        """Gỡ Serial/IMEI gán nhầm khi đơn còn đóng gói (Processing): Reserved → Available, bỏ gắn dòng đơn.

        Sau khi đã giao (Shipping) không gỡ được: hàng hủy khi đang giao xử lý qua hồ sơ ShipmentReturns.
        """
        require_role(actor, *STAFF_OR_ADMIN)
        number = normalize_serial_number(serial_number)
        with self.transaction():
            order = self.orders.get_by_id_for_update(order_id)
            if order is None:
                raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
            if order.OrderStatus != ORDER_PROCESSING:
                raise BusinessRuleError(
                    "Chỉ gỡ Serial/IMEI khi đơn đang đóng gói (Processing)", code="order_not_packing"
                )
            item_ids = {i.OrderItemId for i in self.order_items.list_by_order(order_id)}
            locked = self.serials.list_by_serial_numbers_for_update([number])
            if not locked:
                raise NotFoundError("Không tìm thấy Serial/IMEI", code="serial_not_found")
            serial = locked[0]
            if serial.Status != SERIAL_RESERVED or serial.OrderItemId not in item_ids:
                raise BusinessRuleError("Serial/IMEI không được gán cho đơn này", code="serial_not_assigned_to_order")
            serial.Status, serial.OrderItemId = SERIAL_AVAILABLE, None
            self.serials.flush()
            return self._serial_summary(order_id)

    # ==================================================================
    # Giao hàng thất bại: hàng quay về kho
    # ==================================================================

    def list_shipment_returns(
        self, actor: Actor, *, status: str | None = None, page: int = 1, page_size: int = 20
    ) -> PageResponse[ShipmentReturnResponse]:
        """Staff/Admin xem hồ sơ hàng chờ quay về (AwaitingReturn) / đã nhận lại (Received)."""
        require_role(actor, *STAFF_OR_ADMIN)
        if status is not None and status not in SHIPMENT_RETURN_STATUSES:
            raise BusinessRuleError(f"Trạng thái hồ sơ không hợp lệ: {status}", code="invalid_shipment_return_status")
        offset, limit = self._page_args(page, page_size)
        items = self.shipment_returns.list_returns(status=status, offset=offset, limit=limit)
        return PageResponse[ShipmentReturnResponse](
            Items=[ShipmentReturnResponse.model_validate(r) for r in items],
            Total=self.shipment_returns.count_returns(status=status),
            Page=page,
            PageSize=page_size,
        )

    def get_shipment_return(self, actor: Actor, order_id: uuid.UUID) -> ShipmentReturnResponse:
        require_role(actor, *STAFF_OR_ADMIN)
        record = self.shipment_returns.get_by_order(order_id)
        if record is None:
            raise NotFoundError("Không có hồ sơ hàng hoàn kho cho đơn này", code="shipment_return_not_found")
        return ShipmentReturnResponse.model_validate(record)

    def receive_shipment_return(
        self, actor: Actor, order_id: uuid.UUID, data: ShipmentReturnReceive
    ) -> ShipmentReturnResponse:
        """Staff/Admin xác nhận đã nhận lại hàng của đơn hủy khi đang giao và kết quả kiểm tra thực tế.

        Phải khai đủ mọi đơn vị hàng của hồ sơ: dòng không quản lý serial (số nhập lại + số hỏng = số đã giao),
        mọi serial nằm đúng một trong hai danh sách đạt/hỏng. Trong MỘT transaction: khóa đơn → hồ sơ → biến thể
        (thứ tự id) → serial (thứ tự SerialNumber); hàng đạt cộng lại tồn, serial đạt → Available (bỏ gắn đơn);
        hàng hỏng không cộng tồn, serial hỏng → Returned. Hồ sơ chỉ nhận một lần (không cộng tồn hai lần).
        """
        require_role(actor, *STAFF_OR_ADMIN)
        restocked_numbers = [normalize_serial_number(s) for s in data.RestockedSerialNumbers]
        damaged_numbers = [normalize_serial_number(s) for s in data.DamagedSerialNumbers]
        all_numbers = restocked_numbers + damaged_numbers
        repeated = sorted({s for s in all_numbers if all_numbers.count(s) > 1})
        if repeated:
            raise BusinessRuleError(f"Serial/IMEI bị khai trùng: {repeated}", code="duplicate_serial_in_request")
        lines: dict[uuid.UUID, object] = {}
        for line in data.Items:
            if line.OrderItemId in lines:
                raise BusinessRuleError("Một dòng đơn chỉ khai một lần", code="duplicate_return_line")
            lines[line.OrderItemId] = line

        with self.transaction():
            order = self.orders.get_by_id_for_update(order_id)
            if order is None:
                raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
            record = self.shipment_returns.get_by_order_for_update(order_id)
            if record is None:
                raise NotFoundError("Không có hồ sơ hàng hoàn kho cho đơn này", code="shipment_return_not_found")
            if record.Status != SHIPMENT_RETURN_AWAITING:
                raise BusinessRuleError("Hồ sơ đã được nhận hàng", code="shipment_return_already_received")
            rows = self.shipment_return_items.list_by_return(record.ShipmentReturnId)
            variant_of = {i.OrderItemId: i.ProductVariantId for i in self.order_items.list_by_order(order_id)}

            plain = {r.OrderItemId: r for r in rows if r.ProductSerialId is None}
            if set(lines) != set(plain):
                raise BusinessRuleError(
                    "Phải khai kết quả cho đúng các dòng hàng không quản lý serial của hồ sơ",
                    code="shipment_return_items_mismatch",
                )
            for order_item_id, row in plain.items():
                line = lines[order_item_id]
                if line.RestockedQuantity + line.DamagedQuantity != row.ExpectedQuantity:
                    raise BusinessRuleError(
                        f"Số nhập lại + số hỏng phải bằng {row.ExpectedQuantity} cho dòng {order_item_id}",
                        code="shipment_return_quantity_mismatch",
                    )

            # Thứ tự khóa chung: biến thể (theo id) trước serial (theo SerialNumber).
            self.variants.get_many_by_ids_for_update(sorted({variant_of[r.OrderItemId] for r in rows}))
            by_serial = {r.ProductSerialId: r for r in rows if r.ProductSerialId is not None}
            locked = {s.SerialNumber: s for s in self.serials.list_by_serial_numbers_for_update(all_numbers)}
            given = {locked[n].ProductSerialId for n in all_numbers if n in locked}
            if len(given) != len(all_numbers) or given != set(by_serial):
                raise BusinessRuleError(
                    "Danh sách serial phải gồm đúng các serial của hồ sơ, mỗi serial ở một kết quả",
                    code="shipment_return_serials_mismatch",
                )
            for number in all_numbers:
                serial = locked[number]
                if serial.Status != SERIAL_RESERVED or serial.OrderItemId != by_serial[serial.ProductSerialId].OrderItemId:
                    raise BusinessRuleError(
                        f"Serial/IMEI {number} không ở trạng thái đang giao của đơn", code="serial_not_in_transit"
                    )

            restock: dict[uuid.UUID, int] = {}
            for order_item_id, row in plain.items():
                row.RestockedQuantity = lines[order_item_id].RestockedQuantity
                row.DamagedQuantity = lines[order_item_id].DamagedQuantity
                variant_id = variant_of[order_item_id]
                restock[variant_id] = restock.get(variant_id, 0) + row.RestockedQuantity
            for number in restocked_numbers:
                serial = locked[number]
                row = by_serial[serial.ProductSerialId]
                row.RestockedQuantity, row.DamagedQuantity = 1, 0
                serial.Status, serial.OrderItemId = SERIAL_AVAILABLE, None
                restock[serial.ProductVariantId] = restock.get(serial.ProductVariantId, 0) + 1
            for number in damaged_numbers:
                serial = locked[number]
                row = by_serial[serial.ProductSerialId]
                row.RestockedQuantity, row.DamagedQuantity = 0, 1
                serial.Status, serial.OrderItemId = SERIAL_RETURNED, None
            self.variant_service.change_stock(restock)

            record.Status = SHIPMENT_RETURN_RECEIVED
            record.ReceivedAt = self.now()
            record.ReceivedByUserId = actor.user_id
            record.Note = data.Note
            self.shipment_returns.flush()
            return ShipmentReturnResponse.model_validate(self.shipment_returns.get_by_order(order_id))

    # ==================================================================
    # Hệ thống: hết hạn thanh toán QR
    # ==================================================================

    def expire_unpaid_qr_orders(self, *, limit: int = 100) -> int:
        """Hủy các đơn QR (không phải COD) còn Pending, chưa thanh toán, quá 15 phút kể từ OrderedAt.

        Dành cho endpoint nội bộ được bảo vệ do cron bên ngoài gọi (không phải thao tác người dùng nên không
        nhận Actor; lịch sử ghi ChangedByUserId = NULL). Mỗi đơn một transaction: khóa đơn → kiểm tra lại điều kiện
        → hủy (hoàn tồn kho, trả lượt coupon) → hủy giao dịch QR đang chờ. Đơn đã hủy/đã thanh toán (callback
        đến trước) bị bỏ qua nên tồn kho và coupon chỉ được hoàn đúng một lần. Trả về số đơn đã hủy.
        """
        if self.in_transaction():
            raise BusinessRuleError(
                "Xử lý hết hạn phải là use case độc lập", code="expiry_requires_own_transaction"
            )
        if limit < 1:
            raise BusinessRuleError("limit phải lớn hơn 0", code="invalid_limit")
        candidates = self.orders.list_expired_unpaid_order_ids(
            ordered_before=self.now() - QR_PAYMENT_TTL,
            order_status=ORDER_PENDING,
            payment_statuses=UNPAID_PAYMENT_STATUSES,
            excluded_payment_method_code=PAYMENT_METHOD_COD,
            limit=limit,
        )
        expired = 0
        for order_id in candidates:
            with self.transaction():
                order = self.orders.get_by_id_for_update(order_id)
                if order is None or not self.is_qr_payment_expired(order):
                    continue
                self._cancel(order, changed_by=None, reason=QR_EXPIRED_REASON, note="Hệ thống: hết hạn thanh toán QR")
                expired += 1
        return expired

    def is_qr_payment_expired(self, order: Order) -> bool:
        """Đơn QR chưa thanh toán đã quá hạn 15 phút (chỉ áp dụng cho đơn Pending)."""
        return (
            order.OrderStatus == ORDER_PENDING
            and order.PaymentStatus in UNPAID_PAYMENT_STATUSES
            and not self._is_cod(order)
            and qr_payment_deadline(order) <= self.now()
        )

    # ==================================================================
    # Helpers (tham gia transaction của use case gọi chúng)
    # ==================================================================

    def _get_customer(self, customer_id: uuid.UUID) -> User:
        customer = self.users.get_by_id(customer_id)
        if customer is None or customer.IsDeleted:
            raise NotFoundError("Không tìm thấy tài khoản", code="user_not_found")
        return customer

    def _receiver(self, customer_id: uuid.UUID, data: OrderCreate) -> dict:
        """Thông tin người nhận: chụp lại từ Address của khách hoặc lấy từ dữ liệu nhập."""
        explicit = {"ReceiverName", "ReceiverPhone", "ShippingAddress"} & data.model_fields_set
        if data.AddressId is not None:
            if explicit:
                raise BusinessRuleError(
                    "Chỉ chọn địa chỉ đã lưu hoặc nhập thông tin người nhận, không dùng cả hai", code="receiver_conflict"
                )
            address = self.addresses.get_by_id_and_user(data.AddressId, customer_id)
            if address is None or address.IsDeleted:
                raise NotFoundError("Không tìm thấy địa chỉ", code="address_not_found")
            return {
                "AddressId": address.AddressId,
                "ReceiverName": address.ReceiverName,
                "ReceiverPhone": address.ReceiverPhone,
                "ShippingAddress": ", ".join((address.DetailAddress, address.Ward, address.Province)),
            }
        return {
            "AddressId": None,
            "ReceiverName": data.ReceiverName,
            "ReceiverPhone": data.ReceiverPhone,
            "ShippingAddress": data.ShippingAddress,
        }

    def _build_lines(self, selected: list, locked: dict[uuid.UUID, ProductVariant]) -> list[_Line]:
        """Kiểm tra lại sản phẩm còn bán và tồn kho (trên dòng đã khóa); giá/giá vốn lấy ở server."""
        unavailable, short = [], []
        lines = []
        for item in selected:
            variant = locked.get(item.ProductVariantId)
            if not is_variant_sellable(variant):
                unavailable.append(str(item.ProductVariantId))
                continue
            if item.Quantity > variant.StockQuantity:
                short.append(str(item.ProductVariantId))
                continue
            lines.append(
                _Line(
                    cart_item_id=item.CartItemId,
                    variant=variant,
                    quantity=item.Quantity,
                    unit_price=variant.Price,
                    unit_cost=variant.CostPrice,
                    gross=_money(variant.Price * item.Quantity),
                )
            )
        if unavailable:
            raise BusinessRuleError(f"Sản phẩm không còn bán: {sorted(unavailable)}", code="variant_not_available")
        if short:
            raise BusinessRuleError(f"Không đủ tồn kho: {sorted(short)}", code="insufficient_stock")
        return lines

    def _new_order_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(10):
            code = f"VT{self.now():%y%m%d}{''.join(secrets.choice(alphabet) for _ in range(6))}"
            if not self.orders.exists_by_code(code):
                return code
        raise BusinessRuleError("Không tạo được mã đơn hàng", code="order_code_generation_failed")

    def _cancel(self, order: Order, *, changed_by: uuid.UUID | None, reason: str | None, note: str | None) -> None:
        """Hủy đơn (đã khóa): xử lý hàng theo vị trí thực tế, trả lượt coupon, cập nhật PaymentStatus chưa thanh toán.

        Trước Shipping: hoàn tồn kho + nhả serial đang giữ ngay. Đang Shipping: hàng ở bên vận chuyển → không hoàn
        tồn, serial giữ Reserved, mở hồ sơ ShipmentReturns chờ nhận lại. Đơn đã Paid: không coi là đã hoàn tiền.
        """
        previous = order.OrderStatus
        items = self.order_items.list_by_order(order.OrderId)
        if previous == ORDER_SHIPPING:
            self._open_shipment_return(order, items, created_by=changed_by)
        else:
            self.variant_service.change_stock({i.ProductVariantId: i.Quantity for i in items})
            for item in items:
                for serial in self.serials.list_by_order_item(item.OrderItemId):
                    if serial.Status == SERIAL_RESERVED:
                        serial.Status = SERIAL_AVAILABLE
                        serial.OrderItemId = None
        if order.CouponId is not None:
            self.coupon_service.release_coupon_usage(order.CouponId)
        self._cancel_pending_payment_requests(order)
        if order.PaymentStatus in UNPAID_PAYMENT_STATUSES:
            order.PaymentStatus = PAYMENT_CANCELLED
        order.OrderStatus = ORDER_CANCELLED
        order.CancelledAt = self.now()
        if reason is not None:
            order.CancelReason = reason
        self._record_history(order, previous, ORDER_CANCELLED, changed_by=changed_by, note=note)
        self._notify_status(order)
        if order.PaymentStatus == PAYMENT_PAID:
            self._notify_staff_refund_needed(order)

    def _cancel_pending_payment_requests(self, order: Order) -> None:
        """Hủy đơn (Order đã khóa): giao dịch Payment còn Pending (yêu cầu QR) → Cancelled.

        Chỉ đổi Status: giữ GatewayTransactionCode/QrData/ResponseData để đối soát. Không đụng giao dịch Success/Failed/
        Cancelled và giao dịch Refund. Mọi luồng ghi PaymentTransactions đều khóa Order trước nên không chạy chồng với
        callback/webhook. Đánh dấu Cancelled không chứng minh khách không thể chuyển khoản; khoản tiền đến sau được
        PaymentService ghi nhận Success + đối soát PaymentAfterCancellation (không bỏ qua, không tự hoàn).
        """
        for transaction in self.payment_transactions.list_by_order(order.OrderId, status=TX_PENDING):
            if transaction.TransactionType == TX_PAYMENT:
                transaction.Status = TX_CANCELLED

    def _open_shipment_return(self, order: Order, items: list[OrderItem], *, created_by: uuid.UUID | None) -> None:
        """Hồ sơ hàng chờ quay về: một dòng mỗi serial đang giữ (biến thể quản lý serial) hoặc mỗi dòng đơn."""
        record = self.shipment_returns.create(
            {
                "OrderId": order.OrderId,
                "Status": SHIPMENT_RETURN_AWAITING,
                "CreatedByUserId": created_by,
                "CreatedAt": self.now(),
            }
        )
        self.shipment_returns.flush()
        for item in sorted(items, key=lambda i: i.OrderItemId):
            variant = self.variants.get_by_id(item.ProductVariantId)
            if variant is not None and variant.IsSerialTracked:
                serials = [
                    s for s in self.serials.list_by_order_item_for_update(item.OrderItemId) if s.Status == SERIAL_RESERVED
                ]
                if len(serials) != item.Quantity:
                    raise BusinessRuleError(
                        f"Dòng đơn {item.OrderItemId} đang giao nhưng thiếu Serial/IMEI ({len(serials)}/{item.Quantity})",
                        code="shipment_serials_incomplete",
                    )
                for serial in serials:
                    self._add_return_item(record, item, serial.ProductSerialId, 1)
            else:
                self._add_return_item(record, item, None, item.Quantity)

    def _add_return_item(self, record, item: OrderItem, serial_id: uuid.UUID | None, quantity: int) -> None:
        self.shipment_return_items.create(
            {
                "ShipmentReturnId": record.ShipmentReturnId,
                "OrderItemId": item.OrderItemId,
                "ProductSerialId": serial_id,
                "ExpectedQuantity": quantity,
            }
        )

    def _notify_staff_refund_needed(self, order: Order) -> None:
        """Đơn đã thanh toán bị hủy: báo Staff/Admin đang hoạt động xử lý hoàn tiền (chưa coi là đã hoàn)."""
        for role in STAFF_ROLES:
            for user in self.users.list_users(role=role, account_status="Active"):
                self.notifications.notify(
                    user.UserId,
                    title="Cần hoàn tiền",
                    content=f"Đơn hàng {order.OrderCode} đã hủy khi đã thanh toán; cần xử lý hoàn tiền.",
                    notification_type=ORDER_NOTIFICATION_TYPE,
                    reference_type="Order",
                    reference_id=order.OrderId,
                )

    @staticmethod
    def _is_cod(order: Order) -> bool:
        return order.payment_method.Code == PAYMENT_METHOD_COD

    def _move_to(self, order: Order, target: str, *, changed_by: uuid.UUID | None, note: str | None) -> None:
        """Chuyển đơn sang trạng thái kế tiếp (đã kiểm tra hợp lệ): tác động nghiệp vụ, mốc thời gian, lịch sử, thông báo.

        Một mốc thời gian duy nhất (UTC) dùng cho cả cột thời điểm (ví dụ DeliveredAt) và tác động nghiệp vụ
        (ví dụ ngày bắt đầu bảo hành), để hai giá trị luôn nhất quán.
        """
        current = order.OrderStatus
        moved_at = self.now()
        self._apply_transition_effects(order, target, moved_at)
        order.OrderStatus = target
        if target in STATUS_TIMESTAMP:
            setattr(order, STATUS_TIMESTAMP[target], moved_at)
        self._record_history(order, current, target, changed_by=changed_by, note=note)
        self._notify_status(order)

    def _apply_transition_effects(self, order: Order, target: str, moved_at: datetime) -> None:
        """Tác động nghiệp vụ khi Staff/Admin chuyển đơn sang trạng thái kế tiếp.

        Không thay đổi PaymentStatus: COD được ghi nhận Paid riêng trong ``confirm_cod_delivery``.
        """
        if target == ORDER_SHIPPING:
            if not self._is_cod(order) and order.PaymentStatus != PAYMENT_PAID:
                raise BusinessRuleError("Đơn hàng chưa được thanh toán", code="order_not_paid")
            self._ensure_serials_assigned(order)
        elif target == ORDER_DELIVERED:
            self._sell_reserved_serials(order, delivered_at=moved_at)
        elif target == ORDER_COMPLETED:
            self._ensure_no_open_returns(order)
            self._update_sales_counters(order)

    def _ensure_no_open_returns(self, order: Order) -> None:
        """Completed: đơn không còn yêu cầu đổi/trả đang xử lý (gồm yêu cầu có Refund Pending/Failed chưa hoàn tất)."""
        codes = self.returns.list_open_request_codes_for_order(order.OrderId)
        if codes:
            raise BusinessRuleError(
                f"Đơn còn yêu cầu đổi/trả đang xử lý ({', '.join(codes)}); hoàn tất, từ chối hoặc hủy yêu cầu trước "
                "khi chuyển Completed",
                code="order_has_open_returns",
            )

    def _sell_reserved_serials(self, order: Order, *, delivered_at: datetime) -> None:
        """Delivered: Serial/IMEI đang giữ cho đơn (Reserved) → Sold và bắt đầu bảo hành.

        - Thời hạn theo ``delivery_warranty_period``: bắt đầu = ngày lịch Việt Nam của thời điểm Delivered (UTC),
          hết hạn = bắt đầu + OrderItems.WarrantyMonths − 1 ngày; WarrantyMonths = 0 → không bảo hành (cả hai NULL).
          Serial bán lại nhận thời hạn của lần bán này (không giữ ngày của lần bán trước).
        - Số tháng không hợp lệ (âm, không phải số nguyên, thiếu) → lỗi, cả use case rollback.
        - Chỉ serial đang Reserved của đơn này mới được cập nhật; serial đã Sold không bị tính lại.
        Khóa serial theo từng dòng đơn (thứ tự OrderItemId, SerialNumber); lỗi ở bất kỳ serial nào thì use case rollback.
        """
        for item in sorted(self.order_items.list_by_order(order.OrderId), key=lambda i: i.OrderItemId):
            period = delivery_warranty_period(delivered_at, item.WarrantyMonths)
            for serial in self.serials.list_by_order_item_for_update(item.OrderItemId):
                if serial.Status != SERIAL_RESERVED:
                    continue
                serial.Status = SERIAL_SOLD
                serial.WarrantyStartDate = period.start if period else None
                serial.WarrantyEndDate = period.end if period else None

    def _ensure_serials_assigned(self, order: Order) -> None:
        """Shipping: mọi dòng đơn của biến thể quản lý serial phải được gán đủ Serial/IMEI thực tế (Reserved)."""
        missing = []
        for item in sorted(self.order_items.list_by_order(order.OrderId), key=lambda i: i.OrderItemId):
            variant = self.variants.get_by_id(item.ProductVariantId)
            if variant is None or not variant.IsSerialTracked:
                continue
            reserved = sum(1 for s in self.serials.list_by_order_item(item.OrderItemId) if s.Status == SERIAL_RESERVED)
            if reserved != item.Quantity:
                missing.append(f"{item.Sku}: {reserved}/{item.Quantity}")
        if missing:
            raise BusinessRuleError(
                f"Chưa gán đủ Serial/IMEI thực tế khi đóng gói: {missing}", code="order_serials_not_assigned"
            )

    def _serial_summary(self, order_id: uuid.UUID) -> list[OrderItemSerialsResponse]:
        summary = []
        for item in sorted(self.order_items.list_by_order(order_id), key=lambda i: i.OrderItemId):
            variant = self.variants.get_by_id(item.ProductVariantId)
            summary.append(
                OrderItemSerialsResponse(
                    OrderItemId=item.OrderItemId,
                    ProductVariantId=item.ProductVariantId,
                    Sku=item.Sku,
                    Quantity=item.Quantity,
                    IsSerialTracked=bool(variant is not None and variant.IsSerialTracked),
                    SerialNumbers=sorted(s.SerialNumber for s in self.serials.list_by_order_item(item.OrderItemId)),
                )
            )
        return summary

    def _update_sales_counters(self, order: Order) -> None:
        """Completed: TotalSpent += TotalAmount, TotalOrders += 1, SoldQuantity += số lượng (có khóa dòng)."""
        customer = self.users.get_by_id_for_update(order.CustomerId)
        customer.TotalSpent += order.TotalAmount
        customer.TotalOrders += 1
        sold: dict[uuid.UUID, int] = {}
        for item in self.order_items.list_by_order(order.OrderId):
            product_id = self.variants.get_by_id(item.ProductVariantId).ProductId
            sold[product_id] = sold.get(product_id, 0) + item.Quantity
        for product_id in sorted(sold):
            product: Product = self.products.get_by_id_for_update(product_id)
            product.SoldQuantity += sold[product_id]

    def _record_history(
        self, order: Order, old: str | None, new: str, *, changed_by: uuid.UUID | None, note: str | None = None
    ) -> None:
        self.histories.create(
            {
                "OrderId": order.OrderId,
                "ChangedByUserId": changed_by,
                "OldStatus": old,
                "NewStatus": new,
                "Note": note,
                "ChangedAt": self.now(),
            }
        )

    def _notify_status(self, order: Order) -> None:
        self.notifications.notify(
            order.CustomerId,
            title="Cập nhật đơn hàng",
            content=f"Đơn hàng {order.OrderCode} chuyển sang trạng thái {order.OrderStatus}.",
            notification_type=ORDER_NOTIFICATION_TYPE,
            reference_type="Order",
            reference_id=order.OrderId,
        )

    @staticmethod
    def _check_status_value(order_status: str | None) -> None:
        if order_status is not None and order_status not in ORDER_STATUSES:
            raise BusinessRuleError(f"OrderStatus không hợp lệ: {order_status}", code="invalid_order_status")


def _variant_info(variant: ProductVariant) -> str:
    """Thông tin biến thể chụp lại vào OrderItems.VariantInfo (varchar 255)."""
    extras = [value for value in (variant.Color, variant.Storage) if value]
    info = variant.VariantName + (f" ({', '.join(extras)})" if extras else "")
    return info[:255]

