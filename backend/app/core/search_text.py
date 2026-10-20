"""Tìm sản phẩm theo từ khóa như khách gõ (docs/customer-search.md).

Không phân biệt hoa thường. Từ gõ không dấu khớp mọi dấu ("dien thoai" khớp "Điện thoại"); từ gõ có dấu khớp đúng
dấu đó ("cơ" không khớp "có"). Khoảng trắng thừa được gộp. Phía SQL dùng lower() và translate() có sẵn của
PostgreSQL, không cần extension unaccent hay cột tìm kiếm riêng.
"""
import re
import unicodedata

from sqlalchemy import func


def _letters():
    """Lowercase Latin letters with marks (all Vietnamese ones included) and the same letters without them."""
    pairs = []
    for code in (*range(0x00C0, 0x0250), *range(0x1E00, 0x1F00)):
        char = chr(code)
        parts = unicodedata.normalize("NFD", char)
        if char.islower() and len(parts) > 1 and parts[0].isascii() and parts[0].isalpha():
            pairs.append((char, parts[0]))
    pairs.append(("đ", "d"))
    return "".join(marked for marked, _ in pairs), "".join(plain for _, plain in pairs)


MARKED, PLAIN = _letters()
_TABLE = str.maketrans(MARKED, PLAIN)
MAX_WORDS = 10


def fold(text: str) -> str:
    """"  Điện  THOẠI " → "dien thoai"."""
    folded = unicodedata.normalize("NFC", text).lower().translate(_TABLE)
    return re.sub(r"\s+", " ", folded).strip()


def words(text: str) -> list[str]:
    """Distinct lowercase words of a search, marks kept, in the order typed (at most MAX_WORDS)."""
    lowered = re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).lower()).strip()
    return list(dict.fromkeys(lowered.split(" ")))[:MAX_WORDS] if lowered else []


def is_marked(word: str) -> bool:
    return fold(word) != word


def folded(expression):
    """SQL equivalent of fold() for stored NFC text (spaces are not squeezed)."""
    return func.translate(func.lower(expression), MARKED, PLAIN)


def like_pattern(text: str) -> str:
    """``%text%`` with LIKE wildcards in the text escaped by a backslash."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
