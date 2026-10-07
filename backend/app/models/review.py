from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    FetchedValue,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .catalog import Product
    from .order import OrderItem
    from .user import User


class Review(Base):
    __tablename__ = "Reviews"
    __table_args__ = (CheckConstraint('"Rating" BETWEEN 1 AND 5', name="Rating_Range"),)

    ReviewId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    UserId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="RESTRICT"), nullable=False
    )
    ProductId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Products.ProductId", ondelete="RESTRICT"), nullable=False
    )
    OrderItemId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("OrderItems.OrderItemId", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    Rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    Content: Mapped[str] = mapped_column(Text, nullable=False)
    IsDeleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    DeleteReason: Mapped[str | None] = mapped_column(Text, nullable=True)
    DeletedByUserId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    DeletedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # Database trigger BEFORE UPDATE cập nhật cột này.
    UpdatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        server_onupdate=FetchedValue(),
    )

    user: Mapped[User] = relationship(back_populates="reviews", foreign_keys=[UserId])
    product: Mapped[Product] = relationship(back_populates="reviews", foreign_keys=[ProductId])
    order_item: Mapped[OrderItem] = relationship(back_populates="review", foreign_keys=[OrderItemId])
    deleted_by: Mapped[User | None] = relationship(
        back_populates="deleted_reviews", foreign_keys=[DeletedByUserId]
    )
    images: Mapped[list[ReviewImage]] = relationship(
        back_populates="review",
        foreign_keys="ReviewImage.ReviewId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ReviewImage(Base):
    __tablename__ = "ReviewImages"

    ReviewImageId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ReviewId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Reviews.ReviewId", ondelete="CASCADE"), nullable=False
    )
    ImageUrl: Mapped[str] = mapped_column(String(500), nullable=False)
    DisplayOrder: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    review: Mapped[Review] = relationship(back_populates="images", foreign_keys=[ReviewId])
