"""Thành phần dùng chung cho Pydantic schemas.

Quy ước:
- Tên field giữ PascalCase, trùng tên column trong database và thuộc tính SQLAlchemy model.
- Field lồng nhau lấy từ relationship (snake_case trong model) dùng ``relation_field()``.
- Ràng buộc chỉ lấy từ docs/database-schema.md (độ dài varchar, CHECK, nullable).
"""

from decimal import Decimal
from typing import Annotated, Any, ClassVar, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Kiểu dữ liệu dùng chung
# ---------------------------------------------------------------------------

# numeric(15,2) với CHECK >= 0 (mọi cột tiền trong schema đều có CHECK >= 0).
Money = Annotated[Decimal, Field(ge=0, max_digits=15, decimal_places=2)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]

# Chưa dùng EmailStr vì cần package email-validator (chưa có trong requirements.txt).
EmailAddress = Annotated[str, Field(max_length=255)]


def varchar(length: int) -> Any:
    """Chuỗi tương ứng varchar(length)."""
    return Annotated[str, Field(max_length=length)]


# ---------------------------------------------------------------------------
# Giá trị hợp lệ của các cột status (khớp CHECK trong docs/database-schema.md)
# ---------------------------------------------------------------------------

UserRole = Literal["Customer", "Staff", "Admin", "SuperAdmin"]
OrderStatusValue = Literal["Pending", "Confirmed", "Processing", "Shipping", "Delivered", "Completed", "Cancelled"]
PaymentStatusValue = Literal["Pending", "Paid", "Failed", "Refunded", "Cancelled"]
ProductStatus = Literal["Draft", "Active", "Inactive", "Discontinued"]
ProductSerialStatus = Literal["Available", "Reserved", "Sold", "Warranty", "Returned"]
PromotionStatus = Literal["Draft", "Scheduled", "Active", "Expired", "Cancelled"]
DiscountTypeValue = Literal["Percentage", "FixedAmount"]
PurchaseOrderStatus = Literal["Pending", "Approved", "Rejected", "Receiving", "Completed", "Cancelled"]
PaymentTransactionStatus = Literal["Pending", "Success", "Failed", "Cancelled", "Refunded"]
WarrantyEligibilityStatus = Literal["Pending", "Eligible", "Ineligible"]
WarrantyRequestStatus = Literal["New", "Rejected", "HandedOver", "Processing", "Completed", "Cancelled"]
ReturnRequestStatus = Literal["Pending", "Approved", "Rejected", "Receiving", "Processing", "Completed", "Cancelled"]
ConversationStatus = Literal["Open", "Closed"]
NewsArticleStatus = Literal["Draft", "Published", "Hidden"]


# ---------------------------------------------------------------------------
# Base schemas
# ---------------------------------------------------------------------------


class RequestSchema(BaseModel):
    """Schema cho dữ liệu client gửi lên.

    Field optional có 2 nghĩa khác nhau:
    - Bỏ qua field: không thay đổi (PATCH) hoặc dùng default của database (Create).
    - Gửi ``null``: chỉ hợp lệ với field có trong ``NULLABLE_FIELDS`` (cột nullable trong database).

    Service nên dùng ``model_dump(exclude_unset=True)`` để chỉ lấy field client thực sự gửi.
    """

    model_config = ConfigDict(extra="forbid")

    NULLABLE_FIELDS: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_null_for_not_null_columns(self):
        for name in self.model_fields_set:
            if getattr(self, name) is None and name not in self.NULLABLE_FIELDS:
                raise ValueError(f"{name} không được null")
        return self


class ResponseSchema(BaseModel):
    """Schema trả dữ liệu ra API, đọc trực tiếp từ SQLAlchemy model."""

    # validate_by_name: field lồng nhau nhận cả tên PascalCase lẫn tên relationship trong model.
    model_config = ConfigDict(from_attributes=True, validate_by_name=True, validate_by_alias=True)


def relation_field(relationship_name: str) -> Any:
    """Field lồng nhau đọc từ relationship snake_case của SQLAlchemy model.

    Ví dụ ``Items: list[OrderItemResponse] = relation_field("items")`` đọc ``order.items``
    và trả ra JSON với key ``Items``.
    """
    return Field(validation_alias=relationship_name)


def check_end_after_start(start: Any, end: Any) -> None:
    """CHECK EndDate >= StartDate (chỉ kiểm tra khi có đủ 2 giá trị)."""
    if start is not None and end is not None and end < start:
        raise ValueError("EndDate phải lớn hơn hoặc bằng StartDate")


T = TypeVar("T")


class PageResponse(ResponseSchema, Generic[T]):
    """Response danh sách có phân trang."""

    Items: list[T]
    Total: NonNegativeInt
    Page: PositiveInt
    PageSize: PositiveInt
