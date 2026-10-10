"""BaseService và ranh giới transaction cho từng use case.

- Service nhận Session từ bên ngoài (Router/dependency), không tạo SessionLocal.
- Mỗi use case public mở ``with self.transaction():``. Khi use case kết thúc thành công thì commit,
  khi có lỗi thì rollback.
- Khi một use case được gọi bên trong use case khác (cùng Session), chỉ use case ngoài cùng
  commit/rollback, nên nhiều Service có thể tham gia chung một transaction.
- Vi phạm ràng buộc của database (IntegrityError, ví dụ hai request đồng thời cùng tạo một mã)
  được chuyển thành lỗi nghiệp vụ tại use case ngoài cùng, sau khi đã rollback.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .exceptions import BusinessRuleError, ConflictError, ServiceError

_DEPTH_KEY = "vietech_transaction_depth"

# SQLSTATE của PostgreSQL cho các vi phạm ràng buộc.
_UNIQUE_VIOLATION = "23505"
_FOREIGN_KEY_VIOLATION = "23503"
_CHECK_VIOLATION = "23514"
_NOT_NULL_VIOLATION = "23502"

# Mã lỗi trùng theo tên constraint/unique index (giữ đúng code mà Service đang dùng khi kiểm tra trước).
UNIQUE_CONSTRAINT_CODES = {
    "UX_Users_Email_Lower": "email_exists",
    "UQ_Users_PhoneNumber": "phone_number_exists",
    "UQ_Categories_Slug": "category_slug_exists",
    "UQ_Brands_Slug": "brand_slug_exists",
    "UQ_Products_Slug": "product_slug_exists",
    "UQ_ProductVariants_Sku": "sku_exists",
    "UQ_ProductSerials_SerialNumber": "serial_exists",
    "UQ_StockAdjustmentSerials_ProductSerialId_Direction": "serial_already_adjusted",
    "UQ_WishlistItems_WishlistId_ProductId": "wishlist_item_exists",
    "UQ_CartItems_CartId_ProductVariantId": "cart_item_exists",
    "UQ_ShippingMethods_Code": "shipping_method_code_exists",
    "UQ_Orders_OrderCode": "order_code_exists",
    "UQ_PaymentMethods_Code": "payment_method_code_exists",
    "UX_Coupons_Code_Lower": "coupon_code_exists",
    "UQ_Suppliers_SupplierCode": "supplier_code_exists",
    "UQ_PurchaseOrders_PurchaseOrderCode": "purchase_order_code_exists",
    "UQ_Reviews_OrderItemId": "review_exists",
    "UX_Conversations_CustomerId_Open": "open_conversation_exists",
    "UQ_WarrantyRequests_RequestCode": "warranty_request_code_exists",
    "UX_WarrantyRequests_Serial_Open": "warranty_request_open",
    "UX_WarrantyRequests_OrderItem_Open_NoSerial": "warranty_request_open",
    "UQ_ReturnRequests_RequestCode": "return_request_code_exists",
    "UX_ReturnRequests_Serial_Open": "return_request_open",
    "UQ_ReturnRequests_RefundPaymentTransactionId": "return_refund_exists",
    "UQ_NewsArticles_Slug": "news_article_slug_exists",
    "UQ_PaymentWebhookEvents_ProviderTxn": "payment_webhook_event_exists",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def integrity_error_to_service_error(exc: IntegrityError) -> ServiceError | None:
    """Đổi IntegrityError thành lỗi nghiệp vụ khi xác định được loại vi phạm; không xác định được thì trả None."""
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None)
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
    if sqlstate == _UNIQUE_VIOLATION:
        return ConflictError(
            "Dữ liệu đã tồn tại", code=UNIQUE_CONSTRAINT_CODES.get(constraint, "duplicate_value")
        )
    if sqlstate == _FOREIGN_KEY_VIOLATION:
        return BusinessRuleError("Dữ liệu tham chiếu không hợp lệ hoặc đang được sử dụng", code="reference_violation")
    if sqlstate == _CHECK_VIOLATION:
        return BusinessRuleError("Dữ liệu vi phạm ràng buộc nghiệp vụ", code="check_violation")
    if sqlstate == _NOT_NULL_VIOLATION:
        return BusinessRuleError("Thiếu dữ liệu bắt buộc", code="not_null_violation")
    return None


class BaseService:
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        self.session = session
        self._clock = clock

    def now(self) -> datetime:
        return self._clock()

    def in_transaction(self) -> bool:
        """True khi đang ở bên trong một use case (``transaction()``) của Session này."""
        return self.session.info.get(_DEPTH_KEY, 0) > 0

    def require_enclosing_use_case(self) -> None:
        """Helper nội bộ (đổi tồn kho, dùng coupon, tạo thông báo...) chỉ được gọi bên trong một use case.

        Ngăn Router gọi thẳng helper để bỏ qua kiểm tra quyền/trạng thái của use case.
        """
        if not self.in_transaction():
            raise BusinessRuleError(
                "Thao tác nội bộ chỉ được gọi bên trong một nghiệp vụ", code="internal_operation"
            )

    @contextmanager
    def transaction(self) -> Iterator[None]:
        depth = self.session.info.get(_DEPTH_KEY, 0)
        self.session.info[_DEPTH_KEY] = depth + 1
        try:
            yield
            if depth == 0:
                self.session.commit()
        except IntegrityError as exc:
            if depth != 0:
                raise
            self.session.rollback()
            mapped = integrity_error_to_service_error(exc)
            if mapped is None:
                raise
            raise mapped from exc
        except BaseException:
            if depth == 0:
                self.session.rollback()
            raise
        finally:
            self.session.info[_DEPTH_KEY] = depth

    @staticmethod
    def _page_args(page: int, page_size: int) -> tuple[int, int]:
        """Đổi page/page_size (bắt đầu từ 1) thành offset/limit."""
        if page < 1 or page_size < 1:
            raise BusinessRuleError("page và page_size phải lớn hơn 0", code="invalid_pagination")
        return (page - 1) * page_size, page_size
