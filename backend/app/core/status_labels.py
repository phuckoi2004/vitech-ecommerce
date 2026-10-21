"""Vietnamese labels for messages; persisted/API status codes stay unchanged."""

import re

ORDER_STATUS_LABELS = {
    "Pending": "Chờ xác nhận", "Confirmed": "Đã xác nhận", "Processing": "Đang xử lý",
    "Shipping": "Đang giao", "Delivered": "Đã giao", "Completed": "Hoàn tất", "Cancelled": "Đã hủy",
}
PAYMENT_STATUS_LABELS = {
    "Pending": "Chưa thanh toán", "Paid": "Đã thanh toán", "Failed": "Thanh toán thất bại",
    "Refunded": "Đã hoàn tiền", "Cancelled": "Đã hủy thanh toán",
}
TRANSACTION_STATUS_LABELS = {
    "Pending": "Chờ xử lý", "Success": "Thành công", "Failed": "Thất bại",
    "Cancelled": "Đã hủy", "Refunded": "Đã hoàn tiền",
}
PURCHASE_STATUS_LABELS = {
    "Pending": "Chờ xác nhận", "Approved": "Đã xác nhận", "Rejected": "Từ chối",
    "Receiving": "Đang nhận hàng", "Completed": "Đã nhận đủ", "Cancelled": "Đã hủy", "Closed": "Đóng phiếu thiếu",
}
RETURN_STATUS_LABELS = {
    "Pending": "Đang chờ", "Approved": "Đã tiếp nhận", "Receiving": "Đang điều phối",
    "Processing": "Đang đánh giá hư hại", "Completed": "Đã trả máy", "Rejected": "Từ chối", "Cancelled": "Đã hủy",
}
WARRANTY_STATUS_LABELS = {
    "New": "Mới", "HandedOver": "Đã bàn giao trung tâm bảo hành", "Processing": "Đang xử lý",
    "Completed": "Đã trả khách", "Rejected": "Từ chối", "Cancelled": "Đã hủy",
}


def status_label(value: str | None, labels: dict[str, str]) -> str:
    return labels.get(value, "Chưa xác định") if value else "—"


_LEGACY_ORDER_NOTIFICATION = re.compile(
    r"(Đơn hàng .+ chuyển sang trạng thái )(" + "|".join(ORDER_STATUS_LABELS) + r")(\.)"
)


def notification_content(content: str, notification_type: str, reference_type: str | None) -> str:
    """Translate the known system template on read, without rewriting stored notices or free text."""
    if notification_type == "Order" and reference_type == "Order":
        match = _LEGACY_ORDER_NOTIFICATION.fullmatch(content)
        if match:
            return match[1] + ORDER_STATUS_LABELS[match[2]] + match[3]
    return content
