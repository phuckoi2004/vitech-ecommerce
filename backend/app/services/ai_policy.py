"""Store policies the AI chat may state: warranty, exchange/return and how promotions apply.

The rules are the ones the services enforce and the customer pages show (warranty_period.py and "Chính sách bảo hành";
returns.py/exchange.py and the exchange request page). They are written once here so Gemini and the backend's own
fallback answer quote the same text; the return window comes from configuration (RETURN_WINDOW_DAYS), never the model.
"""

import re

from .returns import ReturnPolicy

# On folded text. "đời máy"/"đời mới" fold like "đổi máy"/"đổi mới", so those are not policy words.
WARRANTY_TERMS = re.compile(r"\bbao hanh\b")
RETURN_TERMS = re.compile(r"\b(?:doi tra|doi hang|tra hang|tra lai (?:hang|tien|may|san pham)|hoan tien|hoan tra"
                          r"|doi san pham|(?:muon|can|duoc|xin|co the) doi (?:may|moi)"
                          r"|doi (?:may|moi) (?:duoc|khong)|(?:duoc|muon|can) tra(?: lai)?(?: khong)?)\b")
POLICY_TERMS = re.compile(rf"{WARRANTY_TERMS.pattern}|{RETURN_TERMS.pattern}|\bchinh sach\b")

WARRANTY_LINES = (
    "Thời hạn bảo hành tùy từng sản phẩm và được ghi trên trang sản phẩm; sản phẩm ghi 0 tháng không có bảo hành.",
    "Bảo hành tính từ ngày giao hàng thành công đến hết số tháng bảo hành của sản phẩm.",
    "Gửi yêu cầu bảo hành trong tài khoản: chọn sản phẩm thuộc đơn đã giao, mô tả lỗi, đính kèm ảnh/video và "
    "Serial/IMEI nếu có.",
    "VieTech tiếp nhận, kiểm tra điều kiện bảo hành rồi chuyển trung tâm bảo hành; kết quả (sửa chữa, thay linh kiện, "
    "đổi máy hoặc không thể bảo hành) được thông báo cho bạn.",
)
RETURN_LINES = (
    "Mỗi yêu cầu đổi mới 1 sản phẩm: còn hàng thì đổi đúng phiên bản đã mua; nếu hết hàng, bạn có thể chọn sản phẩm "
    "khác cùng danh mục.",
    "Nếu chọn sản phẩm giá cao hơn, bạn thanh toán thêm phần chênh lệch; phần chênh lệch còn dư không được hoàn lại. "
    "Đơn đổi được miễn phí giao hàng tiêu chuẩn.",
    "VieTech đối chiếu chính sách, Serial/IMEI và tình trạng thực tế của sản phẩm rồi thông báo kết quả.",
)
PROMOTION_LINE = ("Giá trên trang sản phẩm và thẻ gợi ý đã gồm giảm giá tự động; mã giảm giá được kiểm tra điều kiện "
                  "khi áp dụng ở giỏ hàng.")
PROMOTION_USAGE_LINES = (
    "Mở giỏ hàng và chọn các sản phẩm muốn mua.",
    "Nhập mã vào ô mã giảm giá rồi chọn áp dụng.",
    "Kiểm tra số tiền giảm và tổng thanh toán; mã chỉ áp dụng khi giỏ hàng đáp ứng điều kiện sản phẩm, "
    "giá trị tối thiểu, thời hạn và lượt sử dụng.",
)
TITLES = {"Warranty": "Bảo hành", "Returns": "Đổi trả", "Promotion": "Khuyến mãi"}


def policy_topics(text, *, promo):
    """Topics a folded question asks about; "chính sách" alone means the after-sales policies."""
    warranty, returns = bool(WARRANTY_TERMS.search(text)), bool(RETURN_TERMS.search(text))
    if not (warranty or returns or promo) and "chinh sach" in text:
        warranty = returns = True
    return tuple(topic for topic, asked in (("promotion", promo), ("warranty", warranty), ("returns", returns)) if asked)


def return_window_days():
    try:
        return ReturnPolicy.from_env().window_days
    except ValueError:
        return None  # Misconfigured: the request page states the deadline; the chat does not guess one.


def requested_coupon(text):
    """A code explicitly named by the customer, not words such as 'mã giảm giá nào'."""
    match = re.search(r"\b(?:ma(?: giam gia| uu dai| khuyen mai)?|code|coupon|voucher)\s+([a-z0-9_-]{4,50})\b", text)
    if match and match[1] not in {"giam", "khuyen", "hang", "hien", "duoc", "trong", "dung", "khong", "giup"}:
        return match[1]
    return None


def promotion_usage(text):
    return bool(re.search(r"\b(?:cach (?:dung|su dung|ap dung|nhap)|huong dan (?:dung|su dung|ap dung|nhap)"
                          r"|(?:nhap|ap dung|su dung) ma.*(?:o dau|the nao|nhu nao)"
                          r"|ma.*(?:nhap o dau|dung the nao|su dung the nao))\b", text))


def return_message_issue(text):
    """The active workflow accepts exchanges; Gemini cannot promise a new refund."""
    from app.core.search_text import fold

    for sentence in re.split(r"[.!?\n]", fold(text or "")):
        if "hoan tien" in sentence and not re.search(r"\b(?:khong|chua)\b.*\bhoan tien\b", sentence):
            return "cam kết hoàn tiền ngoài quy trình đổi sản phẩm hiện hành"
    return None


def return_lines(question=""):
    from app.core.search_text import fold

    text = fold(question)
    days = return_window_days()
    window = (f"Gửi yêu cầu đổi trả trong {days} ngày kể từ ngày giao hàng (ngày giao là ngày thứ nhất)"
              if days else "Gửi yêu cầu đổi trả trong thời hạn ghi ở trang tạo yêu cầu")
    window += ", cho sản phẩm thuộc đơn đã giao."
    mode = "VieTech hiện tiếp nhận yêu cầu đổi sản phẩm, mỗi phiếu đổi 1 sản phẩm; chưa hỗ trợ yêu cầu trả hàng hoàn tiền mới."
    steps = ("Vào Tài khoản → Bảo hành và đổi trả → Tạo yêu cầu đổi trả; chọn sản phẩm trong đơn đã giao, "
             "chọn Serial/IMEI nếu có, mô tả lý do và đính kèm ảnh minh chứng nếu cần rồi gửi yêu cầu.")
    check = "VieTech kiểm tra thời hạn, Serial/IMEI và tình trạng thực tế trước khi xác nhận; chat chưa thể kết luận sản phẩm của bạn đủ điều kiện."
    if re.search(r"\b(?:trang thai|tien do|den dau|xong chua|duyet chua|da gui|da tao)\b", text):
        return ("Xem tiến trình phiếu trong Tài khoản → Bảo hành và đổi trả → chọn yêu cầu đã gửi.",
                "Chat AI chưa tra cứu trạng thái phiếu cụ thể; nếu cần kiểm tra thêm, bạn liên hệ nhân viên VieTech.")
    if re.search(r"\b(?:hoan tien|hoan tra|tra hang|tra lai|duoc tra)\b", text):
        return (mode, "Nếu bạn đang có phiếu trả hàng cũ, xem kết quả trong tài khoản hoặc liên hệ nhân viên để kiểm tra.")
    if re.search(r"\b(?:bao lau|bao nhieu ngay|may ngay|thoi han|han doi)\b", text):
        return (window, check)
    if re.search(r"\b(?:phi|chenh lech|bu them|gia cao hon|gia thap hon)\b", text):
        return (RETURN_LINES[1],)
    if re.search(r"\b(?:cach|thu tuc|cac buoc|gui|tao|o dau|lam sao)\b", text):
        return (steps, window, mode, check)
    return (window, mode, *RETURN_LINES[:2], steps, check)


def policy_text(policy):
    """The backend's answer: one block per topic, in the order asked."""
    blocks = []
    for key, lines in policy.items():
        body = []
        for line in lines:
            if line.startswith("**") and "\n" in line:
                body.append("\n" + line + "\n")
            else:
                body.append("- " + line)
        blocks.append(f"{TITLES[key]}:\n" + "\n".join(body))
    return "\n\n".join(blocks)
