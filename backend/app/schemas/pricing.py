"""Public prices and coupon previews; no cost or profit fields are public."""
import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import Field

from .common import Money, RequestSchema, ResponseSchema, varchar


class QuoteItemRequest(RequestSchema):
    ProductVariantId: uuid.UUID
    Quantity: int = Field(ge=1, le=999)


class PricingQuoteRequest(RequestSchema):
    NULLABLE_FIELDS = frozenset({"CouponCode"})
    Items: list[QuoteItemRequest] = Field(min_length=1, max_length=50)
    CouponCode: varchar(50) | None = None


class PricedItem(ResponseSchema):
    ProductVariantId: uuid.UUID
    Quantity: int
    OriginalPrice: Money
    SalePrice: Money
    AutomaticDiscount: Money
    CouponDiscount: Money
    LineTotal: Money
    AppliedPromotionId: uuid.UUID | None


class PricingQuoteResponse(ResponseSchema):
    Items: list[PricedItem]
    OriginalSubtotal: Money
    Subtotal: Money
    AutomaticDiscount: Money
    CouponDiscount: Money
    Total: Money
    CouponId: uuid.UUID | None = None
    CouponCode: str | None = None
    EvaluatedAt: datetime
    # A quote never reserves stock, price or a coupon redemption.
    PreviewOnly: bool = True


class PublicCouponResponse(ResponseSchema):
    CouponId: uuid.UUID
    Code: str
    Name: str
    Description: str | None
    DiscountType: str
    DiscountValue: Money
    MinOrderValue: Money
    MaxDiscountAmount: Money | None
    StartDate: datetime
    EndDate: datetime
    RemainingUses: int | None
    PerCustomerUsageLimit: int = 1
    EvaluatedAt: datetime


class CategoryOfferResponse(ResponseSchema):
    CategoryId: uuid.UUID
    AvailableProductCount: int
    MaxDiscountAmount: Money
    MaxDiscountPercent: Decimal = Field(ge=0, le=100)
