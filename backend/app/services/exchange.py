"""One return request buys one replacement; credit and stock are always calculated by the server."""
from decimal import Decimal
from types import SimpleNamespace
import uuid

from app.schemas.order import OrderDetailResponse
from app.schemas.exchange import ExchangeOrderCreate
from app.services.actor import CUSTOMER_ONLY, require_role
from app.services.base import BaseService
from app.services.catalog import is_variant_sellable
from app.services.exceptions import BusinessRuleError, NotFoundError
from app.services.order import OrderService, qr_payment_deadline, _variant_info
from app.services.pricing import variant_price

OPEN = ("Approved", "Receiving", "Processing")


def committed(order):
    # A zero-pay order is settled at creation. A positive QR order is settled only by the verified payment flow.
    return order is not None and order.OrderStatus != "Cancelled" and order.PaymentStatus == "Paid"


class ExchangeService(BaseService):
    def __init__(self, session, returns, *, clock):
        super().__init__(session, clock=clock)
        self.returns = returns
        self.sales = OrderService(session, clock=clock)

    def describe(self, request):
        flow = self.returns
        item = flow.order_items.get_by_id(request.OrderItemId)
        variant = flow.variants.get_by_id(item.ProductVariantId)
        active = flow.orders.exchange_order(request.ReturnRequestId)
        price = variant_price(variant, self.sales.promotions.list_automatic(self.now()), self.now()) if variant else None
        return dict(
            ReturnRequestId=request.ReturnRequestId, RequestCode=request.RequestCode, Status=request.Status,
            CategoryId=variant.product.CategoryId if variant else None,
            OriginalProductId=variant.ProductId if variant else None,
            OriginalProductSlug=variant.product.Slug if variant else None,
            OriginalVariantId=item.ProductVariantId,
            OriginalInStock=bool(is_variant_sellable(variant) and variant.StockQuantity > 0),
            OriginalSalePrice=price["SalePrice"] if price else None,
            CreditLimit=item.UnitPrice, CanChoose=request.Status in OPEN and active is None
                and not (is_variant_sellable(variant) and variant.StockQuantity > 0),
            Committed=committed(active),
            OrderId=active.OrderId if active else None,
            OrderCode=active.OrderCode if active else None,
            PaymentStatus=active.PaymentStatus if active else None,
            TotalAmount=active.TotalAmount if active else None,
        )

    def context(self, actor, request_id):
        require_role(actor, *CUSTOMER_ONLY)
        with self.transaction():
            request, original, _ = self.returns._lock(request_id, customer_id=actor.user_id)
            self.expire_pending(request)
            self.ensure_original_order(request, original)
            return self.describe(request)

    def ensure_original_order(self, request, original):
        """Called with the request locked; system creates the available exact SKU for its owner."""
        if request.Status not in OPEN or request.Quantity != 1:
            return
        # Historical financial-flow requests may already have received goods/approved money.
        # Reading them must not issue an additional replacement automatically.
        if request.RestockedQuantity or request.CompensationApprovedAt is not None:
            return
        if self.returns.orders.exchange_order(request.ReturnRequestId, for_update=True):
            return
        variants = self.returns.variants.get_many_by_ids_for_update({original.ProductVariantId})
        variant = next(iter(variants), None)
        if variant is None or not is_variant_sellable(variant) or variant.StockQuantity <= 0:
            return
        return self._create_order(request.CustomerId, request.ReturnRequestId,
                                  ExchangeOrderCreate(), changed_by=None)

    def expire_pending(self, request):
        order = self.returns.orders.exchange_order(request.ReturnRequestId, for_update=True)
        if order and order.OrderStatus == "Pending" and order.PaymentStatus in ("Pending", "Failed") and self.now() >= qr_payment_deadline(order):
            self.sales._cancel(order, changed_by=None, reason="Hết hạn thanh toán đơn đổi trả", note=None)
            self.returns.orders.flush()
            return None
        return order

    def create_order(self, actor, request_id, data):
        require_role(actor, *CUSTOMER_ONLY)
        return self._create_order(actor.user_id, request_id, data, changed_by=actor.user_id)

    def _create_order(self, customer_id, request_id, data, *, changed_by):
        flow, sales = self.returns, self.sales
        with self.transaction():
            request, original, source = flow._lock(request_id, customer_id=customer_id)
            if request.Status not in OPEN:
                raise BusinessRuleError("Chỉ chọn máy đổi sau khi tiếp nhận và trước khi đóng phiếu", code="exchange_not_open")
            if request.Quantity != 1:
                raise BusinessRuleError("Phiếu cũ có nhiều máy cần được xử lý riêng; luồng đổi mới chỉ đổi 1 máy", code="exchange_quantity_invalid")
            existing = self.expire_pending(request)
            if existing:
                return OrderDetailResponse.model_validate(sales.orders.get_detail(existing.OrderId))
            target_id = data.ProductVariantId or original.ProductVariantId
            # Order both row locks identically across requests, including swaps between variants.
            variants = {v.ProductVariantId: v for v in flow.variants.get_many_by_ids_for_update({original.ProductVariantId, target_id})}
            old, target = variants.get(original.ProductVariantId), variants.get(target_id)
            if old is None or target is None:
                raise NotFoundError("Không tìm thấy sản phẩm đổi", code="variant_not_available")
            if is_variant_sellable(old) and old.StockQuantity > 0 and target_id != old.ProductVariantId:
                raise BusinessRuleError("Máy ban đầu còn hàng, hệ thống đổi đúng phiên bản đã mua", code="exchange_original_available")
            if target.product.CategoryId != old.product.CategoryId:
                raise BusinessRuleError("Chỉ đổi sản phẩm cùng danh mục", code="exchange_category_mismatch")
            line = sales._build_lines([SimpleNamespace(ProductVariantId=target_id, Quantity=1, CartItemId=None)], variants)[0]
            # An exact-SKU replacement is an even exchange, regardless of later price changes.
            # Only a different replacement SKU may require the customer to pay a difference.
            credit = line.gross if target_id == original.ProductVariantId else min(original.UnitPrice, line.gross)
            due = line.gross - credit
            # No custom coupon is created; exchange credit belongs only to this request and its owner.
            shipping = next((m for m in sales.shipping_methods.list_methods(is_active=True)
                             if m.Code.upper() in ("STANDARD", "STD", "SHIP_STANDARD", "SHIP_STD")
                             or "tiêu chuẩn" in m.Name.lower()), None)
            if shipping is None:
                raise BusinessRuleError("Chưa có phương thức giao hàng tiêu chuẩn đang hoạt động", code="exchange_shipping_unavailable")
            payment = next((m for m in sales.payment_methods.list_methods(is_active=True) if m.Code == "QR"), None)
            if payment is None:
                raise BusinessRuleError("Chưa có phương thức chuyển khoản đang hoạt động", code="payment_method_not_available")
            receiver = (sales._receiver(customer_id, data) if data.AddressId or data.ReceiverName else
                        dict(AddressId=source.AddressId, ReceiverName=source.ReceiverName,
                             ReceiverPhone=source.ReceiverPhone, ShippingAddress=source.ShippingAddress))
            order = sales.orders.create(dict(
                OrderCode=sales._new_order_code(), CustomerId=customer_id,
                SourceReturnRequestId=request_id, ExchangeCreditAmount=credit,
                ShippingMethodId=shipping.ShippingMethodId, PaymentMethodId=payment.PaymentMethodId,
                Subtotal=line.unit_price, DiscountAmount=line.automatic + credit, ShippingFee=Decimal("0"), TotalAmount=due,
                OrderStatus="Pending", PaymentStatus="Paid" if due == 0 else "Pending",
                CustomerNote=f"Đơn đổi trả · {request.RequestCode}", **receiver))
            sales.orders.flush()
            sales.order_items.create(dict(OrderId=order.OrderId, ProductVariantId=target_id,
                ProductName=target.product.Name, Sku=target.Sku, VariantInfo=_variant_info(target),
                WarrantyMonths=target.product.WarrantyMonths, Quantity=1, UnitPrice=line.unit_price,
                UnitCost=line.unit_cost, DiscountAmount=line.automatic + credit, LineTotal=due))
            sales.variant_service.change_stock({target_id: -1})
            sales.orders.flush()
            # Reserve a real code immediately for the replacement; normal delivery starts its new warranty.
            sales._auto_assign_order_serials(order)
            sales._record_history(order, None, "Pending", changed_by=changed_by,
                                  note=f"Đơn đổi trả từ {request.RequestCode}; bù thêm {due:,.0f}đ.")
            sales.notifications.notify(customer_id, title="Đã tạo đơn đổi trả",
                content=f"Đơn {order.OrderCode}: {'không cần thanh toán' if due == 0 else f'cần thanh toán phần bù {due:,.0f}đ'}.",
                notification_type="Order", reference_type="Order", reference_id=order.OrderId)
            for role in ("Admin", "Staff"):
                for operator in sales.users.list_users(role=role):
                    sales.notifications.notify(operator.UserId, title="Đơn đổi trả mới chờ xác nhận",
                        content=f"Đơn {order.OrderCode} từ phiếu {request.RequestCode}.", notification_type="NewOrder",
                        action_url=f"/admin/orders/{order.OrderId}", reference_type="Order", reference_id=order.OrderId)
            prefix = "Hệ thống tự động tạo" if changed_by is None else "Đã tạo"
            flow._history(request, changed_by, request.Status, request.Status,
                          f"{prefix} đơn đổi trả {order.OrderCode}; giá trị dùng đổi {credit:,.0f}đ; bù thêm {due:,.0f}đ.")
            sales.orders.flush()
            return OrderDetailResponse.model_validate(sales.orders.get_detail(order.OrderId))

    def cancel_pending(self, request, actor):
        order = self.returns.orders.exchange_order(request.ReturnRequestId, for_update=True)
        if committed(order):
            raise BusinessRuleError("Đã chốt đơn đổi trả, không thể hủy phiếu", code="return_not_cancellable")
        if order:
            self.sales._cancel(order, changed_by=actor.user_id, reason="Khách hủy phiếu đổi trả", note=None)

    def complete(self, request, original):
        order = self.returns.orders.exchange_order(request.ReturnRequestId, for_update=True)
        if not committed(order):
            raise BusinessRuleError("Khách phải chốt đơn đổi trả và thanh toán phần bù (nếu có) trước khi hoàn tất phiếu", code="exchange_order_not_settled")
        if request.RestockedQuantity:
            raise BusinessRuleError("Phiếu đã nhập lại tồn trước đó", code="exchange_already_restocked")
        self.returns.variant_service.change_stock({original.ProductVariantId: 1})
        if request.ProductSerialId:
            serial = self.returns._lock_request_serial(request, original, expected_status="Sold")
            serial.Status, serial.OrderItemId = "Available", None
        request.RestockedQuantity, request.DamagedQuantity = 1, 0
