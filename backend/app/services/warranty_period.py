"""Thời hạn bảo hành: quy tắc tính ngày dùng chung cho toàn Service Layer (hàm thuần, không truy cập database).

Quy tắc đã chốt (đợt 5.1.1):
1. Số tháng bảo hành lấy từ OrderItems.WarrantyMonths (chụp lại lúc mua), không lấy Products.WarrantyMonths hiện tại.
2. Máy ban đầu: ngày bắt đầu = ngày lịch Việt Nam (Asia/Ho_Chi_Minh) của thời điểm giao hàng thành công (UTC).
3. Ngày hết hạn = ngày bắt đầu + số tháng − 1 ngày.
4. Nếu ngày cộng tháng vượt ngày cuối tháng đích: lấy ngày cuối tháng đích TRƯỚC khi trừ một ngày
   (ví dụ 31/01/2027 + 1 tháng → 28/02/2027 → hết hạn 27/02/2027).
5. WarrantyMonths = 0: không có bảo hành (không có ngày bắt đầu/kết thúc).
6. Máy thay thế: thời hạn MỚI bắt đầu từ ngày Staff xác nhận bàn giao máy thay thế cho khách; không tự đặt thời
   điểm bàn giao khi hệ thống chưa ghi nhận.
7. Không ghi đè ngày bảo hành của serial cũ bằng ngày của máy thay thế.
Còn bảo hành vào một ngày (theo lịch Việt Nam) khi ngày bắt đầu <= ngày đó <= ngày hết hạn (tính cả ngày hết hạn).
"""

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .exceptions import BusinessRuleError

# Thời điểm lưu/xử lý bằng UTC; ngày lịch bảo hành theo giờ Việt Nam.
VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


@dataclass(frozen=True)
class WarrantyPeriod:
    start: date
    end: date

    def covers(self, day: date) -> bool:
        """Còn bảo hành vào ngày ``day`` (lịch Việt Nam), tính cả ngày bắt đầu và ngày hết hạn."""
        return self.start <= day <= self.end


def vietnam_date(moment: datetime) -> date:
    """Ngày lịch tại Việt Nam của một thời điểm có múi giờ (timestamptz/UTC)."""
    if moment.tzinfo is None:
        raise ValueError("Thời điểm phải có múi giờ (timestamptz/UTC)")
    return moment.astimezone(VIETNAM_TZ).date()


def validate_warranty_months(months: Any) -> int:
    """Số tháng bảo hành hợp lệ: số nguyên >= 0 (0 = không bảo hành). Không chấp nhận bool, số thực, chuỗi, None."""
    if isinstance(months, bool) or not isinstance(months, int) or months < 0:
        raise BusinessRuleError(
            "Số tháng bảo hành phải là số nguyên không âm", code="invalid_warranty_months"
        )
    return months


def add_months_clamped(start: date, months: int) -> date:
    """Cộng ``months`` tháng; ngày không tồn tại trong tháng đích được thay bằng ngày cuối tháng đích."""
    months = validate_warranty_months(months)
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    if year > date.max.year:
        raise BusinessRuleError("Thời hạn bảo hành vượt giới hạn ngày", code="invalid_warranty_months")
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def compute_warranty_period(start: date, months: Any) -> WarrantyPeriod | None:
    """Thời hạn bảo hành bắt đầu từ ngày ``start``; None nếu không có bảo hành (0 tháng)."""
    if not isinstance(start, date) or isinstance(start, datetime):
        raise BusinessRuleError("Ngày bắt đầu bảo hành không hợp lệ", code="invalid_warranty_start")
    months = validate_warranty_months(months)
    if months == 0:
        return None
    return WarrantyPeriod(start=start, end=add_months_clamped(start, months) - timedelta(days=1))


def delivery_warranty_period(delivered_at: datetime | None, months: Any) -> WarrantyPeriod | None:
    """Máy ban đầu: bảo hành từ ngày Việt Nam ghi nhận giao hàng thành công (Orders.DeliveredAt)."""
    if delivered_at is None:
        raise BusinessRuleError("Chưa ghi nhận thời điểm giao hàng thành công", code="delivery_not_recorded")
    return compute_warranty_period(vietnam_date(delivered_at), months)


def replacement_warranty_period(handed_over_at: datetime | None, months: Any) -> WarrantyPeriod | None:
    """Máy thay thế: thời hạn MỚI từ ngày Việt Nam Staff xác nhận bàn giao máy thay thế cho khách.

    Không có thời điểm bàn giao đã ghi nhận thì từ chối (không tự lấy thời điểm hiện tại hay ngày giao ban đầu).
    """
    if handed_over_at is None:
        raise BusinessRuleError(
            "Chưa ghi nhận thời điểm bàn giao máy thay thế cho khách", code="replacement_handover_not_recorded"
        )
    return compute_warranty_period(vietnam_date(handed_over_at), months)


def stored_warranty_period(start: date | None, end: date | None) -> WarrantyPeriod | None:
    """Thời hạn đã lưu trên ProductSerials; cả hai NULL = không có bảo hành. Dữ liệu lệch thì báo lỗi."""
    if start is None and end is None:
        return None
    if start is None or end is None or end < start:
        raise BusinessRuleError("Dữ liệu thời hạn bảo hành không nhất quán", code="invalid_stored_warranty")
    return WarrantyPeriod(start=start, end=end)


def is_under_warranty(period: WarrantyPeriod | None, at: datetime) -> bool:
    """Còn bảo hành tại thời điểm ``at`` (so theo ngày lịch Việt Nam); không có thời hạn → hết/không bảo hành."""
    return period is not None and period.covers(vietnam_date(at))


def apply_replacement_warranty(original_serial: Any, replacement_serial: Any, *, months: Any,
                               handed_over_at: datetime | None) -> WarrantyPeriod | None:
    """Gán thời hạn MỚI cho serial máy thay thế; KHÔNG đổi ngày bảo hành của serial cũ (giữ lịch sử).

    ``months``: OrderItems.WarrantyMonths của dòng đơn gốc. ``handed_over_at``: thời điểm Staff xác nhận bàn giao máy
    thay thế (đã ghi nhận). Chỉ xử lý ngày bảo hành: trạng thái serial, tồn kho và liên kết với yêu cầu bảo hành thuộc
    WarrantyService (cần bổ sung cột liên kết máy thay thế ở WarrantyRequests).
    """
    if replacement_serial is original_serial or replacement_serial.ProductSerialId == original_serial.ProductSerialId:
        raise BusinessRuleError("Máy thay thế phải là serial khác serial cũ", code="replacement_same_serial")
    period = replacement_warranty_period(handed_over_at, months)
    replacement_serial.WarrantyStartDate = period.start if period else None
    replacement_serial.WarrantyEndDate = period.end if period else None
    return period
