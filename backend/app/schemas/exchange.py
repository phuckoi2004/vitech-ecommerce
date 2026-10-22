import uuid
from pydantic import model_validator
from .common import RequestSchema, varchar


class ExchangeOrderCreate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"ProductVariantId", "AddressId"})
    ProductVariantId: uuid.UUID | None = None
    AddressId: uuid.UUID | None = None
    ReceiverName: varchar(255) | None = None
    ReceiverPhone: varchar(20) | None = None
    ShippingAddress: varchar(500) | None = None

    @model_validator(mode="after")
    def receiver(self):
        supplied = [self.ReceiverName, self.ReceiverPhone, self.ShippingAddress]
        if any(supplied) and not all(supplied):
            raise ValueError("Cần nhập đủ tên, điện thoại và địa chỉ nhận hàng")
        return self
