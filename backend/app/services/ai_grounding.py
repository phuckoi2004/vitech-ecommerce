"""Checks a model-written answer against the facts this turn actually read, before a customer sees it.

Gemini writes the wording; the backend decides whether it may be shown. Every quantity (price, GB, mAh, Hz, months…),
model token ("S25", "i7-13620H") and brand in the message must come from this turn's catalog data, the customer's own
question or coupon data read with list_offers. A line that names one product is checked against that product only.
Claims VieTech has no data for (installments, gifts, battery hours, "best in the segment") and personal reasons
("bạn đã mua…") are refused. A refused message is never shown: the backend's own grounded text replaces it.
Pure functions: no database access.
"""

import re
from dataclasses import dataclass, field

from app.core.search_text import fold

from .recommendation import model_key

MAX_MESSAGE = 1500
_MONEY_TOLERANCE = 50_000  # "khoảng 8 triệu" for 7.990.000 đ; amounts written in đồng must match exactly.

_UNITS = {
    "mah": "mah", "whrs": "wh", "whr": "wh", "wh": "wh", "ghz": "ghz", "mhz": "mhz", "gb": "gb", "tb": "tb", "mb": "mb",
    "hz": "hz", "mp": "mp", "inches": "inch", "inch": "inch", '"': "inch", "”": "inch", "kg": "kg", "g": "g", "nm": "nm",
    "nits": "nits", "mm": "mm", "w": "w", "%": "%", "thang": "thang", "nam": "nam", "gio": "gio", "phut": "phut",
    "loi": "loi", "nhan": "loi", "luong": "luong", "cell": "cell",
    "trieu": "trieu", "tr": "trieu", "nghin": "nghin", "ngan": "nghin", "k": "nghin", "dong": "dong", "vnd": "dong",
    "d": "dong", "₫": "dong",
}
_MONEY_UNITS = {"trieu": 1_000_000, "nghin": 1000, "dong": 1}
_QUANTITY = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)*)\s*(" + "|".join(
    re.escape(unit) for unit in sorted(_UNITS, key=len, reverse=True)) + r")(?![a-z0-9])")
_WATT_HOURS = re.compile(r"(\d+(?:[.,]\d+)?)\s*watt\W*gio")
_NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*(?![\w.,%])")
_TOKEN = re.compile(r"\b(?=[a-z0-9-]*[a-z])(?=[a-z0-9-]*\d)[a-z0-9]+(?:-[a-z0-9]+)*\b")
_NETWORK = re.compile(r"\b[2-6]g\b")
_CODE = re.compile(r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{5,}\b")

_INTERNAL = re.compile(r"search_products|get_product|list_offers|present_answer|\branking\b|system prompt|system instruction"
                       r"|\bapi[ _]?key\b|gemini_api|function call|\bjson\b|thong tin san pham tu catalog")
_PERSONAL = re.compile(r"\bda mua\b|\bda (?:tung )?(?:yeu thich|them vao yeu thich)\b|\blich su mua\b|\bwishlist\b"
                       r"|\bdanh sach yeu thich\b|\bgio hang cua ban\b")
_CLAIMS = re.compile(r"\btra gop\b|\btang kem\b|\bqua tang\b|\bmien phi (?:van chuyen|giao hang)\b|\bfreeship\b"
                     r"|\bbao hanh vang\b|\b1 doi 1\b|\bsap ve\b|\bdat truoc\b|\bpre-?order\b|\bhang hot\b"
                     r"|\bban chay nhat\b|\b(?:tot|manh|re|dep|ngon|xin) nhat (?:phan khuc|thi truong|the gioi|hien nay|viet nam)\b"
                     r"|\b(?:ca|tron|mot|1|hai|2|ba|3) ngay\b")
_PROMOTION = re.compile(r"\b(?:dang|duoc)\s+(?:giam|khuyen mai|sale|uu dai)\b|\bgiam (?:gia|ngay|them)\b|\bkhuyen mai\b"
                        r"|\bvoucher\b|\bcoupon\b|\bma giam\b")
_CONTACT = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\d)(?:\+?84|0)(?:[ .-]?\d){8,10}(?!\d)|https?://|www\.")


@dataclass
class ProductFacts:
    product_id: str
    name: str
    brand: str
    texts: list[str] = field(default_factory=list)
    money: set[int] = field(default_factory=set)


@dataclass
class Facts:
    products: list[ProductFacts] = field(default_factory=list)
    shared_texts: list[str] = field(default_factory=list)  # The question, coupon data, budget amounts.
    money: set[int] = field(default_factory=set)
    brands: tuple[str, ...] = ()  # Every visible brand name, to notice brands the data does not support.
    promotions: bool = False  # list_offers was read or a selected price carries an automatic discount.
    order: list[str] = field(default_factory=list)  # Card order the message must not contradict.


def sanitize(message):
    """Plain text for the chat bubble (rendered with pre-wrap, not Markdown)."""
    text = re.sub(r"\*\*|__|`+", "", message or "")
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*[*•]\s+", "- ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _value(text):
    """"5.000" → 5000, "17.990.000" → 17990000, "6,1" → 6.1, "53.8" → 53.8."""
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", text):
        return float(re.sub(r"[.,]", "", text))
    if text.count(".") + text.count(",") > 1:
        return None
    return float(text.replace(",", "."))


def _quantities(folded):
    """[(value, unit, span)] for numbers followed by a unit; network generations ("5G") are not grams."""
    masked = _NETWORK.sub(lambda match: "#" * len(match[0]), folded)
    found = []
    for match in _QUANTITY.finditer(masked):
        value = _value(match[1])
        if value is not None:
            found.append((value, _UNITS[match[2]], match.span()))
    for match in _WATT_HOURS.finditer(masked):
        value = _value(match[1])
        if value is not None:
            found.append((value, "wh", match.span()))
    return found


class _Corpus:
    """Numbers, (number, unit) pairs, money and model tokens of a set of fact texts."""

    def __init__(self, texts, money):
        folded = " ".join(fold(str(text)) for text in texts if text)
        self.folded = folded
        self.compact = re.sub(r"[\s-]+", "", folded)
        self.money = set(money)
        self.pairs, self.numbers = set(), set()
        for value, unit, _ in _quantities(folded):
            if unit in _MONEY_UNITS:
                self.money.add(round(value * _MONEY_UNITS[unit]))
                continue
            self.pairs.add((value, unit))
            if unit == "tb":
                self.pairs.update({(value * 1024, "gb"), (value * 1000, "gb")})
            if unit == "gb" and value >= 1000:
                self.pairs.update({(value / 1024, "tb"), (value / 1000, "tb")})
            if unit == "thang" and value % 12 == 0:
                self.pairs.add((value / 12, "nam"))
        for match in _NUMBER.finditer(folded):
            value = _value(match[0])
            if value is not None:
                self.numbers.add(value)

    def has_pair(self, value, unit):
        return any(unit == known_unit and abs(value - known) < 1e-6 for known, known_unit in self.pairs)

    def has_money(self, amount, unit):
        tolerance = _MONEY_TOLERANCE if unit == "trieu" else 0
        return any(abs(amount - known) <= tolerance for known in self.money)


def _aliases(product):
    """Ways a message may name a product: its canonical model name, without the brand, and a short prefix."""
    key = model_key(product.name)
    brand = fold(product.brand or "")
    names = {key}
    if brand and key.startswith(brand + " "):
        names.add(key[len(brand) + 1:])
    for name in list(names):
        tokens = name.split()
        if len(tokens) > 3:
            names.add(" ".join(tokens[:3]))
    return {name for name in names if len(name) >= 4 and (" " in name or re.search(r"\d", name))}


def _mentions(folded, aliases):
    """Products named in a text; "iPhone 17 Pro" names that model, not also "iPhone 17"."""
    matched = {product_id: [name for name in names
                            if re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", folded)]
               for product_id, names in aliases.items()}
    matched = {product_id: names for product_id, names in matched.items() if names}
    return {product_id for product_id, names in matched.items()
            if not all(any(name != longer and name in longer for other, others in matched.items() if other != product_id
                           for longer in others) for name in names)}


def _segments(text):
    return [part for line in text.splitlines() for part in re.split(r"(?<=[.!?;])\s+", line) if part.strip()]


def check_message(message, facts: Facts):
    """(clean message, issues). An empty issue list means every fact in the message is grounded."""
    clean = sanitize(message)
    issues = []
    if not clean:
        return clean, ["trống"]
    if len(clean) > MAX_MESSAGE:
        issues.append("quá dài")
    folded = fold(clean)
    if _INTERNAL.search(folded):
        issues.append("lộ chi tiết nội bộ")
    if _CONTACT.search(clean):
        issues.append("chứa liên hệ/đường dẫn")
    if _PERSONAL.search(folded):
        issues.append("lý do dựa trên lịch sử cá nhân")
    shared = _Corpus(facts.shared_texts, facts.money)
    every = _Corpus([*facts.shared_texts, *(text for p in facts.products for text in p.texts)],
                    facts.money | {amount for p in facts.products for amount in p.money})
    for match in _CLAIMS.finditer(folded):
        if match[0] not in every.folded:
            issues.append(f"khẳng định không có dữ liệu: {match[0]}")
    if _PROMOTION.search(folded) and not facts.promotions:
        issues.append("nhắc ưu đãi khi chưa tra cứu ưu đãi")
    for code in _CODE.findall(clean):
        if fold(code) not in every.folded and fold(code) not in every.compact:
            issues.append(f"mã/mẫu không có căn cứ: {code}")
    known_brands = {fold(p.brand) for p in facts.products if p.brand}
    known_brands |= {fold(b) for b in facts.brands if re.search(r"\b" + re.escape(fold(b)) + r"\b", shared.folded)}
    for brand in facts.brands:
        name = fold(brand)
        if name and name not in known_brands and re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", folded):
            issues.append(f"hãng không có căn cứ: {brand}")

    aliases = {p.product_id: _aliases(p) for p in facts.products}
    by_id = {p.product_id: p for p in facts.products}
    corpora, first_seen = {}, {}
    for index, segment in enumerate(_segments(clean)):
        text = fold(segment)
        named = _mentions(text, aliases)
        for product_id in named:
            first_seen.setdefault(product_id, index)
        key = frozenset(named)
        if key not in corpora:
            corpora[key] = _Corpus([*facts.shared_texts, *(t for pid in named for t in by_id[pid].texts)],
                                   facts.money | {a for pid in named for a in by_id[pid].money}) if named else every
        corpus = corpora[key]
        spans = []
        for value, unit, span in _quantities(text):
            spans.append(span)
            if unit in _MONEY_UNITS:
                amount = round(value * _MONEY_UNITS[unit])
                if not corpus.has_money(amount, unit):
                    issues.append(f"số tiền không có căn cứ: {segment[span[0]:span[1]].strip() or amount}")
            elif not corpus.has_pair(value, unit):
                issues.append(f"thông số không có căn cứ: {text[span[0]:span[1]]}")
        rest = text
        for start, end in sorted(spans, reverse=True):
            rest = rest[:start] + " " * (end - start) + rest[end:]
        rest = _NETWORK.sub(" ", rest)
        for match in _TOKEN.finditer(rest):
            token = match[0].replace("-", "")
            if token not in corpus.compact:
                issues.append(f"mẫu/thông số không có căn cứ: {match[0]}")
        rest = _TOKEN.sub(" ", rest)
        for match in _NUMBER.finditer(rest):
            value = _value(match[0])
            if value is not None and value > 10 and value not in corpus.numbers:
                issues.append(f"con số không có căn cứ: {match[0]}")

    # Products introduced in another order than the cards would make "máy thứ hai" ambiguous.
    positions = [first_seen[product_id] for product_id in facts.order if product_id in first_seen]
    if positions != sorted(positions):
        issues.append("thứ tự sản phẩm khác thứ tự thẻ")
    return clean, list(dict.fromkeys(issues))
