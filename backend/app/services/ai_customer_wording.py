"""Customer prose only: keep identifiers, verdicts, quantities and technical conditions intact."""

import re


_REPLACEMENTS = (
    (r",?[ \t]*tối đa[ \t]+\d+[ \t]+lượt[ \t]*/[ \t]*khách\b", ""),
    (r"Mình đã đối chiếu các phiên bản sau bằng dữ liệu hiện tại của VieTech:", "So sánh các mẫu sau:"),
    (r"Chưa (?:thể chọn|đủ căn cứ để chọn|thể kết luận để chọn) một mẫu phù hợp hơn(?: với nhu cầu của bạn)?\."
     r"(?: Bạn cho mình biết nhu cầu ưu tiên nhé\.)?", ""),
    (r"Các mẫu có mức phù hợp gần nhau theo dữ liệu hiện có[;,] chưa đủ căn cứ chọn một mẫu vượt trội\.",
     "Các mẫu có mức phù hợp gần nhau, chưa thể chọn một mẫu vượt trội."),
    (r"phù hợp hơn theo tiêu chí của VieTech nhờ", "phù hợp hơn với nhu cầu của bạn nhờ"),
    (r"chưa đủ dữ liệu để xác nhận", "chưa thể xác nhận"),
    (r"chưa đủ dữ liệu", "chưa rõ"),
    (r"chưa có dữ liệu", "chưa rõ"),
    (r"chỉ truyền dữ liệu|data only", "chỉ truyền tệp"),
    (r"truyền dữ liệu", "truyền tệp"),
    (r"dữ liệu đầu ra và đầu vào", "giới hạn đầu ra và đầu vào"),
    (r"dữ liệu", "thông số"),
    (r"có căn cứ xác nhận(?: trong điều kiện đã nêu)?", "đáp ứng trong điều kiện đã nêu"),
    (r"có căn cứ về kết nối", "có thể kết nối"),
    (r"đã có căn cứ ở", "được hỗ trợ ở"),
    (r"có căn cứ qua", "qua"),
    (r"chưa đủ căn cứ", "chưa thể kết luận"),
    (r"đã xác minh", ""),
    (r"được xác minh", "phù hợp"),
    (r"xác minh", "kiểm tra"),
    (r"được đối chiếu với", "nằm trong"),
    (r"đối chiếu", "kiểm tra"),
)
_PATTERNS = [(re.compile(pattern, re.I), replacement) for pattern, replacement in _REPLACEMENTS]
_PROSE_FIELDS = frozenset({"Label", "Values", "Strengths", "Limitations", "Recommendation", "Differences",
                           "Caveats", "Needs", "Summary", "Evidence", "Missing", "Conditions", "Explanation", "Facts"})


def customer_text(value):
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(lambda match: (replacement[0].upper() + replacement[1:]
                            if replacement and match[0][0].isupper() else replacement), value)
    value = value.replace(";", ",").replace("；", ",")
    value = re.sub(r"(?<=\S)[ \t]{2,}(?=\S)", " ", value)
    return re.sub(r"[ \t]+([,;:.])", r"\1", value).strip()


def _snapshot(value, prose=False):
    if isinstance(value, str):
        return customer_text(value) if prose else value
    if isinstance(value, list):
        return [_snapshot(item, prose) for item in value]
    if isinstance(value, dict):
        return {key: _snapshot(item, key in _PROSE_FIELDS) for key, item in value.items()}
    return value


def customer_notes(notes):
    return {key: _snapshot(value) if key in ("Comparison", "Compatibility") else value
            for key, value in notes.items()}
