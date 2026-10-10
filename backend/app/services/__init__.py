"""Service layer: nghiệp vụ và điều phối Repository; quản lý transaction theo use case."""

from .actor import ADMIN_ONLY, ANY_ROLE, CUSTOMER_ONLY, STAFF_OR_ADMIN, Actor, has_role, require_role
from .base import BaseService
from .chat import ChatService
from .content import ContentService
from .catalog import (
    BrandService,
    CategoryService,
    ProductImageService,
    ProductSerialService,
    ProductService,
    ProductVariantService,
)
from .exceptions import (
    AccountLockedError,
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    EmailNotVerifiedError,
    InvalidOtpError,
    TooManyRequestsError,
    NotFoundError,
    PaymentGatewayError,
    PaymentVerificationError,
    PermissionDeniedError,
    ServiceError,
)
from .inventory import InventoryService, ReceiptLine, weighted_average_cost
from .order import QR_PAYMENT_TTL, OrderService, order_item_cogs
from .payment import PaymentService
from .purchasing import PurchaseOrderService, SupplierService
from .review import ReviewService
from .statistics import StatisticsService, statistics_period
from .returns import ReturnPolicy, ReturnService
from .shipping_method import ShippingMethodService
from .warranty import WarrantyService
from .promotion import (
    CouponService,
    PromotionService,
    allocate_discount,
    calculate_discount,
    is_promotion_in_effect,
)
from .ports import (
    GatewayPaymentResult,
    GatewayRefundResult,
    OtpSender,
    PasswordHasher,
    PaymentGateway,
    QrPaymentRequest,
)
from .wishlist_cart import CartService, WishlistService
from .user import (
    ACCOUNT_STATUS_ACTIVE,
    ACCOUNT_STATUS_LOCKED,
    ACCOUNT_STATUSES,
    AccountSettings,
    AddressService,
    NotificationService,
    UserService,
)

__all__ = [
    "Actor",
    "require_role",
    "has_role",
    "STAFF_OR_ADMIN",
    "ADMIN_ONLY",
    "CUSTOMER_ONLY",
    "ANY_ROLE",
    "InventoryService",
    "ReceiptLine",
    "weighted_average_cost",
    "QR_PAYMENT_TTL",
    "BaseService",
    "ServiceError",
    "NotFoundError",
    "ConflictError",
    "BusinessRuleError",
    "AuthenticationError",
    "AccountLockedError",
    "EmailNotVerifiedError",
    "InvalidOtpError",
    "TooManyRequestsError",
    "PasswordHasher",
    "OtpSender",
    "AccountSettings",
    "ACCOUNT_STATUS_ACTIVE",
    "ACCOUNT_STATUS_LOCKED",
    "ACCOUNT_STATUSES",
    "UserService",
    "AddressService",
    "NotificationService",
    "CategoryService",
    "BrandService",
    "ProductService",
    "ProductVariantService",
    "ProductImageService",
    "ProductSerialService",
    "WishlistService",
    "CartService",
    "OrderService",
    "order_item_cogs",
    "ChatService",
    "PaymentService",
    "PaymentGateway",
    "QrPaymentRequest",
    "GatewayPaymentResult",
    "GatewayRefundResult",
    "PaymentVerificationError",
    "PaymentGatewayError",
    "PermissionDeniedError",
    "PromotionService",
    "CouponService",
    "calculate_discount",
    "allocate_discount",
    "is_promotion_in_effect",
    "SupplierService",
    "PurchaseOrderService",
    "ReviewService",
    "ShippingMethodService",
    "WarrantyService",
    "ReturnService",
    "ReturnPolicy",
    "ContentService",
    "StatisticsService",
    "statistics_period",
]
