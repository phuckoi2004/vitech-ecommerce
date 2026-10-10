from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, check_in

if TYPE_CHECKING:
    from .chat import Conversation, Message
    from .content import Banner, NewsArticle
    from .order import Order, OrderStatusHistory
    from .promotion import Coupon, Promotion
    from .purchasing import PurchaseOrder
    from .review import Review
    from .service_request import ReturnRequest, ServiceRequestHistory, WarrantyRequest
    from .wishlist_cart import Cart, Wishlist


USER_ROLES = ("Customer", "Staff", "Admin")
ACCOUNT_STATUSES = ("Active", "Locked")
OTP_PURPOSE_REGISTRATION = "Registration"
OTP_PURPOSE_PASSWORD_RESET = "PasswordReset"
OTP_PURPOSES = (OTP_PURPOSE_REGISTRATION, OTP_PURPOSE_PASSWORD_RESET)


class User(Base):
    __tablename__ = "Users"
    __table_args__ = (
        check_in("Role", USER_ROLES, "Role_Valid"),
        check_in("AccountStatus", ACCOUNT_STATUSES, "AccountStatus_Valid"),
        CheckConstraint('"TotalSpent" >= 0', name="TotalSpent_NonNegative"),
        CheckConstraint('"TotalOrders" >= 0', name="TotalOrders_NonNegative"),
    )

    UserId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    Email: Mapped[str] = mapped_column(String(255), nullable=False)
    PhoneNumber: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    PasswordHash: Mapped[str] = mapped_column(String(255), nullable=False)
    FullName: Mapped[str] = mapped_column(String(255), nullable=False)
    Gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    DateOfBirth: Mapped[date | None] = mapped_column(Date, nullable=True)
    AvatarUrl: Mapped[str | None] = mapped_column(String(500), nullable=True)
    Role: Mapped[str] = mapped_column(String(20), nullable=False)
    AccountStatus: Mapped[str] = mapped_column(String(20), nullable=False)
    IsEmailVerified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    OtpCode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    OtpExpiredAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    LockReason: Mapped[str | None] = mapped_column(Text, nullable=True)
    LockedUntil: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    TotalSpent: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default=text("0")
    )
    TotalOrders: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
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
    IsDeleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    addresses: Mapped[list[Address]] = relationship(
        back_populates="user",
        foreign_keys="Address.UserId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="user",
        foreign_keys="Notification.UserId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    wishlist: Mapped[Wishlist | None] = relationship(
        back_populates="user",
        foreign_keys="Wishlist.UserId",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    cart: Mapped[Cart | None] = relationship(
        back_populates="user",
        foreign_keys="Cart.UserId",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    customer_orders: Mapped[list[Order]] = relationship(
        back_populates="customer", foreign_keys="Order.CustomerId", passive_deletes="all"
    )
    assigned_orders: Mapped[list[Order]] = relationship(
        back_populates="assigned_staff", foreign_keys="Order.AssignedStaffId", passive_deletes=True
    )
    order_status_changes: Mapped[list[OrderStatusHistory]] = relationship(
        back_populates="changed_by",
        foreign_keys="OrderStatusHistory.ChangedByUserId",
        passive_deletes=True,
    )
    created_promotions: Mapped[list[Promotion]] = relationship(
        back_populates="created_by", foreign_keys="Promotion.CreatedByUserId", passive_deletes="all"
    )
    created_coupons: Mapped[list[Coupon]] = relationship(
        back_populates="created_by", foreign_keys="Coupon.CreatedByUserId", passive_deletes="all"
    )
    created_purchase_orders: Mapped[list[PurchaseOrder]] = relationship(
        back_populates="created_by",
        foreign_keys="PurchaseOrder.CreatedByUserId",
        passive_deletes="all",
    )
    decided_purchase_orders: Mapped[list[PurchaseOrder]] = relationship(
        back_populates="decided_by",
        foreign_keys="PurchaseOrder.DecidedByUserId",
        passive_deletes=True,
    )
    reviews: Mapped[list[Review]] = relationship(
        back_populates="user", foreign_keys="Review.UserId", passive_deletes="all"
    )
    deleted_reviews: Mapped[list[Review]] = relationship(
        back_populates="deleted_by", foreign_keys="Review.DeletedByUserId", passive_deletes=True
    )
    customer_conversations: Mapped[list[Conversation]] = relationship(
        back_populates="customer", foreign_keys="Conversation.CustomerId", passive_deletes="all"
    )
    assigned_conversations: Mapped[list[Conversation]] = relationship(
        back_populates="assigned_staff",
        foreign_keys="Conversation.AssignedStaffId",
        passive_deletes=True,
    )
    sent_messages: Mapped[list[Message]] = relationship(
        back_populates="sender", foreign_keys="Message.SenderUserId", passive_deletes=True
    )
    warranty_requests: Mapped[list[WarrantyRequest]] = relationship(
        back_populates="customer", foreign_keys="WarrantyRequest.CustomerId", passive_deletes="all"
    )
    assigned_warranty_requests: Mapped[list[WarrantyRequest]] = relationship(
        back_populates="assigned_staff",
        foreign_keys="WarrantyRequest.AssignedStaffId",
        passive_deletes=True,
    )
    return_requests: Mapped[list[ReturnRequest]] = relationship(
        back_populates="customer", foreign_keys="ReturnRequest.CustomerId", passive_deletes="all"
    )
    assigned_return_requests: Mapped[list[ReturnRequest]] = relationship(
        back_populates="assigned_staff",
        foreign_keys="ReturnRequest.AssignedStaffId",
        passive_deletes=True,
    )
    service_request_changes: Mapped[list[ServiceRequestHistory]] = relationship(
        back_populates="changed_by",
        foreign_keys="ServiceRequestHistory.ChangedByUserId",
        passive_deletes=True,
    )
    news_articles: Mapped[list[NewsArticle]] = relationship(
        back_populates="created_by", foreign_keys="NewsArticle.CreatedByUserId", passive_deletes="all"
    )
    banners: Mapped[list[Banner]] = relationship(
        back_populates="created_by", foreign_keys="Banner.CreatedByUserId", passive_deletes="all"
    )


# Email unique không phân biệt hoa thường.
Index("UX_Users_Email_Lower", func.lower(User.Email), unique=True)


class Address(Base):
    __tablename__ = "Addresses"

    AddressId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    UserId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="CASCADE"), nullable=False
    )
    ReceiverName: Mapped[str] = mapped_column(String(255), nullable=False)
    ReceiverPhone: Mapped[str] = mapped_column(String(20), nullable=False)
    Province: Mapped[str] = mapped_column(String(100), nullable=False)
    Ward: Mapped[str] = mapped_column(String(100), nullable=False)
    DetailAddress: Mapped[str] = mapped_column(String(255), nullable=False)
    IsDefault: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    IsDeleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    user: Mapped[User] = relationship(back_populates="addresses", foreign_keys=[UserId])
    orders: Mapped[list[Order]] = relationship(
        back_populates="address", foreign_keys="Order.AddressId", passive_deletes=True
    )


class Notification(Base):
    __tablename__ = "Notifications"

    NotificationId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    UserId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="CASCADE"), nullable=False
    )
    Title: Mapped[str] = mapped_column(String(255), nullable=False)
    Content: Mapped[str] = mapped_column(Text, nullable=False)
    NotificationType: Mapped[str] = mapped_column(String(50), nullable=False)
    ActionUrl: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ReferenceType: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Tham chiếu đa hình, không có FK.
    ReferenceId: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    IsRead: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    ReadAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    user: Mapped[User] = relationship(back_populates="notifications", foreign_keys=[UserId])


class OtpChallenge(Base):
    """Một lần gửi OTP theo tài khoản + mục đích (thêm bởi migration a7c3e9d1f285, chưa áp dụng).

    Chỉ lưu bản băm OTP (CodeHash, qua PasswordHasher). Xác minh luôn dùng lần gửi mới nhất của (UserId, Purpose).
    FailedAttempts mang sang lần gửi lại (gửi lại không xóa số lần sai); LockedUntil: khóa xác minh (và chặn gửi
    mới) cho tài khoản + mục đích. Số lần gửi trong một giờ đếm từ các dòng này. Users.OtpCode/OtpExpiredAt không
    còn được dùng.
    """

    __tablename__ = "OtpChallenges"
    __table_args__ = (
        check_in("Purpose", OTP_PURPOSES, "Purpose_Valid"),
        CheckConstraint('"FailedAttempts" >= 0', name="FailedAttempts_NonNegative"),
    )

    OtpChallengeId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    UserId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="CASCADE"), nullable=False
    )
    Purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    CodeHash: Mapped[str] = mapped_column(String(255), nullable=False)
    ExpiresAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    FailedAttempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    LockedUntil: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ConsumedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


Index("IX_OtpChallenges_UserId_Purpose_CreatedAt", OtpChallenge.UserId, OtpChallenge.Purpose, OtpChallenge.CreatedAt)
