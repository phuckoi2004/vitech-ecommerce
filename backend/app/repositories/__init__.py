"""Repository layer: truy vấn và thao tác dữ liệu qua SQLAlchemy Session (không commit)."""

from .base import BaseRepository
from .user import (
    AddressRepository,
    NotificationRepository,
    UserRepository,
)
from .catalog import (
    BrandRepository,
    CategoryRepository,
    ProductImageRepository,
    ProductRepository,
    ProductSerialRepository,
    ProductVariantRepository,
)
from .wishlist_cart import (
    CartItemRepository,
    CartRepository,
    WishlistItemRepository,
    WishlistRepository,
)
from .order import (
    OrderItemRepository,
    OrderRepository,
    OrderStatusHistoryRepository,
    ShippingMethodRepository,
)
from .payment import (
    PaymentMethodRepository,
    PaymentTransactionRepository,
)
from .promotion import (
    CouponRepository,
    PromotionCategoryRepository,
    PromotionProductRepository,
    PromotionRepository,
)
from .purchasing import (
    PurchaseOrderItemRepository,
    PurchaseOrderRepository,
    SupplierRepository,
)
from .review import (
    ReviewImageRepository,
    ReviewRepository,
)
from .chat import (
    ConversationRepository,
    MessageRepository,
)
from .service_request import (
    ReturnRequestRepository,
    ServiceRequestAttachmentRepository,
    ServiceRequestHistoryRepository,
    WarrantyRequestRepository,
)
from .content import (
    BannerRepository,
    NewsArticleRepository,
)

__all__ = [
    "BaseRepository",
    "AddressRepository",
    "NotificationRepository",
    "UserRepository",
    "BrandRepository",
    "CategoryRepository",
    "ProductImageRepository",
    "ProductRepository",
    "ProductSerialRepository",
    "ProductVariantRepository",
    "CartItemRepository",
    "CartRepository",
    "WishlistItemRepository",
    "WishlistRepository",
    "OrderItemRepository",
    "OrderRepository",
    "OrderStatusHistoryRepository",
    "ShippingMethodRepository",
    "PaymentMethodRepository",
    "PaymentTransactionRepository",
    "CouponRepository",
    "PromotionCategoryRepository",
    "PromotionProductRepository",
    "PromotionRepository",
    "PurchaseOrderItemRepository",
    "PurchaseOrderRepository",
    "SupplierRepository",
    "ReviewImageRepository",
    "ReviewRepository",
    "ConversationRepository",
    "MessageRepository",
    "ReturnRequestRepository",
    "ServiceRequestAttachmentRepository",
    "ServiceRequestHistoryRepository",
    "WarrantyRequestRepository",
    "BannerRepository",
    "NewsArticleRepository",
]
