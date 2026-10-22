"""Customer contract for a managed AI turn, separate from staff MessageCreate."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .chat import MessageResponse
from .common import RequestSchema, ResponseSchema


class AiMessageCreate(RequestSchema):
    ClientRequestId: uuid.UUID
    MessageType: Literal["Text"] = "Text"
    Content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class AiMessageCancel(RequestSchema):
    # Keep the question even if cancellation reaches the server before the original POST.
    Content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class AiTurnResponse(ResponseSchema):
    ClientRequestId: uuid.UUID
    Status: Literal["Pending", "Completed", "Failed", "Cancelled"]
    CustomerMessage: MessageResponse
    AiMessages: list[MessageResponse]


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchProductsArguments(ToolArguments):
    keyword: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    brand: str | None = Field(default=None, max_length=100)
    min_price: int | None = Field(default=None, ge=0, le=10**12, strict=True)
    max_price: int | None = Field(default=None, ge=1, le=10**12, strict=True)
    sort: Literal["price_asc", "price_desc", "newest", "relevance"] = "price_asc"

    @model_validator(mode="after")
    def price_order(self):
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price phải nhỏ hơn hoặc bằng max_price")
        return self


class GetProductArguments(ToolArguments):
    product_id: uuid.UUID | None = None
    # Stage 10.7: a comparison reads its products in one round instead of one round each.
    product_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=5)
    slug: str | None = Field(default=None, min_length=1, max_length=300)
    rank: int | None = Field(default=None, ge=1, le=5, strict=True)

    @model_validator(mode="after")
    def one_selector(self):
        if sum(value is not None for value in (self.product_id, self.product_ids, self.slug, self.rank)) != 1:
            raise ValueError("Chọn một trong product_id, product_ids, slug hoặc rank")
        if self.product_ids and len(set(self.product_ids)) != len(self.product_ids):
            raise ValueError("Không lặp sản phẩm")
        return self


class ListOffersArguments(ToolArguments):
    product_id: uuid.UUID | None = None


class ProductSelection(ToolArguments):
    product_id: uuid.UUID
    product_variant_id: uuid.UUID | None = None
    specification_keys: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]] = Field(
        default_factory=list, max_length=4)


class PresentAnswerArguments(ToolArguments):
    # explain/policy answers are built by the backend from its own data; any products the model lists are ignored.
    intent: Literal["recommend", "product", "compare", "offers", "no_results", "clarify", "handoff", "chat", "explain",
                    "policy"]
    products: list[ProductSelection] = Field(default_factory=list, max_length=5)
    clarification: Literal["category", "budget", "usage", "brand", "products"] = "category"
    # Natural-language answer written by the model. The backend shows it only when every fact in it is grounded
    # in this turn's data (services/ai_grounding.py); otherwise its own text is used.
    message: str | None = Field(default=None, max_length=1500)

    @model_validator(mode="after")
    def selection_rules(self):
        ids = [p.product_id for p in self.products]
        if len(ids) != len(set(ids)):
            raise ValueError("Không lặp sản phẩm")
        if self.intent in ("recommend", "product") and not ids:
            raise ValueError("Cần chọn sản phẩm đã tra cứu")
        if self.intent == "compare" and len(ids) < 2:
            raise ValueError("So sánh cần ít nhất hai sản phẩm")
        if self.intent in ("clarify", "handoff", "no_results", "offers", "chat") and ids:
            raise ValueError("Ý định này không kèm lựa chọn sản phẩm")
        return self
