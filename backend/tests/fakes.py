"""Test doubles: Session và Repository trong bộ nhớ. Không kết nối database.

- FakeSession đếm commit/rollback/flush. Khi use case ngoài cùng bắt đầu (độ sâu transaction 0 → 1),
  FakeSession chụp lại dữ liệu; rollback() khôi phục dữ liệu về ảnh chụp đó, nên test kiểm tra được
  tính nguyên tử (một bước lỗi thì không thay đổi nào còn lại).
- Mọi truy cập database thật qua Session (get/scalars/execute/...) làm test lỗi ngay.
- Fake repository cài đặt đúng các method mà Service đang gọi, và ghi lại các lần khóa dòng.
Giới hạn: không mô phỏng được khóa dòng/đồng thời thật của PostgreSQL.
"""

import uuid
from collections import defaultdict
from contextlib import nullcontext
from datetime import datetime, timezone
from decimal import Decimal

from types import SimpleNamespace

from sqlalchemy import Numeric, inspect
from sqlalchemy.exc import IntegrityError

from app.models import (
    Conversation,
    Message,
    Address,
    Cart,
    CartItem,
    Category,
    Coupon,
    Notification,
    Order,
    OrderItem,
    OrderStatusHistory,
    OtpChallenge,
    PaymentMethod,
    PaymentTransaction,
    Product,
    ProductSerial,
    ProductVariant,
    Promotion,
    PromotionCategory,
    PromotionProduct,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
    Review,
    ReviewImage,
    ShippingMethod,
    Supplier,
    User,
    Brand,
    PaymentReconciliation,
    PaymentWebhookEvent,
    StockAdjustment,
    ShipmentReturn,
    ShipmentReturnItem,
    StockAdjustmentSerial,
    ServiceRequestAttachment,
    ServiceRequestHistory,
    WarrantyRequest,
    ReturnRequest,
    NewsArticle,
    Banner,
)
from app.models.service_request import RETURN_OPEN_STATUSES, WARRANTY_OPEN_STATUSES
from app.models.shipment import SHIPMENT_RETURN_AWAITING
from app.repositories.catalog import SerialTrackingUsage
from app.services import (
    ChatService,
    ReviewService,
    WarrantyService,
    ReturnService,
    ContentService,
    StatisticsService,
    Actor,
    CouponService,
    InventoryService,
    NotificationService,
    OrderService,
    PaymentService,
    ShippingMethodService,
    ProductVariantService,
    PurchaseOrderService,
)
from app.services.base import _DEPTH_KEY

NOW = datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc)


def resolve_refund(payments, actor, refund_id, *, success=True, evidence="SAO-KE-001",
                   note="Đã đối soát sao kê ngân hàng"):
    """Đợt 5.11: Admin (khác người tạo) xác nhận thủ công Refund Pending kèm bằng chứng."""
    from app.schemas import RefundResolution

    return payments.resolve_pending_refund(
        actor, refund_id, RefundResolution(Success=success, EvidenceReference=evidence, ResolutionNote=note))


def fixed_clock() -> datetime:
    return NOW


# ======================================================================
# Session + kho dữ liệu trong bộ nhớ
# ======================================================================


def _apply_server_defaults(obj) -> None:
    for attr in inspect(type(obj)).column_attrs:
        column = attr.columns[0]
        if getattr(obj, attr.key) is not None or column.server_default is None:
            continue
        expr = getattr(column.server_default.arg, "text", str(column.server_default.arg))
        if expr == "gen_random_uuid()":
            value = uuid.uuid4()
        elif expr == "now()":
            value = NOW
        elif expr in ("true", "false"):
            value = expr == "true"
        elif expr == "0":
            value = Decimal("0") if isinstance(column.type, Numeric) else 0
        else:
            raise AssertionError(f"Server default chưa hỗ trợ trong fake: {expr}")
        setattr(obj, attr.key, value)


def _pk(obj):
    # Tên attribute trùng tên column (PascalCase) trong toàn bộ Models.
    values = tuple(getattr(obj, column.key) for column in inspect(type(obj)).primary_key)
    return values[0] if len(values) == 1 else values


def _state(obj) -> dict:
    mapper = inspect(type(obj))
    state = {attr.key: getattr(obj, attr.key) for attr in mapper.column_attrs}
    for rel in mapper.relationships:
        if rel.uselist and rel.key in obj.__dict__:
            state[rel.key] = list(obj.__dict__[rel.key])
    return state


class InMemoryDB:
    def __init__(self) -> None:
        self.tables: dict[type, dict] = defaultdict(dict)
        self.locks: list[tuple[str, object]] = []

    def add(self, obj):
        _apply_server_defaults(obj)
        self.tables[type(obj)][_pk(obj)] = obj
        return obj

    def get(self, model, pk):
        return self.tables[model].get(pk)

    def rows(self, model) -> list:
        return list(self.tables[model].values())

    def remove(self, obj) -> None:
        self.tables[type(obj)].pop(_pk(obj), None)

    def snapshot(self):
        tables = {model: dict(rows) for model, rows in self.tables.items()}
        states = [(obj, _state(obj)) for rows in tables.values() for obj in rows.values()]
        return tables, states

    def restore(self, snapshot) -> None:
        tables, states = snapshot
        self.tables = defaultdict(dict, {model: dict(rows) for model, rows in tables.items()})
        for obj, state in states:
            for key, value in state.items():
                setattr(obj, key, value)


class _TxInfo(dict):
    """session.info: phát hiện use case ngoài cùng bắt đầu để chụp dữ liệu."""

    def __init__(self, session: "FakeSession") -> None:
        super().__init__()
        self._session = session

    def __setitem__(self, key, value) -> None:
        if key == _DEPTH_KEY and self.get(key, 0) == 0 and value == 1:
            self._session._begin()
        super().__setitem__(key, value)


class FakeSession:
    def __init__(self, db: InMemoryDB) -> None:
        self.db = db
        self.info = _TxInfo(self)
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0
        self.events: list[str] = []
        self._snapshot = None

    def _begin(self) -> None:
        self._snapshot = self.db.snapshot()

    def commit(self) -> None:
        self.commits += 1
        self.events.append("commit")
        self._snapshot = None

    def rollback(self) -> None:
        self.rollbacks += 1
        self.events.append("rollback")
        if self._snapshot is not None:
            self.db.restore(self._snapshot)
        self._snapshot = None

    def flush(self, objects=None) -> None:
        self.flushes += 1

    def expire(self, *args, **kwargs) -> None:
        pass

    def begin_nested(self):
        return nullcontext()

    def __getattr__(self, name):
        raise AssertionError(f"Test gọi Session.{name}: không được truy cập database thật")


# ======================================================================
# Fake repositories
# ======================================================================


class FakeRepo:
    model: type

    def __init__(self, db: InMemoryDB) -> None:
        self.db = db

    def _rows(self, predicate=lambda obj: True) -> list:
        return [obj for obj in self.db.rows(self.model) if predicate(obj)]

    def get_by_id(self, id_):
        return self.db.get(self.model, id_)

    def get_by_id_for_update(self, id_):
        self.db.locks.append((self.model.__name__, id_))
        return self.get_by_id(id_)

    def create(self, values):
        return self.db.add(self.model(**values))

    def add(self, obj):
        return self.db.add(obj)

    def update(self, obj, values):
        for key, value in values.items():
            setattr(obj, key, value)
        return obj

    def delete(self, obj) -> None:
        self.db.remove(obj)

    def flush(self, objects=None) -> None:
        pass

    def get_one(self, *where):
        """Chỉ hỗ trợ điều kiện dạng ``Model.Column == value`` (đủ cho các Service đang dùng)."""
        conditions = [(clause.left.key, clause.right.value) for clause in where]
        rows = self._rows(lambda obj: all(getattr(obj, key) == value for key, value in conditions))
        if len(rows) > 1:
            raise AssertionError("get_one trả về nhiều dòng")
        return rows[0] if rows else None


class FakeUserRepo(FakeRepo):
    model = User

    def get_by_email(self, email):
        rows = self._rows(lambda u: u.Email.lower() == email.lower())
        return rows[0] if rows else None

    def exists_by_email(self, email, exclude_user_id=None):
        return any(u.UserId != exclude_user_id for u in self._rows(lambda u: u.Email.lower() == email.lower()))

    def exists_by_phone(self, phone_number, exclude_user_id=None):
        return any(u.UserId != exclude_user_id for u in self._rows(lambda u: u.PhoneNumber == phone_number))

    def list_admins_for_update(self):
        rows = sorted(self._rows(lambda u: u.Role == "Admin" and not u.IsDeleted), key=lambda u: str(u.UserId))
        self.db.locks.extend(("User", u.UserId) for u in rows)
        return rows

    def list_users(self, *, role=None, account_status=None, include_deleted=False, offset=None, limit=None):
        return self._rows(
            lambda u: (role is None or u.Role == role)
            and (account_status is None or u.AccountStatus == account_status)
            and (include_deleted or not u.IsDeleted)
        )


class FakeAddressRepo(FakeRepo):
    model = Address

    def get_by_id_and_user(self, address_id, user_id):
        address = self.get_by_id(address_id)
        return address if address is not None and address.UserId == user_id else None


class FakeNotificationRepo(FakeRepo):
    model = Notification


class FakeProductRepo(FakeRepo):
    model = Product


class FakeVariantRepo(FakeRepo):
    model = ProductVariant

    def _low(self):
        rows = self._rows(lambda v: v.MinStockLevel > 0 and v.StockQuantity <= v.MinStockLevel and not v.IsDeleted)
        return sorted(rows, key=lambda v: (v.StockQuantity, v.Sku))

    def list_low_stock(self, *, offset=None, limit=None):
        rows = self._low()
        start = offset or 0
        return rows[start : start + limit] if limit is not None else rows[start:]

    def count_low_stock(self):
        return len(self._low())

    def exists_by_sku(self, sku, exclude_id=None):
        return bool(self._rows(lambda v: v.Sku == sku and v.ProductVariantId != exclude_id))

    def get_many_by_ids(self, variant_ids, *, with_product=False):
        return [v for v in self._rows(lambda v: v.ProductVariantId in set(variant_ids))]

    def get_many_by_ids_for_update(self, variant_ids):
        ids = sorted(set(variant_ids))
        self.db.locks.extend(("ProductVariant", variant_id) for variant_id in ids)
        return [self.get_by_id(variant_id) for variant_id in ids if self.get_by_id(variant_id) is not None]

    def serial_tracking_usage(self, variant_id):
        lines = {i.OrderItemId for i in self.db.rows(OrderItem) if i.ProductVariantId == variant_id}
        awaiting = {r.ShipmentReturnId for r in self.db.rows(ShipmentReturn) if r.Status == SHIPMENT_RETURN_AWAITING}
        return SerialTrackingUsage(
            sum(1 for s in self.db.rows(ProductSerial) if s.ProductVariantId == variant_id and s.Status != "WrittenOff"),
            len(lines),
            sum(1 for w in self.db.rows(WarrantyRequest)
                if w.OrderItemId in lines and w.Status in WARRANTY_OPEN_STATUSES),
            sum(1 for r in self.db.rows(ReturnRequest) if r.OrderItemId in lines and r.Status in RETURN_OPEN_STATUSES),
            len({i.ShipmentReturnId for i in self.db.rows(ShipmentReturnItem)
                 if i.OrderItemId in lines and i.ShipmentReturnId in awaiting}),
        )


class FakeSerialRepo(FakeRepo):
    model = ProductSerial

    def has_return_history(self, product_serial_id):
        return any(r.ProductSerialId == product_serial_id for r in self.db.rows(ReturnRequest)) or any(
            i.ProductSerialId == product_serial_id for i in self.db.rows(ShipmentReturnItem))

    def count_by_variant(self, variant_id, *, status=None):
        return len(self._rows(lambda s: s.ProductVariantId == variant_id and (status is None or s.Status == status)))

    def list_by_order_item(self, order_item_id):
        return self._rows(lambda s: s.OrderItemId == order_item_id)

    def list_by_order_item_for_update(self, order_item_id):
        rows = sorted(self._rows(lambda s: s.OrderItemId == order_item_id), key=lambda s: s.SerialNumber)
        self.db.locks.extend(("ProductSerial", s.ProductSerialId) for s in rows)
        return rows

    def list_by_serial_numbers_for_update(self, serial_numbers):
        wanted = set(serial_numbers)
        rows = sorted(self._rows(lambda s: s.SerialNumber in wanted), key=lambda s: s.SerialNumber)
        self.db.locks.extend(("ProductSerial", s.ProductSerialId) for s in rows)
        return rows

    def find_existing_serial_numbers(self, serial_numbers):
        wanted = set(serial_numbers)
        return {s.SerialNumber for s in self._rows(lambda s: s.SerialNumber in wanted)}

    def list_for_update(self, variant_id, *, status, limit):
        rows = sorted(
            self._rows(lambda s: s.ProductVariantId == variant_id and s.Status == status), key=lambda s: s.SerialNumber
        )[:limit]
        self.db.locks.extend(("ProductSerial", s.ProductSerialId) for s in rows)
        return rows

    def list_by_variant(self, variant_id, *, status=None, offset=None, limit=None):
        return sorted(
            self._rows(lambda s: s.ProductVariantId == variant_id and (status is None or s.Status == status)),
            key=lambda s: s.SerialNumber,
        )

    def exists_by_serial_number(self, serial_number, exclude_id=None):
        return bool(self._rows(lambda s: s.SerialNumber == serial_number and s.ProductSerialId != exclude_id))


class FakeCartRepo(FakeRepo):
    model = Cart

    def get_by_user(self, user_id, *, with_items=False):
        rows = self._rows(lambda c: c.UserId == user_id)
        return rows[0] if rows else None


class FakeCartItemRepo(FakeRepo):
    model = CartItem

    def list_by_cart(self, cart_id, *, is_selected=None, with_variant=False):
        return self._rows(lambda i: i.CartId == cart_id and (is_selected is None or i.IsSelected == is_selected))

    def get_by_id_and_cart(self, cart_item_id, cart_id):
        item = self.get_by_id(cart_item_id)
        return item if item is not None and item.CartId == cart_id else None

    def get_by_cart_and_variant(self, cart_id, variant_id):
        rows = self._rows(lambda i: i.CartId == cart_id and i.ProductVariantId == variant_id)
        return rows[0] if rows else None


class FakeShippingMethodRepo(FakeRepo):
    model = ShippingMethod

    def exists_by_code(self, code, exclude_id=None):
        return bool(self._rows(lambda m: m.Code == code and m.ShippingMethodId != exclude_id))

    def list_methods(self, *, is_active=None):
        rows = self._rows(lambda m: is_active is None or m.IsActive is is_active)
        return sorted(rows, key=lambda m: (m.BaseFee, m.Name))


class FakePaymentMethodRepo(FakeRepo):
    model = PaymentMethod


class FakeOrderRepo(FakeRepo):
    model = Order

    def get_detail(self, order_id):
        return self.get_by_id(order_id)

    def get_by_id_and_customer(self, order_id, customer_id):
        order = self.get_by_id(order_id)
        return order if order is not None and order.CustomerId == customer_id else None

    def exists_by_code(self, order_code):
        return bool(self._rows(lambda o: o.OrderCode == order_code))

    def exists_by_shipping_method(self, shipping_method_id):
        return bool(self._rows(lambda o: o.ShippingMethodId == shipping_method_id))

    def list_expired_unpaid_order_ids(
        self, *, ordered_before, order_status, payment_statuses, excluded_payment_method_code, limit
    ):
        rows = self._rows(
            lambda o: o.OrderStatus == order_status
            and o.PaymentStatus in payment_statuses
            and o.OrderedAt <= ordered_before
            and self.db.get(PaymentMethod, o.PaymentMethodId).Code != excluded_payment_method_code
        )
        return [o.OrderId for o in sorted(rows, key=lambda o: o.OrderedAt)[:limit]]


    def _filtered(self, order_status=None, payment_status=None):
        return sorted(
            self._rows(
                lambda o: (order_status is None or o.OrderStatus == order_status)
                and (payment_status is None or o.PaymentStatus == payment_status)
            ),
            key=lambda o: o.OrderCode,
        )

    def list_orders(self, *, order_status=None, payment_status=None, offset=None, limit=None, **_):
        return self._filtered(order_status, payment_status)

    def count_orders(self, *, order_status=None, payment_status=None, **_):
        return len(self._filtered(order_status, payment_status))


class FakeConversationRepo(FakeRepo):
    """Partial UNIQUE (CustomerId) WHERE Status = 'Open' như database: tạo trùng → IntegrityError 23505."""

    model = Conversation

    def create(self, values):
        if values.get("Status") == "Open" and self.get_open_by_customer(values["CustomerId"]) is not None:
            orig = SimpleNamespace(sqlstate="23505", diag=SimpleNamespace(constraint_name="UX_Conversations_CustomerId_Open"))
            raise IntegrityError("INSERT Conversations", {}, orig)
        return super().create(values)

    def get_detail(self, conversation_id):
        return self.get_by_id(conversation_id)

    def get_open_by_customer(self, customer_id):
        rows = self._rows(lambda c: c.CustomerId == customer_id and c.Status == "Open")
        return rows[0] if rows else None

    def _filtered(self, customer_id=None, assigned_staff_id=None, status=None, mode=None, unassigned=False):
        return sorted(
            self._rows(
                lambda c: (customer_id is None or c.CustomerId == customer_id)
                and (assigned_staff_id is None or c.AssignedStaffId == assigned_staff_id)
                and (status is None or c.Status == status)
                and (mode is None or c.Mode == mode)
                and (not unassigned or c.AssignedStaffId is None)
            ),
            key=lambda c: (c.CreatedAt, str(c.ConversationId)),
            reverse=True,
        )

    def list_conversations(self, *, offset=None, limit=None, **filters):
        return self._filtered(**filters)

    def count_conversations(self, **filters):
        return len(self._filtered(**filters))


class FakeMessageRepo(FakeRepo):
    model = Message

    def create(self, values):
        message = super().create(values)
        conversation = self.db.get(Conversation, message.ConversationId)
        if conversation is not None:
            conversation.messages.append(message)
        return message

    def list_by_conversation(self, conversation_id, *, offset=None, limit=None):
        return sorted(self._rows(lambda m: m.ConversationId == conversation_id), key=lambda m: (m.SentAt, str(m.MessageId)))

    def count_by_conversation(self, conversation_id, *, is_read=None):
        return len(self._rows(lambda m: m.ConversationId == conversation_id and (is_read is None or m.IsRead == is_read)))


class FakeReviewRepo(FakeRepo):
    """UNIQUE OrderItemId như database (tính cả review đã ẩn): tạo trùng → IntegrityError 23505."""

    model = Review

    def create(self, values):
        if self._rows(lambda r: r.OrderItemId == values["OrderItemId"]):
            orig = SimpleNamespace(sqlstate="23505", diag=SimpleNamespace(constraint_name="UQ_Reviews_OrderItemId"))
            raise IntegrityError("INSERT Reviews", {}, orig)
        review = super().create(values)
        review.user = self.db.get(User, review.UserId)
        return review

    def get_detail(self, review_id):
        return self.get_by_id(review_id)

    def get_by_order_item(self, order_item_id):
        rows = self._rows(lambda r: r.OrderItemId == order_item_id)
        return rows[0] if rows else None

    def exists_by_order_item(self, order_item_id):
        return bool(self._rows(lambda r: r.OrderItemId == order_item_id))

    def _visible(self, predicate, include_deleted):
        return sorted(self._rows(lambda r: predicate(r) and (include_deleted or not r.IsDeleted)),
                      key=lambda r: (r.CreatedAt, str(r.ReviewId)), reverse=True)

    def list_by_product(self, product_id, *, rating=None, include_deleted=False, offset=None, limit=None):
        return self._visible(lambda r: r.ProductId == product_id and (rating is None or r.Rating == rating), include_deleted)

    def count_by_product(self, product_id, *, rating=None, include_deleted=False):
        return len(self.list_by_product(product_id, rating=rating, include_deleted=include_deleted))

    def list_by_user(self, user_id, *, include_deleted=False, offset=None, limit=None):
        return self._visible(lambda r: r.UserId == user_id, include_deleted)

    def count_by_user(self, user_id, *, include_deleted=False):
        return len(self.list_by_user(user_id, include_deleted=include_deleted))

    def rating_summary(self, product_id):
        ratings = [r.Rating for r in self._rows(lambda r: r.ProductId == product_id and not r.IsDeleted)]
        return len(ratings), (Decimal(sum(ratings)) / Decimal(len(ratings)) if ratings else None)


class FakeReviewImageRepo(FakeRepo):
    model = ReviewImage

    def create(self, values):
        image = super().create(values)
        review = self.db.get(Review, image.ReviewId)
        if review is not None:
            review.images.append(image)
        return image

    def list_by_review(self, review_id):
        return sorted(self._rows(lambda i: i.ReviewId == review_id), key=lambda i: i.DisplayOrder)


class FakeOtpChallengeRepo(FakeRepo):
    model = OtpChallenge

    def latest_for(self, user_id, purpose):
        rows = sorted(self._rows(lambda c: c.UserId == user_id and c.Purpose == purpose),
                      key=lambda c: (c.CreatedAt, str(c.OtpChallengeId)))
        return rows[-1] if rows else None

    def count_sent_since(self, user_id, purpose, since):
        return len(self._rows(lambda c: c.UserId == user_id and c.Purpose == purpose and c.CreatedAt > since))


class FakePurchaseReceiptRepo(FakeRepo):
    model = PurchaseReceipt

    def list_by_purchase_order(self, purchase_order_id):
        return self._rows(lambda r: r.PurchaseOrderId == purchase_order_id)

    def update(self, obj, values):
        raise PermissionError("Lịch sử nhận hàng chỉ được ghi thêm")

    def delete(self, obj):
        raise PermissionError("Lịch sử nhận hàng chỉ được ghi thêm")


class FakePurchaseReceiptItemRepo(FakeRepo):
    model = PurchaseReceiptItem

    def create(self, values):
        item = super().create(values)
        receipt = self.db.get(PurchaseReceipt, item.PurchaseReceiptId)
        if receipt is not None:
            receipt.items.append(item)
        return item

    def update(self, obj, values):
        raise PermissionError("Lịch sử nhận hàng chỉ được ghi thêm")

    def delete(self, obj):
        raise PermissionError("Lịch sử nhận hàng chỉ được ghi thêm")


class FakeShipmentReturnRepo(FakeRepo):
    """UNIQUE OrderId như database (mỗi đơn tối đa một hồ sơ)."""

    model = ShipmentReturn

    def create(self, values):
        if self._rows(lambda r: r.OrderId == values["OrderId"]):
            orig = SimpleNamespace(sqlstate="23505", diag=SimpleNamespace(constraint_name="UQ_ShipmentReturns_OrderId"))
            raise IntegrityError("INSERT ShipmentReturns", {}, orig)
        return super().create(values)

    def get_by_order(self, order_id):
        rows = self._rows(lambda r: r.OrderId == order_id)
        return rows[0] if rows else None

    def get_by_order_for_update(self, order_id):
        record = self.get_by_order(order_id)
        if record is not None:
            self.db.locks.append(("ShipmentReturn", record.ShipmentReturnId))
        return record

    def _filtered(self, status):
        return self._rows(lambda r: status is None or r.Status == status)

    def list_returns(self, *, status=None, offset=None, limit=None):
        return self._filtered(status)

    def count_returns(self, *, status=None):
        return len(self._filtered(status))


class FakeShipmentReturnItemRepo(FakeRepo):
    model = ShipmentReturnItem

    def create(self, values):
        item = super().create(values)
        record = self.db.get(ShipmentReturn, item.ShipmentReturnId)
        if record is not None:
            record.items.append(item)
        return item

    def list_by_return(self, shipment_return_id):
        return sorted(self._rows(lambda i: i.ShipmentReturnId == shipment_return_id), key=lambda i: str(i.OrderItemId))


class FakeOrderItemRepo(FakeRepo):
    model = OrderItem

    def create(self, values):
        item = super().create(values)
        order = self.db.get(Order, item.OrderId)
        if order is not None:
            order.items.append(item)
        return item

    def list_by_order(self, order_id):
        return self._rows(lambda i: i.OrderId == order_id)

    def get_by_id_and_customer(self, order_item_id, customer_id):
        item = self.get_by_id(order_item_id)
        if item is None:
            return None
        order = self.db.get(Order, item.OrderId)
        return item if order is not None and order.CustomerId == customer_id else None


class FakeHistoryRepo(FakeRepo):
    model = OrderStatusHistory

    def create(self, values):
        history = super().create(values)
        order = self.db.get(Order, history.OrderId)
        if order is not None:
            order.status_histories.append(history)
        return history

    def list_by_order(self, order_id):
        return self._rows(lambda h: h.OrderId == order_id)


class FakePaymentTransactionRepo(FakeRepo):
    model = PaymentTransaction

    def list_by_order(self, order_id, *, status=None):
        return self._rows(lambda t: t.OrderId == order_id and (status is None or t.Status == status))

    def list_by_gateway_code(self, gateway_transaction_code):
        return self._rows(lambda t: t.GatewayTransactionCode == gateway_transaction_code)

    def sum_refunds_by_source(self, order_id, *, statuses):
        totals: dict = {}
        for t in self._rows(lambda t: t.OrderId == order_id and t.TransactionType == "Refund" and t.Status in statuses):
            totals[t.RefundOfPaymentTransactionId] = totals.get(t.RefundOfPaymentTransactionId, Decimal("0")) + t.Amount
        return totals


class FakePromotionRepo(FakeRepo):
    model = Promotion


class FakePromotionProductRepo(FakeRepo):
    model = PromotionProduct

    def list_by_promotion(self, promotion_id):
        return self._rows(lambda p: p.PromotionId == promotion_id)


class FakePromotionCategoryRepo(FakeRepo):
    model = PromotionCategory

    def list_by_promotion(self, promotion_id):
        return self._rows(lambda p: p.PromotionId == promotion_id)


class FakeCouponRepo(FakeRepo):
    model = Coupon

    def get_by_code(self, code, *, with_promotion=False):
        rows = self._rows(lambda c: c.Code.lower() == code.lower())
        return rows[0] if rows else None

    def get_by_code_for_update(self, code):
        coupon = self.get_by_code(code)
        if coupon is not None:
            self.db.locks.append(("Coupon", coupon.CouponId))
        return coupon


class FakeSupplierRepo(FakeRepo):
    model = Supplier


class FakePurchaseOrderRepo(FakeRepo):
    model = PurchaseOrder

    def exists_by_code(self, code):
        return bool(self._rows(lambda p: p.PurchaseOrderCode == code))

    def get_detail(self, purchase_order_id):
        return self.get_by_id(purchase_order_id)


class FakePurchaseOrderItemRepo(FakeRepo):
    model = PurchaseOrderItem

    def create(self, values):
        item = super().create(values)
        po = self.db.get(PurchaseOrder, item.PurchaseOrderId)
        if po is not None:
            po.items.append(item)
        return item

    def delete(self, obj) -> None:
        po = self.db.get(PurchaseOrder, obj.PurchaseOrderId)
        if po is not None and obj in po.items:
            po.items.remove(obj)
        super().delete(obj)

    def list_by_purchase_order(self, purchase_order_id):
        return self._rows(lambda i: i.PurchaseOrderId == purchase_order_id)

    def has_received_for_variant(self, variant_id):
        return bool(self._rows(lambda i: i.ProductVariantId == variant_id and i.ReceivedQuantity > 0))

    def get_by_id_and_purchase_order(self, item_id, purchase_order_id):
        item = self.get_by_id(item_id)
        return item if item is not None and item.PurchaseOrderId == purchase_order_id else None


class FakeWebhookEventRepo(FakeRepo):
    """Giả lập UNIQUE (Provider, AccountNumber, ProviderTransactionId) như database."""

    model = PaymentWebhookEvent

    def get_by_key(self, provider, account_number, provider_transaction_id):
        rows = self._rows(lambda e: (e.Provider, e.AccountNumber, e.ProviderTransactionId)
                          == (provider, account_number, provider_transaction_id))
        return rows[0] if rows else None

    def create(self, values):
        if self.get_by_key(values["Provider"], values["AccountNumber"], values["ProviderTransactionId"]):
            orig = SimpleNamespace(sqlstate="23505", diag=SimpleNamespace(constraint_name="UQ_PaymentWebhookEvents_ProviderTxn"))
            raise IntegrityError("INSERT PaymentWebhookEvents", {}, orig)
        return super().create(values)

    def list_unprocessed_ids(self, *, received_before, limit):
        rows = sorted(self._rows(lambda e: e.Status == "Received" and e.ReceivedAt <= received_before),
                      key=lambda e: e.ReceivedAt)
        return [e.PaymentWebhookEventId for e in rows[:limit]]

    def delete(self, obj):
        raise PermissionError("PaymentWebhookEvents không được xóa")


class FakeReconciliationRepo(FakeRepo):
    model = PaymentReconciliation

    def get_by_key(self, gateway_transaction_code, issue_type):
        rows = self._rows(lambda r: r.GatewayTransactionCode == gateway_transaction_code and r.IssueType == issue_type)
        return rows[0] if rows else None

    def _filtered(self, status, issue_type, order_id):
        return self._rows(
            lambda r: (status is None or r.Status == status)
            and (issue_type is None or r.IssueType == issue_type)
            and (order_id is None or r.OrderId == order_id)
        )

    def list_reconciliations(self, *, status=None, issue_type=None, order_id=None, offset=None, limit=None):
        return self._filtered(status, issue_type, order_id)

    def count_reconciliations(self, *, status=None, issue_type=None, order_id=None):
        return len(self._filtered(status, issue_type, order_id))

    def delete(self, obj):
        raise PermissionError("PaymentReconciliations không được xóa")


class FakeStockAdjustmentRepo(FakeRepo):
    model = StockAdjustment

    def has_opening(self, variant_id):
        return bool(self._rows(lambda a: a.ProductVariantId == variant_id and a.AdjustmentType == "Opening"))

    def _filtered(self, variant_id, adjustment_type):
        return self._rows(
            lambda a: (variant_id is None or a.ProductVariantId == variant_id)
            and (adjustment_type is None or a.AdjustmentType == adjustment_type)
        )

    def list_adjustments(self, *, variant_id=None, adjustment_type=None, offset=None, limit=None):
        return self._filtered(variant_id, adjustment_type)

    def count_adjustments(self, *, variant_id=None, adjustment_type=None):
        return len(self._filtered(variant_id, adjustment_type))

    def update(self, obj, values):
        raise PermissionError("StockAdjustments chỉ được ghi thêm")

    def delete(self, obj):
        raise PermissionError("StockAdjustments chỉ được ghi thêm")


class FakeStockAdjustmentSerialRepo(FakeRepo):
    """UNIQUE (ProductSerialId, Direction) như database: tạo trùng → IntegrityError 23505."""

    model = StockAdjustmentSerial

    def create(self, values):
        if self._rows(lambda l: l.ProductSerialId == values["ProductSerialId"] and l.Direction == values["Direction"]):
            orig = SimpleNamespace(
                sqlstate="23505", diag=SimpleNamespace(constraint_name="UQ_StockAdjustmentSerials_ProductSerialId_Direction")
            )
            raise IntegrityError("INSERT StockAdjustmentSerials", {}, orig)
        return super().create(values)

    def list_by_adjustment(self, adjustment_id):
        return self._rows(lambda l: l.StockAdjustmentId == adjustment_id)

    def list_by_serial(self, serial_id):
        return self._rows(lambda l: l.ProductSerialId == serial_id)

    def linked_serial_ids(self, serial_ids, direction):
        wanted = set(serial_ids)
        return {l.ProductSerialId for l in self._rows(lambda l: l.ProductSerialId in wanted and l.Direction == direction)}

    def update(self, obj, values):
        raise PermissionError("StockAdjustmentSerials chỉ được ghi thêm")

    def delete(self, obj):
        raise PermissionError("StockAdjustmentSerials chỉ được ghi thêm")


class FakeWarrantyRequestRepo(FakeRepo):
    """UNIQUE RequestCode và partial UNIQUE yêu cầu đang xử lý (theo serial / dòng đơn không serial) như database."""

    model = WarrantyRequest

    def list_by_product_serial(self, product_serial_id):
        return sorted(self._rows(lambda r: r.ProductSerialId == product_serial_id),
                      key=lambda r: (r.RequestedAt, str(r.WarrantyRequestId)), reverse=True)

    def create(self, values):
        constraint = None
        if self.exists_by_code(values["RequestCode"]):
            constraint = "UQ_WarrantyRequests_RequestCode"
        elif values.get("Status") in WARRANTY_OPEN_STATUSES:
            # Gọi qua class: test giả lập "transaction kia chưa commit" bằng cách thay method của instance,
            # còn ràng buộc database vẫn thấy dòng đã có.
            serial_id = values.get("ProductSerialId")
            if serial_id is not None and FakeWarrantyRequestRepo.get_open_by_product_serial(self, serial_id):
                constraint = "UX_WarrantyRequests_Serial_Open"
            elif serial_id is None and FakeWarrantyRequestRepo.get_open_by_order_item_without_serial(
                    self, values["OrderItemId"]):
                constraint = "UX_WarrantyRequests_OrderItem_Open_NoSerial"
        if constraint is not None:
            orig = SimpleNamespace(sqlstate="23505", diag=SimpleNamespace(constraint_name=constraint))
            raise IntegrityError("INSERT WarrantyRequests", {}, orig)
        return super().create(values)

    def exists_by_code(self, request_code):
        return bool(self._rows(lambda r: r.RequestCode == request_code))

    def get_by_id_and_customer(self, warranty_request_id, customer_id):
        request = self.get_by_id(warranty_request_id)
        return request if request is not None and request.CustomerId == customer_id else None

    def get_detail(self, warranty_request_id):
        return self.get_by_id(warranty_request_id)

    def get_open_by_product_serial(self, product_serial_id):
        rows = self._rows(lambda r: r.ProductSerialId == product_serial_id and r.Status in WARRANTY_OPEN_STATUSES)
        return rows[0] if rows else None

    def get_open_by_order_item_without_serial(self, order_item_id):
        rows = self._rows(lambda r: r.OrderItemId == order_item_id and r.ProductSerialId is None
                          and r.Status in WARRANTY_OPEN_STATUSES)
        return rows[0] if rows else None

    def get_latest_replacement_handover(self, product_serial_id):
        rows = self._rows(lambda r: r.ReplacementProductSerialId == product_serial_id
                          and r.ReplacementHandedOverAt is not None)
        return max(rows, key=lambda r: r.ReplacementHandedOverAt) if rows else None

    def _filtered(self, customer_id=None, assigned_staff_id=None, supplier_id=None, status=None,
                  eligibility_status=None):
        return sorted(
            self._rows(
                lambda r: (customer_id is None or r.CustomerId == customer_id)
                and (assigned_staff_id is None or r.AssignedStaffId == assigned_staff_id)
                and (supplier_id is None or r.SupplierId == supplier_id)
                and (status is None or r.Status == status)
                and (eligibility_status is None or r.EligibilityStatus == eligibility_status)
            ),
            key=lambda r: (r.RequestedAt, str(r.WarrantyRequestId)),
            reverse=True,
        )

    def list_requests(self, *, offset=None, limit=None, **filters):
        return self._filtered(**filters)

    def count_requests(self, **filters):
        return len(self._filtered(**filters))


class FakeReturnRequestRepo(FakeRepo):
    """UNIQUE RequestCode, RefundPaymentTransactionId và partial UNIQUE yêu cầu đang xử lý theo serial như database."""

    model = ReturnRequest

    def create(self, values):
        constraint = None
        if self.exists_by_code(values["RequestCode"]):
            constraint = "UQ_ReturnRequests_RequestCode"
        elif (values.get("ProductSerialId") is not None and values.get("Status") in RETURN_OPEN_STATUSES
              and FakeReturnRequestRepo.get_open_by_product_serial(self, values["ProductSerialId"])):
            constraint = "UX_ReturnRequests_Serial_Open"
        if constraint is not None:
            orig = SimpleNamespace(sqlstate="23505", diag=SimpleNamespace(constraint_name=constraint))
            raise IntegrityError("INSERT ReturnRequests", {}, orig)
        return super().create(values)

    def exists_by_code(self, request_code):
        return bool(self._rows(lambda r: r.RequestCode == request_code))

    def get_by_id_and_customer(self, return_request_id, customer_id):
        request = self.get_by_id(return_request_id)
        return request if request is not None and request.CustomerId == customer_id else None

    def get_detail(self, return_request_id):
        return self.get_by_id(return_request_id)

    def get_open_by_product_serial(self, product_serial_id):
        rows = self._rows(lambda r: r.ProductSerialId == product_serial_id and r.Status in RETURN_OPEN_STATUSES)
        return rows[0] if rows else None

    def list_open_request_codes_for_order(self, order_id):
        items = {i.OrderItemId for i in self.db.rows(OrderItem) if i.OrderId == order_id}
        return sorted(r.RequestCode for r in self._rows(lambda r: r.OrderItemId in items and r.Status in RETURN_OPEN_STATUSES))

    def list_refund_transaction_ids_for_order(self, order_id):
        items = {i.OrderItemId for i in self.db.rows(OrderItem) if i.OrderId == order_id}
        return {r.RefundPaymentTransactionId for r in self._rows(lambda r: r.OrderItemId in items)
                if r.RefundPaymentTransactionId is not None}

    def list_by_order_item(self, order_item_id):
        return sorted(self._rows(lambda r: r.OrderItemId == order_item_id),
                      key=lambda r: (r.RequestedAt, str(r.ReturnRequestId)), reverse=True)

    def _filtered(self, customer_id=None, assigned_staff_id=None, status=None, request_type=None):
        return sorted(
            self._rows(
                lambda r: (customer_id is None or r.CustomerId == customer_id)
                and (assigned_staff_id is None or r.AssignedStaffId == assigned_staff_id)
                and (status is None or r.Status == status)
                and (request_type is None or r.RequestType == request_type)
            ),
            key=lambda r: (r.RequestedAt, str(r.ReturnRequestId)),
            reverse=True,
        )

    def list_requests(self, *, offset=None, limit=None, **filters):
        return self._filtered(**filters)

    def count_requests(self, **filters):
        return len(self._filtered(**filters))

    def check_refund_link_unique(self):
        """Gọi khi flush/commit trong test cần: UNIQUE RefundPaymentTransactionId."""
        linked = [r.RefundPaymentTransactionId for r in self._rows() if r.RefundPaymentTransactionId is not None]
        if len(linked) != len(set(linked)):
            orig = SimpleNamespace(sqlstate="23505",
                                   diag=SimpleNamespace(constraint_name="UQ_ReturnRequests_RefundPaymentTransactionId"))
            raise IntegrityError("UPDATE ReturnRequests", {}, orig)

    def flush(self, objects=None) -> None:
        self.check_refund_link_unique()


class FakeNewsArticleRepo(FakeRepo):
    """UNIQUE Slug như database: tạo/sửa trùng → IntegrityError 23505 (UQ_NewsArticles_Slug)."""

    model = NewsArticle

    def _duplicate(self, slug, exclude_id=None):
        return any(a.Slug == slug and a.NewsArticleId != exclude_id for a in self._rows())

    def _raise_duplicate(self):
        orig = SimpleNamespace(sqlstate="23505", diag=SimpleNamespace(constraint_name="UQ_NewsArticles_Slug"))
        raise IntegrityError("NewsArticles", {}, orig)

    def create(self, values):
        if FakeNewsArticleRepo._duplicate(self, values["Slug"]):
            self._raise_duplicate()
        return super().create(values)

    def update(self, obj, values):
        if "Slug" in values and FakeNewsArticleRepo._duplicate(self, values["Slug"], obj.NewsArticleId):
            self._raise_duplicate()
        return super().update(obj, values)

    def get_by_slug(self, slug):
        rows = self._rows(lambda a: a.Slug == slug)
        return rows[0] if rows else None

    def exists_by_slug(self, slug, exclude_id=None):
        return FakeNewsArticleRepo._duplicate(self, slug, exclude_id)

    def _filtered(self, status):
        rows = self._rows(lambda a: status is None or a.Status == status)
        rows.sort(key=lambda a: str(a.NewsArticleId))
        rows.sort(key=lambda a: a.CreatedAt, reverse=True)
        rows.sort(key=lambda a: (a.PublishedAt is None, -(a.PublishedAt.timestamp() if a.PublishedAt else 0)))
        return rows

    def list_articles(self, *, status=None, offset=None, limit=None):
        rows = self._filtered(status)
        start = offset or 0
        return rows[start:start + limit] if limit is not None else rows[start:]

    def count_articles(self, *, status=None):
        return len(self._filtered(status))


class FakeBannerRepo(FakeRepo):
    model = Banner

    def list_banners(self, *, is_active=None):
        return sorted(self._rows(lambda b: is_active is None or b.IsActive == is_active),
                      key=lambda b: (b.DisplayOrder, str(b.BannerId)))

    def list_displayable(self, at):
        return [b for b in self.list_banners(is_active=True)
                if (b.StartDate is None or b.StartDate <= at) and (b.EndDate is None or b.EndDate >= at)]


class FakeStatisticsRepo:
    """Cùng hợp đồng với StatisticsRepository, tính bằng Python trên InMemoryDB (chỉ để test Service).

    Câu SQL thật của StatisticsRepository được kiểm tra riêng trong tests/test_statistics_queries.py (compile).
    """

    REVENUE_STATUSES = ("Delivered", "Completed")

    def __init__(self, db: InMemoryDB) -> None:
        self.db = db

    def _sum_tx(self, order_id, tx_type, status):
        return sum((t.Amount for t in self.db.rows(PaymentTransaction)
                    if t.OrderId == order_id and t.TransactionType == tx_type and t.Status == status), Decimal("0"))

    def _has_payment(self, order):
        return any(t.OrderId == order.OrderId and t.TransactionType == "Payment" and t.Status == "Success"
                   for t in self.db.rows(PaymentTransaction))

    def _delivered_in(self, start, end):
        return [o for o in self.db.rows(Order) if o.OrderStatus in self.REVENUE_STATUSES and o.DeliveredAt is not None
                and start <= o.DeliveredAt < end]

    def _revenue_orders(self, start, end):
        return [o for o in self._delivered_in(start, end) if self._has_payment(o)]

    def _revenue_items(self, start, end):
        ids = {o.OrderId for o in self._revenue_orders(start, end)}
        return [i for i in self.db.rows(OrderItem) if i.OrderId in ids]

    def count_orders_by_status(self, start, end):
        counts: dict = {}
        for order in self.db.rows(Order):
            if start <= order.OrderedAt < end:
                counts[order.OrderStatus] = counts.get(order.OrderStatus, 0) + 1
        return counts

    def revenue_totals(self, start, end):
        from app.repositories.statistics import RevenueTotals

        orders = self._revenue_orders(start, end)
        return RevenueTotals(
            len(orders),
            sum((o.TotalAmount for o in orders), Decimal("0")),
            sum((o.ShippingFee for o in orders), Decimal("0")),
            sum((self._sum_tx(o.OrderId, "Payment", "Success") for o in orders), Decimal("0")),
            sum((self._sum_tx(o.OrderId, "Refund", "Success") for o in orders), Decimal("0")),
            sum((self._sum_tx(o.OrderId, "Refund", "Pending") for o in orders), Decimal("0")),
        )

    def count_delivered_without_payment(self, start, end):
        return sum(1 for o in self._delivered_in(start, end) if not self._has_payment(o))

    def cogs_totals(self, start, end):
        from app.repositories.statistics import CogsTotals

        items = self._revenue_items(start, end)
        return CogsTotals(
            len(items),
            sum(i.Quantity for i in items),
            sum((i.UnitCost * i.Quantity for i in items if i.UnitCost > 0), Decimal("0")),
            sum(1 for i in items if i.UnitCost == 0),
        )

    def top_products(self, start, end, *, rank_by, limit):
        from app.repositories.statistics import TopProductRow

        grouped: dict = {}
        for item in self._revenue_items(start, end):
            quantity, revenue = grouped.get(item.ProductVariantId, (0, Decimal("0")))
            grouped[item.ProductVariantId] = (quantity + item.Quantity, revenue + item.LineTotal)
        rows = []
        for variant_id, (quantity, revenue) in grouped.items():
            variant = self.db.get(ProductVariant, variant_id)
            product = self.db.get(Product, variant.ProductId)
            rows.append(TopProductRow(variant_id, product.ProductId, product.Name, variant.Sku, variant.VariantName,
                                      quantity, revenue))
        rows.sort(key=lambda r: str(r.product_variant_id))
        if rank_by == "quantity":
            rows.sort(key=lambda r: (r.quantity, r.revenue), reverse=True)
        else:
            rows.sort(key=lambda r: (r.revenue, r.quantity), reverse=True)
        return rows[:limit]

    def returned_quantities(self, start, end, variant_ids):
        items = {i.OrderItemId: i for i in self._revenue_items(start, end) if i.ProductVariantId in set(variant_ids)}
        totals: dict = {}
        for request in self.db.rows(ReturnRequest):
            item = items.get(request.OrderItemId)
            if item is not None and request.RequestType == "Return" and request.Status == "Completed":
                totals[item.ProductVariantId] = totals.get(item.ProductVariantId, 0) + request.Quantity
        return totals

    def _variants(self):
        rows = [v for v in self.db.rows(ProductVariant) if not v.IsDeleted]
        rows.sort(key=lambda v: (self.db.get(Product, v.ProductId).Name, v.Sku, str(v.ProductVariantId)))
        return rows

    def count_inventory_variants(self):
        return len(self._variants())

    def list_inventory(self, *, offset, limit):
        from app.repositories.statistics import InventoryRow

        return [InventoryRow(v.ProductVariantId, v.ProductId, self.db.get(Product, v.ProductId).Name, v.Sku,
                             v.VariantName, v.IsSerialTracked, v.StockQuantity, v.MinStockLevel)
                for v in self._variants()[offset:offset + limit]]

    def stock_total(self):
        return sum(v.StockQuantity for v in self._variants())

    def serial_status_counts(self, variant_ids=None):
        live = {v.ProductVariantId for v in self._variants()}
        counts: dict = {}
        for serial in self.db.rows(ProductSerial):
            if serial.ProductVariantId in live and (variant_ids is None or serial.ProductVariantId in set(variant_ids)):
                key = (serial.ProductVariantId, serial.Status)
                counts[key] = counts.get(key, 0) + 1
        return counts

    def serial_status_totals(self):
        totals: dict = {}
        for (_, status), count in self.serial_status_counts().items():
            totals[status] = totals.get(status, 0) + count
        return totals


def _service_request_of(db, row):
    if row.WarrantyRequestId is not None:
        return db.get(WarrantyRequest, row.WarrantyRequestId)
    if row.ReturnRequestId is not None:
        return db.get(ReturnRequest, row.ReturnRequestId)
    return None


class FakeServiceAttachmentRepo(FakeRepo):
    model = ServiceRequestAttachment

    def create(self, values):
        attachment = super().create(values)
        request = _service_request_of(self.db, attachment)
        if request is not None:
            request.attachments.append(attachment)
        return attachment


class FakeServiceHistoryRepo(FakeRepo):
    """Lịch sử chỉ ghi thêm."""

    model = ServiceRequestHistory

    def create(self, values):
        history = super().create(values)
        request = _service_request_of(self.db, history)
        if request is not None:
            request.histories.append(history)
        return history

    def update(self, obj, values):
        raise PermissionError("ServiceRequestHistories chỉ được ghi thêm")

    def delete(self, obj):
        raise PermissionError("ServiceRequestHistories chỉ được ghi thêm")


# ======================================================================
# Gắn fake vào Service
# ======================================================================


def notification_service(db, session) -> NotificationService:
    svc = NotificationService(session, clock=fixed_clock)
    svc.notifications = FakeNotificationRepo(db)
    return svc


def variant_service(db, session) -> ProductVariantService:
    svc = ProductVariantService(session, clock=fixed_clock)
    svc.variants = FakeVariantRepo(db)
    svc.products = FakeProductRepo(db)
    svc.users = FakeUserRepo(db)
    svc.notifications = notification_service(db, session)
    return svc


def inventory_service(db, session) -> InventoryService:
    svc = InventoryService(session, clock=fixed_clock)
    svc.variants = FakeVariantRepo(db)
    svc.adjustments = FakeStockAdjustmentRepo(db)
    svc.purchase_items = FakePurchaseOrderItemRepo(db)
    svc.serials = FakeSerialRepo(db)
    svc.serial_links = FakeStockAdjustmentSerialRepo(db)
    svc.variant_service = variant_service(db, session)
    return svc


def coupon_service(db, session) -> CouponService:
    svc = CouponService(session, clock=fixed_clock)
    svc.coupons = FakeCouponRepo(db)
    svc.promotions = FakePromotionRepo(db)
    svc.promotion_products = FakePromotionProductRepo(db)
    svc.promotion_categories = FakePromotionCategoryRepo(db)
    svc.orders = FakeOrderRepo(db)
    svc.carts = FakeCartRepo(db)
    svc.cart_items = FakeCartItemRepo(db)
    return svc


def order_service(db, session, clock=fixed_clock) -> OrderService:
    svc = OrderService(session, clock=clock)
    svc.orders = FakeOrderRepo(db)
    svc.order_items = FakeOrderItemRepo(db)
    svc.histories = FakeHistoryRepo(db)
    svc.users = FakeUserRepo(db)
    svc.addresses = FakeAddressRepo(db)
    svc.carts = FakeCartRepo(db)
    svc.cart_items = FakeCartItemRepo(db)
    svc.variants = FakeVariantRepo(db)
    svc.products = FakeProductRepo(db)
    svc.serials = FakeSerialRepo(db)
    svc.shipment_returns = FakeShipmentReturnRepo(db)
    svc.shipment_return_items = FakeShipmentReturnItemRepo(db)
    svc.returns = FakeReturnRequestRepo(db)
    svc.shipping_methods = FakeShippingMethodRepo(db)
    svc.payment_methods = FakePaymentMethodRepo(db)
    svc.payment_transactions = FakePaymentTransactionRepo(db)
    svc.coupon_service = coupon_service(db, session)
    svc.variant_service = variant_service(db, session)
    svc.notifications = notification_service(db, session)
    return svc


def chat_service(db, session, clock=fixed_clock) -> ChatService:
    svc = ChatService(session, clock=clock)
    svc.conversations = FakeConversationRepo(db)
    svc.messages = FakeMessageRepo(db)
    svc.users = FakeUserRepo(db)
    svc.products = FakeProductRepo(db)
    return svc


def review_service(db, session, clock=fixed_clock) -> ReviewService:
    svc = ReviewService(session, clock=clock)
    svc.reviews = FakeReviewRepo(db)
    svc.images = FakeReviewImageRepo(db)
    svc.order_items = FakeOrderItemRepo(db)
    svc.orders = FakeOrderRepo(db)
    svc.variants = FakeVariantRepo(db)
    svc.products = FakeProductRepo(db)
    return svc


def warranty_service(db, session, clock=fixed_clock) -> WarrantyService:
    svc = WarrantyService(session, clock=clock)
    svc.requests = FakeWarrantyRequestRepo(db)
    svc.attachments = FakeServiceAttachmentRepo(db)
    svc.histories = FakeServiceHistoryRepo(db)
    svc.order_items = FakeOrderItemRepo(db)
    svc.orders = FakeOrderRepo(db)
    svc.variants = FakeVariantRepo(db)
    svc.serials = FakeSerialRepo(db)
    svc.suppliers = FakeSupplierRepo(db)
    svc.returns = FakeReturnRequestRepo(db)
    svc.users = FakeUserRepo(db)
    svc.variant_service = variant_service(db, session)
    svc.notifications = notification_service(db, session)
    return svc


def return_service(db, session, clock=fixed_clock, policy=None, gateway=None) -> ReturnService:
    svc = ReturnService(session, policy=policy, gateway=gateway, clock=clock)
    svc.requests = FakeReturnRequestRepo(db)
    svc.attachments = FakeServiceAttachmentRepo(db)
    svc.histories = FakeServiceHistoryRepo(db)
    svc.order_items = FakeOrderItemRepo(db)
    svc.orders = FakeOrderRepo(db)
    svc.variants = FakeVariantRepo(db)
    svc.serials = FakeSerialRepo(db)
    svc.warranty_requests = FakeWarrantyRequestRepo(db)
    svc.transactions = FakePaymentTransactionRepo(db)
    svc.users = FakeUserRepo(db)
    svc.variant_service = variant_service(db, session)
    svc.notifications = notification_service(db, session)
    payments = PaymentService(session, gateway=gateway, clock=clock)
    payments.methods = FakePaymentMethodRepo(db)
    payments.transactions = FakePaymentTransactionRepo(db)
    payments.orders = FakeOrderRepo(db)
    payments.users = FakeUserRepo(db)
    payments.reconciliations = FakeReconciliationRepo(db)
    payments.returns = svc.requests
    payments.notifications = notification_service(db, session)
    svc.payments = payments
    return svc


def statistics_service(db, session, clock=fixed_clock) -> StatisticsService:
    svc = StatisticsService(session, clock=clock)
    svc.stats = FakeStatisticsRepo(db)
    return svc


def content_service(db, session, clock=fixed_clock) -> ContentService:
    svc = ContentService(session, clock=clock)
    svc.articles = FakeNewsArticleRepo(db)
    svc.banners = FakeBannerRepo(db)
    return svc


def shipping_method_service(db, session) -> ShippingMethodService:
    svc = ShippingMethodService(session, clock=fixed_clock)
    svc.methods = FakeShippingMethodRepo(db)
    svc.orders = FakeOrderRepo(db)
    return svc


def payment_service(db, session, gateway=None) -> PaymentService:
    svc = PaymentService(session, gateway=gateway, clock=fixed_clock)
    svc.methods = FakePaymentMethodRepo(db)
    svc.transactions = FakePaymentTransactionRepo(db)
    svc.orders = FakeOrderRepo(db)
    svc.users = FakeUserRepo(db)
    svc.reconciliations = FakeReconciliationRepo(db)
    svc.returns = FakeReturnRequestRepo(db)
    svc.notifications = notification_service(db, session)
    return svc


def payment_webhook_service(db, session, *, account_number="0123456789", gateway=None):
    from app.services.payment_webhook import PaymentWebhookService

    svc = PaymentWebhookService(session, account_number=account_number, clock=fixed_clock)
    svc.events = FakeWebhookEventRepo(db)
    svc.payments = payment_service(db, session, gateway=gateway)
    return svc


def purchase_order_service(db, session) -> PurchaseOrderService:
    svc = PurchaseOrderService(session, clock=fixed_clock)
    svc.purchase_orders = FakePurchaseOrderRepo(db)
    svc.items = FakePurchaseOrderItemRepo(db)
    svc.receipts = FakePurchaseReceiptRepo(db)
    svc.receipt_items = FakePurchaseReceiptItemRepo(db)
    svc.suppliers = FakeSupplierRepo(db)
    svc.variants = FakeVariantRepo(db)
    svc.users = FakeUserRepo(db)
    svc.inventory = inventory_service(db, session)
    svc.notifications = notification_service(db, session)
    return svc


# ======================================================================
# Dữ liệu mẫu
# ======================================================================


class Factory:
    def __init__(self, db: InMemoryDB) -> None:
        self.db = db
        self._seq = 0

    def _next(self) -> int:
        self._seq += 1
        return self._seq

    def user(self, role="Customer", *, status="Active", deleted=False) -> User:
        n = self._next()
        return self.db.add(
            User(
                Email=f"user{n}@example.com",
                PhoneNumber=f"09000000{n:02d}",
                PasswordHash="hash",
                FullName=f"User {n}",
                Role=role,
                AccountStatus=status,
                IsDeleted=deleted,
            )
        )

    def actor(self, user: User) -> Actor:
        return Actor(user.UserId, user.Role)

    def variant(self, *, stock=10, price="100000.00", cost="70000.00", status="Active", active=True,
                serial_tracked=False, min_stock=0) -> ProductVariant:
        n = self._next()
        category = self.db.add(Category(Name=f"Cat {n}", Slug=f"cat-{n}"))
        brand = self.db.add(Brand(Name=f"Brand {n}", Slug=f"brand-{n}"))
        product = self.db.add(
            Product(
                CategoryId=category.CategoryId,
                BrandId=brand.BrandId,
                Name=f"Product {n}",
                Slug=f"product-{n}",
                WarrantyMonths=12,
                Status=status,
            )
        )
        variant = self.db.add(
            ProductVariant(
                ProductId=product.ProductId,
                Sku=f"SKU-{n}",
                VariantName=f"Variant {n}",
                Price=Decimal(price),
                CostPrice=Decimal(cost),
                StockQuantity=stock,
                MinStockLevel=min_stock,
                IsActive=active,
                IsSerialTracked=serial_tracked,
            )
        )
        variant.product = product
        return variant

    def shipping_method(self, fee="30000.00") -> ShippingMethod:
        n = self._next()
        return self.db.add(ShippingMethod(Code=f"SHIP{n}", Name="Giao thường", BaseFee=Decimal(fee), EstimatedDays=3))

    def payment_method(self, code="QR") -> PaymentMethod:
        return self.db.add(PaymentMethod(Code=code, Name=code))

    def cart_with(self, user: User, *lines: tuple[ProductVariant, int], unit_price=None) -> Cart:
        cart = self.db.add(Cart(UserId=user.UserId))
        for variant, quantity in lines:
            item = self.db.add(
                CartItem(
                    CartId=cart.CartId,
                    ProductVariantId=variant.ProductVariantId,
                    Quantity=quantity,
                    UnitPrice=Decimal(unit_price) if unit_price is not None else variant.Price,
                )
            )
            item.product_variant = variant
        return cart

    def coupon(self, creator: User, *, code="SALE10", value="10", usage_limit=None, used=0, active=True,
               start=None, end=None, min_order="0", promotion_status="Active") -> Coupon:
        promotion = self.db.add(
            Promotion(
                CreatedByUserId=creator.UserId,
                Name="Khuyến mãi",
                DiscountType="Percentage",
                DiscountValue=Decimal(value),
                MinOrderValue=Decimal(min_order),
                StartDate=start or datetime(2026, 1, 1, tzinfo=timezone.utc),
                EndDate=end or datetime(2026, 12, 31, tzinfo=timezone.utc),
                Status=promotion_status,
            )
        )
        coupon = self.db.add(
            Coupon(
                PromotionId=promotion.PromotionId,
                CreatedByUserId=creator.UserId,
                Code=code,
                Name="Mã giảm",
                UsageLimit=usage_limit,
                UsedCount=used,
                IsActive=active,
            )
        )
        coupon.promotion = promotion
        return coupon

    def order(self, customer: User, payment_method: PaymentMethod, *, status="Pending", payment_status="Pending",
              total="130000.00", lines: tuple = (), coupon: Coupon | None = None,
              ordered_at: datetime | None = None) -> Order:
        n = self._next()
        shipping = self.shipping_method()
        order = self.db.add(
            Order(
                OrderCode=f"VT{n:06d}",
                CustomerId=customer.UserId,
                ShippingMethodId=shipping.ShippingMethodId,
                PaymentMethodId=payment_method.PaymentMethodId,
                CouponId=coupon.CouponId if coupon else None,
                Subtotal=Decimal(total),
                ShippingFee=Decimal("0"),
                DiscountAmount=Decimal("0"),
                TotalAmount=Decimal(total),
                OrderStatus=status,
                PaymentStatus=payment_status,
                ReceiverName="Nguyễn Văn A",
                ReceiverPhone="0900000000",
                ShippingAddress="1 Đường A, Phường B, Tỉnh C",
                OrderedAt=ordered_at or NOW,
            )
        )
        order.payment_method = payment_method
        for variant, quantity in lines:
            item = self.db.add(
                OrderItem(
                    OrderId=order.OrderId,
                    ProductVariantId=variant.ProductVariantId,
                    ProductName=variant.product.Name,
                    Sku=variant.Sku,
                    VariantInfo=variant.VariantName,
                    WarrantyMonths=12,
                    Quantity=quantity,
                    UnitPrice=variant.Price,
                    UnitCost=variant.CostPrice,
                    DiscountAmount=Decimal("0"),
                    LineTotal=variant.Price * quantity,
                )
            )
            order.items.append(item)
        return order

    def payment(self, order: Order, *, status="Success", amount=None, gateway_code="GW-1",
                tx_type="Payment", refund_of: PaymentTransaction | None = None) -> PaymentTransaction:
        return self.db.add(
            PaymentTransaction(
                OrderId=order.OrderId,
                PaymentMethodId=order.PaymentMethodId,
                GatewayTransactionCode=gateway_code,
                TransactionType=tx_type,
                Amount=Decimal(amount) if amount is not None else order.TotalAmount,
                Status=status,
                PaidAt=NOW if status == "Success" else None,
                RefundOfPaymentTransactionId=refund_of.PaymentTransactionId if refund_of is not None else None,
            )
        )

    def supplier(self, *, active=True) -> Supplier:
        n = self._next()
        return self.db.add(
            Supplier(SupplierCode=f"NCC{n}", Name=f"Nhà cung cấp {n}", PhoneNumber="0280000000", Address="HCM",
                     IsActive=active)
        )

    def notifications_for(self, user: User) -> list[Notification]:
        return [n for n in self.db.rows(Notification) if n.UserId == user.UserId]
