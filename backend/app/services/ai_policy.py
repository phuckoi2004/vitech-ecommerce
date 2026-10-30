"""Store policies the AI chat may state: warranty, exchange/return and how promotions apply.

The rules are the ones the services enforce and the customer pages show (warranty_period.py and "Chính sách bảo hành";
returns.py/exchange.py and the exchange request page). Public wording in after_sales_policy.py is shared by Gemini,
the storefront and the fallback answer; the return window comes from configuration (RETURN_WINDOW_DAYS), never the model.
"""

import re

from .returns import ReturnPolicy
from .after_sales_policy import (
    RETURN_CHECK_LINE, RETURN_LINES, RETURN_MODE_LINE, RETURN_STEPS_LINE, WARRANTY_LINES,
    WARRANTY_REVIEW_LINE, WARRANTY_TIMING_LINE, return_window_line,
)

# On folded text. "đời máy"/"đời mới" fold like "đổi máy"/"đổi mới", so those are not policy words.
WARRANTY_TERMS = re.compile(r"\bbao hanh\b")
RETURN_TERMS = re.compile(r"\b(?:doi tra|doi hang|tra hang|tra lai (?:hang|tien|may|san pham)|hoan tien|hoan tra"
                          r"|doi san pham|(?:muon|can|duoc|xin|co the) doi (?:may|moi)"
                          r"|doi (?:may|moi) (?:duoc|khong)|(?:duoc|muon|can) tra(?: lai)?(?: khong)?)\b")
POLICY_TERMS = re.compile(rf"{WARRANTY_TERMS.pattern}|{RETURN_TERMS.pattern}|\bchinh sach\b")

PROMOTION_LINE = ("Giá trên trang sản phẩm và thẻ gợi ý đã gồm giảm giá tự động, mã giảm giá được kiểm tra điều kiện "
                  "khi áp dụng ở giỏ hàng.")
PROMOTION_USAGE_LINES = (
    "Mở giỏ hàng và chọn các sản phẩm muốn mua.",
    "Nhập mã vào ô mã giảm giá rồi chọn áp dụng.",
    "Kiểm tra số tiền giảm và tổng thanh toán, mã chỉ áp dụng khi giỏ hàng đáp ứng điều kiện sản phẩm, "
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


def warranty_lines(question="", *, has_products=False):
    from app.core.search_text import fold

    text = fold(question)
    if re.search(r"\b(?:phi|mien phi|van chuyen|gui may|nhan may|bao lau.*xong|bao nhieu ngay"
                 r"|thoi gian (?:xu ly|sua)|xu ly.*bao lau|sua.*bao lau)\b", text):
        return (WARRANTY_TIMING_LINE, "Liên hệ nhân viên VieTech trước khi gửi máy để được hướng dẫn.")
    if re.search(r"\b(?:roi|vo|vao nuoc|tu y|can thiep|tu choi|loai tru|dieu kien|pham vi)\b", text):
        return (WARRANTY_REVIEW_LINE, WARRANTY_LINES[2], WARRANTY_TIMING_LINE)
    if not has_products and re.search(r"\b(?:bao lau|bao nhieu (?:thang|nam)|may (?:thang|nam)|thoi han)\b", text):
        return (*WARRANTY_LINES[:2], "Bạn cho mình tên hoặc mã mẫu sản phẩm để kiểm tra đúng thời hạn bảo hành nhé?")
    return (*WARRANTY_LINES, WARRANTY_REVIEW_LINE, WARRANTY_TIMING_LINE)


def warranty_message_issue(message):
    """Decline provider promises for paused replacements, blanket acceptance, fixed turnaround or free service."""
    from app.core.search_text import fold

    for sentence in re.split(r"[.!?\n]", fold(message or "")):
        if re.search(r"\b(?:doi may|doi moi|thay may|1 doi 1|mot doi mot)\b", sentence):
            if not re.search(r"\b(?:khong|chua)\s+(?:(?:ho tro|ap dung|the|duoc phep)\s+)?(?:doi|thay|1 doi 1|mot doi mot)", sentence):
                return "cam kết đổi máy ngoài quy trình bảo hành hiện hành"
        if re.search(r"\b(?:mien phi|khong (?:mat|ton) phi|khong tinh phi)\b", sentence):
            return "cam kết miễn phí bảo hành khi chưa xác nhận điều kiện"
        if re.search(r"\b(?:xu ly|sua|hoan tat|hoan thanh|tra may|nhan lai|bao hanh)\b.*\b(?:\d+|mot|hai|ba)\s*(?:ngay|gio)\b", sentence):
            return "cam kết thời gian xử lý bảo hành chưa được xác nhận"
        if re.search(r"\b(?:bao hanh moi loi|moi loi.*(?:duoc|deu) bao hanh|bao hanh vo dieu kien)\b", sentence):
            return "cam kết phạm vi bảo hành chưa được xác nhận"
    return None


def return_lines(question=""):
    from app.core.search_text import fold

    text = fold(question)
    days = return_window_days()
    window = return_window_line(days)
    mode, steps, check = RETURN_MODE_LINE, RETURN_STEPS_LINE, RETURN_CHECK_LINE
    if re.search(r"\b(?:trang thai|tien do|den dau|xong chua|duyet chua|da gui|da tao)\b", text):
        return ("Xem tiến trình phiếu trong Tài khoản → Bảo hành và đổi trả → chọn yêu cầu đã gửi.",
                "Chat AI chưa tra cứu trạng thái phiếu cụ thể, nếu cần kiểm tra thêm, bạn liên hệ nhân viên VieTech.")
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
