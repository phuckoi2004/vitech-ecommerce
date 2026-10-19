"""Shared Router dependencies for the business APIs (Stage 6).

Routers stay thin: they read the authenticated Actor, validate input with Schemas and call one Service
method. Each Service is provided through a dependency so tests can replace it without a database.
Services own their transactions (``BaseService.transaction``), so Routers never commit.
"""

from collections.abc import Callable
from typing import Annotated, TypeVar

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_actor, get_optional_actor
from app.core.storage import AvatarStorage, get_avatar_storage
from app.database import get_db
from app.integrations.sepay import SePayConfigError, SePayQrGateway, SePaySettings
from app.services import STAFF_OR_ADMIN, Actor, require_role
from app.services.catalog import (
    BrandService,
    CategoryService,
    ProductImageService,
    ProductSerialService,
    ProductService,
    ProductVariantService,
)
from app.services.chat import ChatService
from app.services.catalog_item import CatalogItemService
from app.services.content import ContentService
from app.services.inventory import InventoryService
from app.services.order import OrderService
from app.services.payment import PaymentService
from app.services.ports import PaymentGateway
from app.services.product_media import ProductMediaService
from app.services.promotion import CouponService, PromotionService
from app.services.purchasing import PurchaseOrderService, SupplierService
from app.services.returns import ReturnPolicy, ReturnService
from app.services.review import ReviewService
from app.services.shipping_method import ShippingMethodService
from app.services.statistics import StatisticsService
from app.services.statistics_report import StatisticsReportService
from app.services.user import AddressService, NotificationService
from app.services.warranty import WarrantyService
from app.services.wishlist_cart import CartService, WishlistService

Database = Annotated[Session, Depends(get_db)]
CurrentActor = Annotated[Actor, Depends(get_current_actor)]
OptionalActor = Annotated[Actor | None, Depends(get_optional_actor)]


def require_internal_actor(actor: CurrentActor) -> Actor:
    """Router-level guard for every ``/admin`` route: only Staff/Admin reach internal Services.

    Services still check the exact role and ownership; this keeps customers away from internal schemas.
    """
    require_role(actor, *STAFF_OR_ADMIN)
    return actor


InternalOnly = Depends(require_internal_actor)
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def get_payment_gateway() -> PaymentGateway | None:
    """SePay QR gateway from the environment; None while SePay is not configured.

    PaymentService then refuses QR payments with ``payment_gateway_not_configured``.
    """
    try:
        return SePayQrGateway(SePaySettings.from_env())
    except SePayConfigError:
        return None


def get_return_policy() -> ReturnPolicy:
    return ReturnPolicy.from_env()


S = TypeVar("S")


def _session_service(cls: Callable[[Session], S]) -> Callable[[Session], S]:
    def provide(db: Database) -> S:
        return cls(db)

    provide.__name__ = f"get_{cls.__name__}"
    return provide


get_category_service = _session_service(CategoryService)
get_brand_service = _session_service(BrandService)
get_product_service = _session_service(ProductService)
get_variant_service = _session_service(ProductVariantService)
get_catalog_item_service = _session_service(CatalogItemService)
get_image_service = _session_service(ProductImageService)
get_serial_service = _session_service(ProductSerialService)
get_wishlist_service = _session_service(WishlistService)
get_cart_service = _session_service(CartService)
get_order_service = _session_service(OrderService)
get_shipping_method_service = _session_service(ShippingMethodService)
get_promotion_service = _session_service(PromotionService)
get_coupon_service = _session_service(CouponService)
get_supplier_service = _session_service(SupplierService)
get_purchase_order_service = _session_service(PurchaseOrderService)
get_inventory_service = _session_service(InventoryService)
get_review_service = _session_service(ReviewService)
get_chat_service = _session_service(ChatService)
get_warranty_service = _session_service(WarrantyService)
get_content_service = _session_service(ContentService)
get_statistics_service = _session_service(StatisticsService)
get_report_service = _session_service(StatisticsReportService)
get_address_service = _session_service(AddressService)
get_notification_service = _session_service(NotificationService)


def get_payment_service(
    db: Database, gateway: Annotated[PaymentGateway | None, Depends(get_payment_gateway)]
) -> PaymentService:
    return PaymentService(db, gateway=gateway)


def get_product_media_service(
    storage: Annotated[AvatarStorage | None, Depends(get_avatar_storage)],
) -> ProductMediaService:
    return ProductMediaService(storage)


def get_return_service(
    db: Database,
    policy: Annotated[ReturnPolicy, Depends(get_return_policy)],
) -> ReturnService:
    # Status-only returns do not initialize or depend on the payment gateway.
    # TODO: restore the gateway dependency with the deferred refund workflow.
    return ReturnService(db, policy=policy)
