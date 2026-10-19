"""Shared server-time lifecycle; IsActive is availability, not a manual pause."""

from datetime import datetime, timezone


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def promotion_status(promotion, now: datetime) -> str:
    if promotion.Status not in {"Scheduled", "Active"}:
        return promotion.Status
    now = aware(now)
    if now > aware(promotion.EndDate):
        return "Expired"
    return "Scheduled" if now < aware(promotion.StartDate) else "Active"


def coupon_status(coupon, now: datetime) -> str:
    promotion = coupon.promotion
    now = aware(now)
    if promotion.Status in {"Expired", "Cancelled"} or now > aware(promotion.EndDate):
        return "Ended"
    if coupon.UsageLimit is not None and coupon.UsedCount >= coupon.UsageLimit:
        return "Exhausted"
    if promotion_status(promotion, now) == "Active" and now >= aware(promotion.StartDate):
        return "Active"
    return "Upcoming"
