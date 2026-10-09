from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, check_in

if TYPE_CHECKING:
    from .user import User


NEWS_ARTICLE_STATUSES = ("Draft", "Published", "Hidden")


class NewsArticle(Base):
    __tablename__ = "NewsArticles"
    __table_args__ = (check_in("Status", NEWS_ARTICLE_STATUSES, "Status_Valid"),)

    NewsArticleId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    CreatedByUserId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="RESTRICT"), nullable=False
    )
    Title: Mapped[str] = mapped_column(String(255), nullable=False)
    Slug: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    Summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    Content: Mapped[str] = mapped_column(Text, nullable=False)
    ThumbnailUrl: Mapped[str | None] = mapped_column(String(500), nullable=True)
    Status: Mapped[str] = mapped_column(String(30), nullable=False)
    PublishedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    created_by: Mapped[User] = relationship(back_populates="news_articles", foreign_keys=[CreatedByUserId])


class Banner(Base):
    __tablename__ = "Banners"
    __table_args__ = (
        CheckConstraint('"EndDate" >= "StartDate"', name="EndDate_AfterStartDate"),
    )

    BannerId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    CreatedByUserId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="RESTRICT"), nullable=False
    )
    Title: Mapped[str] = mapped_column(String(255), nullable=False)
    ImageUrl: Mapped[str] = mapped_column(String(500), nullable=False)
    LinkUrl: Mapped[str | None] = mapped_column(String(500), nullable=True)
    DisplayOrder: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    StartDate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    EndDate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    created_by: Mapped[User] = relationship(back_populates="banners", foreign_keys=[CreatedByUserId])
