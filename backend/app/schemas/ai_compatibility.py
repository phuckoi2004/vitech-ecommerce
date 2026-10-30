"""Additive, versioned metadata contract for the existing AI Text message."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CompatibilityStatus = Literal["compatible", "incompatible", "requires_adapter", "unknown"]


class VideoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    Width: int | None = Field(default=None, ge=1, le=16384)
    Height: int | None = Field(default=None, ge=1, le=16384)
    RefreshHz: float | None = Field(default=None, ge=1, le=1000, allow_inf_nan=False)
    SourceConnector: Literal["hdmi", "displayport", "usb_c", "thunderbolt"] | None = None
    DirectOnly: bool = False

    @model_validator(mode="after")
    def paired_resolution(self):
        if (self.Width is None) != (self.Height is None):
            raise ValueError("Độ phân giải cần đủ chiều rộng và chiều cao")
        return self


class CompatibilityCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    Id: str
    Label: str
    Status: CompatibilityStatus
    Requested: bool = True
    Summary: str
    Evidence: list[str] = Field(default_factory=list, max_length=12)
    Missing: list[str] = Field(default_factory=list, max_length=12)


class CompatibilityDevice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ProductId: uuid.UUID
    ProductVariantId: uuid.UUID | None = None
    ProductName: str
    VariantName: str | None = None
    Kind: Literal["laptop", "monitor", "unsupported"]
    Slug: str
    ImageUrl: str | None = None
    InStock: bool | None = None
    Facts: list[str] = Field(default_factory=list, max_length=24)


class ExplanationOption(BaseModel):
    Id: str
    Text: str


class CompatibilitySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    Version: Literal[1] = 1
    RuleVersion: Literal["laptop-monitor-v1"] = "laptop-monitor-v1"
    CheckType: Literal["laptop_monitor", "laptop_video_output", "unsupported"]
    Products: list[CompatibilityDevice] = Field(min_length=1, max_length=2)
    Request: VideoRequest
    Status: CompatibilityStatus
    Criteria: list[CompatibilityCriterion] = Field(min_length=1, max_length=8)
    Conditions: list[str] = Field(default_factory=list, max_length=12)
    Missing: list[str] = Field(default_factory=list, max_length=24)
    Limitations: list[str] = Field(default_factory=list, max_length=12)
    Explanation: str = Field(max_length=3000)
    ExplanationSource: Literal["backend", "gemini"] = "backend"
    AnalysisStatus: Literal["verified", "fallback"] = "verified"
    # device_type: a port direction the specs do not state was read by device type (compatibility.INFERRED_NOTE).
    Basis: Literal["stated", "device_type"] = "stated"
    # published_max: the requested mode was checked against each port's published maximum (compatibility.PUBLISHED_NOTE).
    ModeBasis: Literal["published_max"] | None = None
    SnapshotAt: str

    @model_validator(mode="after")
    def device_scope(self):
        identities = [(p.ProductId, p.ProductVariantId) for p in self.Products]
        if len(set(identities)) != len(identities):
            raise ValueError("Không lặp lại cùng một thiết bị")
        kinds = [p.Kind for p in self.Products]
        if self.CheckType == "laptop_monitor" and sorted(kinds) != ["laptop", "monitor"]:
            raise ValueError("Cần đúng một laptop và một màn hình")
        if self.CheckType == "laptop_video_output" and kinds != ["laptop"]:
            raise ValueError("Kiểm tra đầu ra cần một laptop")
        if self.CheckType == "unsupported" and self.Status != "unknown":
            raise ValueError("Nhóm chưa hỗ trợ phải trả unknown")
        if len({c.Id for c in self.Criteria}) != len(self.Criteria):
            raise ValueError("Không lặp tiêu chí")
        return self
