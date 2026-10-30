"""Public, versioned comparison snapshot stored inside an existing Text message."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import Money


class ComparisonProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ProductId: uuid.UUID
    ProductVariantId: uuid.UUID
    ProductName: str
    VariantName: str
    Brand: str
    Category: str
    Slug: str
    ImageUrl: str | None = None
    Price: Money
    InStock: bool
    Score: float | None = Field(default=None, ge=0, le=1)
    Completeness: float = Field(ge=0, le=1)
    Strengths: list[str] = Field(default_factory=list, max_length=8)
    Limitations: list[str] = Field(default_factory=list, max_length=12)


class ComparisonRow(BaseModel):
    Key: str
    Label: str
    Values: list[str] = Field(min_length=2, max_length=3)


class ComparisonSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    Version: Literal[1] = 1
    Products: list[ComparisonProduct] = Field(min_length=2, max_length=3)
    Rows: list[ComparisonRow] = Field(max_length=24)
    Needs: list[str] = Field(default_factory=list)
    Differences: list[str] = Field(default_factory=list, max_length=12)
    Recommendation: str
    RecommendedProductVariantId: uuid.UUID | None = None
    Caveats: list[str] = Field(default_factory=list)
    AnalysisStatus: Literal["verified", "fallback"] = "verified"
    SnapshotAt: str

    @model_validator(mode="after")
    def consistent_columns(self):
        ids = [p.ProductVariantId for p in self.Products]
        if len(set(ids)) != len(ids) or any(len(row.Values) != len(ids) for row in self.Rows):
            raise ValueError("Các cột so sánh phải là các phiên bản khác nhau và đủ giá trị")
        if self.RecommendedProductVariantId and self.RecommendedProductVariantId not in ids:
            raise ValueError("Đề xuất phải thuộc bảng so sánh")
        return self
