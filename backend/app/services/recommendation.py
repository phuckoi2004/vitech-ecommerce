"""Catalog-based soft ranking of products that already passed the hard filters in AiTools.

Score = Σ wᵢ·sᵢ / Σ wᵢ over the active criteria: N need 0.40, B budget 0.25, T soft brand 0.20, every sᵢ in [0, 1].
The Phase 10 design also had H (purchase/wishlist history, 0.15). Catalog-based advice leaves it out on purpose, so a
new customer and a returning one get the same ranking for the same request: with every criterion active the formula is
(0.40·N + 0.25·B + 0.20·T) / 0.85. A criterion with nothing to measure (no budget, no soft brand) is left out instead of
scoring 0, so its absence never lowers every product.

N is the weighted mean of graded checks on real Specifications values (units normalized first). Data that is missing
or not stated scores 0 and is reported as a gap; it never counts as met. A check that no candidate in the current set
has data for cannot tell candidates apart and is dropped for that set (see `rank`). Without a stated need, phones,
laptops and tablets are compared on a balanced configuration profile instead of on price alone. Weights, anchors and
chip tiers are design hypotheses documented in docs/stage10-ai-advisor-upgrade.md, not a claim of optimality.
Pure functions: no database access.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

from app.core.search_text import fold

WEIGHTS = {"N": 0.40, "B": 0.25, "T": 0.20}
CANDIDATE_PAGE = 30  # Listing page read per search; a second page is read only when the first one is full.
CANDIDATE_MAX = 60  # Eligible candidates scored per search (2 pages). The largest VieTech category has 35 products.
RESULT_LIMIT = 5  # Ranked candidates shown to the model and the maximum number of cards in an answer.
CATEGORY_WEIGHT = 0.2  # VieTech's curated child category ("Laptop lập trình") as one need criterion.
GENERAL = "general"  # Profile used when the customer states no specific need for a phone, laptop or tablet.

MET, UNMET, MISSING = "met", "unmet", "missing"


@dataclass(frozen=True)
class Result:
    status: str
    evidence: str
    score: float = 0.0  # Graded share in [0, 1]; 0 when missing.


def _values(specs, *names):
    """Values of the named keys, in the priority order given (catalog keys vary in case and accents)."""
    folded = {}
    for key, value in (specs or {}).items():
        if isinstance(value, (str, int, float)) and str(value).strip():
            folded.setdefault(fold(str(key)), str(value))
    return [folded[fold(name)] for name in names if fold(name) in folded]


def _value(specs, *names):
    values = _values(specs, *names)
    return values[0] if values else None


def _number(amount):
    return f"{amount:g}".replace(".", ",")


def _amount(text):
    """"5.000" → 5000, "60,9" → 60.9: a dot/comma before exactly three digits is a thousands separator."""
    return float(re.sub(r"[.,](?=\d{3}\b)", "", text).replace(",", "."))


def _shown(amount, unit):
    return (f"{amount:,.0f}".replace(",", ".") if unit == "mAh" else _number(amount)) + f" {unit}"


def _short(text, limit=48):
    text = re.split(r"\s*[(;,]", text, maxsplit=1)[0].strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _ramp(value, low, high):
    """Linear share between two anchors: `low` or worse → 0, `high` or better → 1 (works for "smaller is better")."""
    if high == low:
        return 1.0 if value >= high else 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


# Each check takes (specs, name, category) and returns a Result. Evidence quotes catalog data; it never guesses a
# missing value. `threshold` decides MET/UNMET for the evidence wording; the graded score ranks within that.

def _memory(threshold, low, high, label, *keys):
    def check(specs, _name, _category):
        value = _value(specs, *keys)
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*(tb|gb)\b", fold(value or ""))
        if not match:
            return Result(MISSING, f"chưa có dữ liệu {label}")
        size = _amount(match[1]) * (1024 if match[2] == "tb" else 1)
        score = _ramp(size, low, high)
        if size >= threshold:
            return Result(MET, f"{label} {_number(size)} GB", score)
        return Result(UNMET, f"{label} {_number(size)} GB (dưới {threshold} GB)", score)
    return check


def _storage(threshold, low, high):
    """Laptop storage capacity. Most catalog rows say "512GB" without the type; only a stated HDD fails it."""
    def check(specs, _name, _category):
        value = _value(specs, "Ổ cứng", "SSD")
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*(tb|gb)\b", fold(value or ""))
        if not match:
            return Result(MISSING, "chưa có dữ liệu ổ cứng")
        size = _amount(match[1]) * (1024 if match[2] == "tb" else 1)
        text = fold(value)
        kind = "SSD" if re.search(r"ssd|nvme|pcie", text) else "ổ cứng"
        if re.search(r"\bhdd\b", text) and kind != "SSD":
            return Result(UNMET, f"ổ cứng HDD {_number(size)} GB (không phải SSD)")
        score = _ramp(size, low, high)
        if size >= threshold:
            return Result(MET, f"{kind} {_number(size)} GB", score)
        return Result(UNMET, f"{kind} {_number(size)} GB (dưới {threshold} GB)", score)
    return check


def _pattern(label, keys, pattern, *, met=None, unmet=None):
    """Text evidence such as optical stabilization or upgradable RAM.

    With `unmet`, a stated value that does not match is a definite miss. Without it, a text that does not mention the
    feature only leaves it unconfirmed: a camera description without "OIS" proves nothing.
    """
    def check(specs, _name, _category):
        value = _value(specs, *keys)
        if value is None:
            return Result(MISSING, f"chưa có dữ liệu {label}")
        if re.search(pattern, fold(value)):
            return Result(MET, met or f"{label} {_short(value)}", 1.0)
        if unmet:
            return Result(UNMET, f"{label} {_short(value)} ({unmet})")
        return Result(MISSING, f"chưa xác nhận {label}")
    return check


def _numeric(label, keys, pattern, threshold, unit, low, high):
    """Largest stated amount across the listed keys (e.g. 120 Hz may sit under screen features), graded low → high."""
    def check(specs, _name, _category):
        amounts = [_amount(match[1]) for value in _values(specs, *keys) for match in re.finditer(pattern, fold(value))]
        if not amounts:
            return Result(MISSING, f"chưa có dữ liệu {label}")
        amount = max(amounts)
        score = _ramp(amount, low, high)
        if amount >= threshold:
            return Result(MET, f"{label} {_shown(amount, unit)}", score)
        return Result(UNMET, f"{label} {_shown(amount, unit)} (dưới {_shown(threshold, unit)})", score)
    return check


def _weight(limit_kg, worst_kg):
    def check(specs, _name, _category):
        grams = [_amount(match[1]) * (1000 if match[2] == "kg" else 1)
                 for value in _values(specs, "Trọng lượng", "Khối lượng")
                 for match in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(kg|g)\b", fold(value))]
        if not grams:
            return Result(MISSING, "chưa có dữ liệu khối lượng")
        weight = min(grams)
        kg = limit_kg >= 1
        shown = f"{_number(weight / 1000)} kg" if kg else f"{_number(weight)} g"
        limit = f"{_number(limit_kg)} kg" if kg else f"{_number(limit_kg * 1000)} g"
        score = _ramp(weight, worst_kg * 1000, limit_kg * 1000)
        if weight <= limit_kg * 1000:
            return Result(MET, f"nặng {shown}", 1.0)
        return Result(UNMET, f"nặng {shown} (trên {limit})", score)
    return check


def _screen_size(limit, worst):
    """Compactness from the stated diagonal; says "màn hình 14 inch", never claims a weight."""
    def check(specs, _name, _category):
        value = _value(specs, "Kích thước màn hình")
        match = re.search(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:inch(?:es)?|\"|”|in\b)", fold(value or ""))
        if not match:
            return Result(MISSING, "chưa có dữ liệu kích thước màn hình")
        size = float(match[1].replace(",", "."))
        if size <= limit:
            return Result(MET, f"màn hình {_number(size)} inch, gọn hơn", 1.0)
        return Result(UNMET, f"màn hình {_number(size)} inch (lớn hơn {_number(limit)} inch)", _ramp(size, worst, limit))
    return check


# Chip classes by the family name stated in the catalog. A heuristic table, documented and tested; it reads only the
# chip the catalog lists and never assumes benchmark figures.
PHONE_CHIP_TIERS = (
    ("high", 1.0, r"snapdragon\W*8\b|dimensity\s*(?:8|9)\d{3}|\b(?:apple\s*|chip\s*)?a(?:1[5-9]|2\d)\b"
                  r"|exynos\s*2\d{3}|tensor|kirin\s*9\d{3}|\bapple\s*m[1-9]\b|\bm[1-9]\b"),
    ("mid", 0.55, r"snapdragon\W*7|snapdragon\W*6\s*gen\s*[4-9]|dimensity\s*7\d{3}|\bd7\d{3}\b"
                  r"|exynos\s*1[3-9]\d{2}|helio\s*g9\d"),
    ("entry", 0.15, r"helio|unisoc|spreadtrum|\bt6\d{2}\b|snapdragon\W*[4-6]|dimensity\s*6\d{3}"),
)
LAPTOP_CPU_TIERS = (
    ("high", 1.0, r"core\s*(?:ultra\s*)?[79]\b|core\s*i[79]\b|ryzen\s*(?:ai\s*)?(?:[79]|max)\b|\bapple\s*m[1-9]\b"
                  r"|\bmacbook\b.*\bm[1-9]\b|snapdragon\s*x\s*elite"),
    ("mid", 0.75, r"core\s*(?:ultra\s*)?5\b|core\s*i5\b|ryzen\s*(?:ai\s*)?5\b|snapdragon\s*x|\ba1[7-9]\s*pro\b"),
    ("entry", 0.2, r"core\s*i3\b|core\s*3\b|ryzen\s*3\b|celeron|pentium|athlon|mediatek|intel\s*n\d{2,3}\b"),
)
TIER_LABELS = {"high": "nhóm hiệu năng cao", "mid": "nhóm tầm trung", "entry": "nhóm phổ thông"}


def _tier(label, keys, tiers, *, met_tiers, use_name=False):
    """Chip/CPU class from the stated family; an unlisted family is "chưa xếp nhóm", not a guessed miss."""
    def check(specs, name, _category):
        stated = _values(specs, *keys)
        texts = [(text, False) for text in stated] + ([(name, True)] if use_name and name else [])
        if not stated:
            return Result(MISSING, f"chưa có dữ liệu {label}")
        for text, from_name in texts:
            for tier, score, pattern in tiers:
                if re.search(pattern, fold(text)):
                    # Only the product name states the chip ("MacBook Air M4"): quote the chip, not the whole name.
                    chip = re.search(r"\bm[1-9](?:\s*(?:pro|max))?\b", fold(text)) if from_name else None
                    shown = f"Apple {chip[0].upper()}" if chip else re.sub(r"^chip\s+", "", _short(text), flags=re.I)
                    evidence = f"{label} {shown} ({TIER_LABELS[tier]})"
                    return Result(MET if tier in met_tiers else UNMET, evidence, score)
        return Result(MISSING, f"chưa xếp nhóm {label}")
    return check


def _gpu(label="GPU"):
    """Discrete graphics graded by class (xx50 < xx60 < xx70+); integrated graphics is a stated miss."""
    def check(specs, _name, _category):
        value = _value(specs, "Loại card đồ họa", "Card đồ họa", "GPU")
        if value is None:
            return Result(MISSING, f"chưa có dữ liệu {label}")
        text = fold(value)
        rtx = re.search(r"rtx\s*(?:a)?\s*(\d)0([5-9])0", text)
        if rtx:
            score = {"5": 0.6, "6": 0.8}.get(rtx[2], 1.0)
        elif re.search(r"radeon\s*rx", text):
            score = 0.7
        elif re.search(r"\barc\s*a\d|quadro|rtx", text):
            score = 0.6
        elif re.search(r"gtx", text):
            score = 0.4
        else:
            return Result(UNMET, f"{label} {_short(value)} (không có GPU rời)")
        return Result(MET, f"{label} {_short(value)}", score)
    return check


def _in_category(*terms):
    def check(_specs, _name, category):
        if category and any(term in fold(category) for term in terms):
            return Result(MET, f"thuộc nhóm {category}", 1.0)
        return Result(UNMET, "")
    return check


RAM = ("Dung lượng RAM", "RAM")
STORAGE = ("Bộ nhớ trong", "ROM")
SCREEN = ("Tần số quét", "Tính năng màn hình", "Công nghệ màn hình", "Màn hình")
CHIP = ("Chipset", "Chip xử lý", "Loại CPU", "CPU")
LAPTOP_CPU = ("Loại CPU", "CPU", "Chip xử lý", "Chipset")
HZ = r"(\d{2,3})\s*hz"
MAH = r"(\d{1,2}(?:[.,]\d{3})+|\d{4,5})\s*mah"
WH = r"(\d+(?:[.,]\d+)?)\s*(?:wh(?:rs?)?\b|watt\W*gio)"
WATT = r"(\d{2,3})\s*w(?![a-z])"


@dataclass(frozen=True)
class Need:
    label: str
    triggers: tuple[str, ...]  # On folded text (no accents).
    category_terms: tuple[str, ...]
    criteria: dict  # product type -> [(id, weight, label, check)]
    accented: tuple[str, ...] = ()  # On lowercase text with accents, where folding merges words ("nhẹ"/"nhé").


def _c(id_, weight, label, check):
    return (id_, weight, label, check)


# Balanced configuration: what a sales advisor compares when the customer only gives a category and a budget.
GENERAL_CRITERIA = {
    "phone": [
        _c("chip", 0.30, "chip xử lý", _tier("chip", CHIP, PHONE_CHIP_TIERS, met_tiers={"high", "mid"})),
        _c("ram", 0.15, "RAM", _memory(8, 4, 12, "RAM", *RAM)),
        _c("storage", 0.10, "bộ nhớ trong", _memory(128, 64, 256, "bộ nhớ", *STORAGE)),
        _c("battery", 0.20, "dung lượng pin", _numeric("pin", ("Pin", "Dung lượng pin"), MAH, 5000, "mAh", 4000, 6000)),
        _c("hz", 0.10, "tần số quét màn hình", _numeric("màn hình", SCREEN, HZ, 120, "Hz", 60, 120)),
        _c("ois", 0.15, "camera chống rung quang học", _pattern(
            "chống rung quang học", ("Camera sau",), r"chong rung quang hoc|\bois\b", met="camera có chống rung quang học")),
    ],
    "laptop": [
        _c("cpu", 0.30, "CPU", _tier("CPU", LAPTOP_CPU, LAPTOP_CPU_TIERS, met_tiers={"high", "mid"}, use_name=True)),
        _c("ram", 0.25, "RAM", _memory(16, 4, 16, "RAM", *RAM)),
        _c("ssd", 0.20, "ổ cứng", _storage(512, 128, 512)),
        _c("gpu", 0.10, "card đồ họa", _gpu()),
        _c("battery", 0.15, "pin", _numeric("pin", ("Pin",), WH, 50, "Wh", 40, 70)),
    ],
    "tablet": [
        _c("chip", 0.30, "chip xử lý", _tier("chip", CHIP, PHONE_CHIP_TIERS, met_tiers={"high", "mid"})),
        _c("ram", 0.20, "RAM", _memory(6, 4, 8, "RAM", *RAM)),
        _c("storage", 0.20, "bộ nhớ trong", _memory(128, 64, 256, "bộ nhớ", *STORAGE)),
        _c("battery", 0.15, "dung lượng pin", _numeric("pin", ("Pin", "Dung lượng pin"), MAH, 7000, "mAh", 5000, 9000)),
        _c("hz", 0.15, "tần số quét màn hình", _numeric("màn hình", SCREEN, HZ, 90, "Hz", 60, 120)),
    ],
}

# Anchors per segment are test hypotheses (docs/stage10-ai-advisor-upgrade.md, section "Tiêu chí N").
NEEDS = {
    GENERAL: Need("cấu hình cân bằng", (), (), GENERAL_CRITERIA),
    "value": Need("ngon trong tầm giá", (r"ngon trong tam gia", r"dang (?:dong )?tien", r"gia tot", r"ngon bo re",
                                          r"\bp/?p\b", r"hieu nang tren gia", r"cau hinh (?:tot|manh|cao)"),
                  (), GENERAL_CRITERIA),
    "programming": Need("lập trình", (r"lap trinh", r"\bcode\b", r"coding", r"developer", r"cong nghe thong tin",
                                      r"\bcntt\b"), ("lap trinh",), {
        "laptop": [
            _c("ram16", 0.35, "RAM", _memory(16, 8, 16, "RAM", *RAM)),
            _c("ssd512", 0.25, "SSD", _storage(512, 128, 512)),
            _c("cpu", 0.25, "CPU", _tier("CPU", LAPTOP_CPU, LAPTOP_CPU_TIERS, met_tiers={"high", "mid"}, use_name=True)),
            _c("ram_upgrade", 0.15, "khả năng nâng cấp RAM", _pattern(
                "khe RAM", ("Số khe ram",), r"nang cap|\b[2-9]\s*khe", met="RAM nâng cấp được", unmet="không ghi nâng cấp")),
        ],
    }),
    "gaming": Need("chơi game", (r"choi game", r"gaming", r"\bgame\b", r"lien quan", r"pubg", r"genshin",
                                 r"fps cao"), ("gaming", "choi game"), {
        "laptop": [
            _c("gpu", 0.45, "card đồ họa rời", _gpu()),
            _c("ram16", 0.25, "RAM", _memory(16, 8, 16, "RAM", *RAM)),
            _c("cpu", 0.15, "CPU", _tier("CPU", LAPTOP_CPU, LAPTOP_CPU_TIERS, met_tiers={"high", "mid"}, use_name=True)),
            _c("hz144", 0.15, "tần số quét", _numeric("màn hình", SCREEN, HZ, 120, "Hz", 60, 144)),
        ],
        "phone": [
            _c("chip", 0.45, "chip xử lý", _tier("chip", CHIP, PHONE_CHIP_TIERS, met_tiers={"high"})),
            _c("ram8", 0.25, "RAM", _memory(8, 6, 12, "RAM", *RAM)),
            _c("hz120", 0.30, "tần số quét", _numeric("màn hình", SCREEN, HZ, 120, "Hz", 60, 120)),
        ],
        "tablet": [
            _c("chip", 0.45, "chip xử lý", _tier("chip", CHIP, PHONE_CHIP_TIERS, met_tiers={"high"})),
            _c("ram8", 0.25, "RAM", _memory(8, 4, 8, "RAM", *RAM)),
            _c("hz90", 0.30, "tần số quét", _numeric("màn hình", SCREEN, HZ, 90, "Hz", 60, 120)),
        ],
    }),
    "creative": Need("đồ họa/dựng video", (r"do hoa", r"thiet ke", r"dung (?:phim|video)", r"edit (?:anh|video)",
                                            r"chinh sua (?:anh|video)", r"\brender\b"), ("do hoa", "sang tao"), {
        "laptop": [
            _c("gpu", 0.40, "card đồ họa rời", _gpu()),
            _c("ram16", 0.30, "RAM", _memory(16, 8, 32, "RAM", *RAM)),
            _c("cpu", 0.30, "CPU", _tier("CPU", LAPTOP_CPU, LAPTOP_CPU_TIERS, met_tiers={"high"}, use_name=True)),
        ],
        "tablet": [
            _c("chip", 0.5, "chip xử lý", _tier("chip", CHIP, PHONE_CHIP_TIERS, met_tiers={"high"})),
            _c("ram8", 0.5, "RAM", _memory(8, 4, 12, "RAM", *RAM)),
        ],
    }),
    "study": Need("học tập/văn phòng", (r"hoc tap", r"sinh vien", r"hoc sinh", r"van phong", r"lam viec", r"hoc online",
                                        r"di hoc"), ("hoc tap", "van phong"), {
        "laptop": [
            _c("ram8", 0.30, "RAM", _memory(8, 4, 16, "RAM", *RAM)),
            _c("ssd256", 0.25, "ổ cứng", _storage(256, 128, 512)),
            _c("battery", 0.20, "pin", _numeric("pin", ("Pin",), WH, 50, "Wh", 40, 70)),
            _c("light16", 0.25, "khối lượng", _weight(1.6, 2.5)),
        ],
        "tablet": [
            _c("ram4", 0.5, "RAM", _memory(4, 3, 8, "RAM", *RAM)),
            _c("storage128", 0.5, "bộ nhớ trong", _memory(128, 64, 256, "bộ nhớ", *STORAGE)),
        ],
    }),
    "battery": Need("pin trâu", (r"pin (?:(?:phai|that|can|rat|cuc|sieu|kha|that su) )?"
                                 r"(?:trau|tot|lau|khoe|ben|ngon|cao|lon|du|manh)", r"dung luong pin",
                                 r"pin nhieu", r"sac nhanh", r"thoi luong pin"), ("pin trau",), {
        # mAh/Wh is a capacity signal and charging power a convenience signal, not a promise of screen-on time.
        "phone": [_c("mah5000", 0.75, "dung lượng pin", _numeric("pin", ("Pin", "Dung lượng pin"), MAH, 5000, "mAh",
                                                                 4000, 7000)),
                  _c("charge33", 0.25, "công suất sạc", _numeric("sạc", ("Công nghệ sạc", "Sạc", "Công suất sạc", "Pin"),
                                                                  WATT, 33, "W", 18, 67))],
        "tablet": [_c("mah7000", 1.0, "dung lượng pin", _numeric("pin", ("Pin", "Dung lượng pin"), MAH, 7000, "mAh",
                                                                 5000, 10000))],
        "laptop": [_c("wh50", 1.0, "dung lượng pin", _numeric("pin", ("Pin",), WH, 50, "Wh", 40, 80))],
    }),
    "camera": Need("chụp ảnh", (r"chup anh", r"chup hinh", r"camera", r"quay phim", r"quay video", r"selfie"),
                   ("chup anh",), {
        # Never from megapixels alone: only stated optical stabilization and telephoto/optical zoom.
        "phone": [_c("ois", 0.6, "chống rung quang học", _pattern(
                      "chống rung quang học", ("Camera sau",), r"chong rung quang hoc|\bois\b",
                      met="camera có chống rung quang học")),
                  _c("tele", 0.4, "ống kính tele/zoom quang", _pattern(
                      "ống kính tele/zoom quang", ("Camera sau",), r"tele|zoom quang|tiem vong|periscope",
                      met="camera có ống kính tele/zoom quang"))],
    }),
    # Folding turns "nhẹ" (light) and the particle "nhé" into the same "nhe", so a bare "nhẹ" is matched with accents.
    "portable": Need("mỏng nhẹ", (r"mong nhe", r"gon nhe", r"nho gon", r"de mang", r"mang di"), ("mong nhe", "nho gon"), {
        "laptop": [_c("light15", 0.6, "khối lượng", _weight(1.5, 2.5)),
                   _c("size14", 0.4, "kích thước", _screen_size(14, 16))],
        "phone": [_c("light190", 0.6, "khối lượng", _weight(0.19, 0.24)),
                  _c("size63", 0.4, "kích thước", _screen_size(6.3, 6.9))],
    }, accented=(r"\bnhẹ\b(?! nhàng)",)),
}

GENERAL_KINDS = frozenset(GENERAL_CRITERIA)


def detect_needs(question):
    """Usage needs named in the question, in NEEDS order; the balanced profile is never "detected"."""
    text, accented = fold(question), unicodedata.normalize("NFC", question).lower()
    return tuple(name for name, need in NEEDS.items()
                 if name != GENERAL and (any(re.search(trigger, text) for trigger in need.triggers)
                                         or any(re.search(trigger, accented) for trigger in need.accented)))


def product_type(root_category_name):
    name = fold(root_category_name or "")
    if "laptop" in name:
        return "laptop"
    if "dien thoai" in name:
        return "phone"
    if "may tinh bang" in name or "tablet" in name:
        return "tablet"
    return None


def priorities(needs, kind):
    """Criterion labels the advice should focus on, for the model note and the report."""
    labels = []
    for name in needs or ((GENERAL,) if kind in GENERAL_KINDS else ()):
        for _, _, label, _ in NEEDS[name].criteria.get(kind, []):
            if label not in labels:
                labels.append(label)
    return labels


def model_key(name):
    """Canonical model name: one model sold as several products (storage, colour, 5G) is still one model."""
    text = fold((name or "").split("|")[0])
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\b(?:dien thoai|laptop|may tinh bang|chinh hang|viet nam)\b", " ", text)
    text = re.sub(r"\b\d+\s*(?:gb|tb)\b|\b[45]g\b", " ", text)
    text = re.sub(r"\b(?:den|trang|xam|bac|vang|hong|xanh(?: duong| la)?|tim|do|black|white|gray|grey|silver|gold|"
                  r"blue|green|pink|purple|titan(?:ium)?(?: \w+)?)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


@dataclass(frozen=True)
class RankingCriteria:
    needs: tuple[str, ...] = ()
    soft_brand_ids: frozenset = frozenset()


@dataclass(frozen=True)
class Candidate:
    product_id: str
    brand_id: str
    name: str
    category_name: str
    kind: str | None
    specs: dict
    price: Decimal


@dataclass
class Evaluation:
    score: float | None
    parts: dict = field(default_factory=dict)
    matched: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    completeness: float = 1.0
    soft_brand: bool = False


GENERAL_SHARE = 0.25  # With a stated need, the balanced profile still decides 25% of N (phones, laptops, tablets).


def _criteria(needs, kind):
    """(id, weight, check) of every active need for this product type, plus each need's curated-category check.

    A stated need keeps 75% of N; the balanced profile adds the other 25%, so two phones with the same battery are
    told apart by the rest of their configuration rather than by price alone.
    """
    checks, seen = [], set()
    for name in needs or ((GENERAL,) if kind in GENERAL_KINDS else ()):
        need = NEEDS[name]
        rows = [(id_, weight, check) for id_, weight, _, check in need.criteria.get(kind, [])]
        if need.category_terms:
            rows.append((f"category:{name}", CATEGORY_WEIGHT, _in_category(*need.category_terms)))
        for row in rows:
            if row[0] not in seen:
                seen.add(row[0])
                checks.append(row)
    if needs and kind in GENERAL_KINDS and not {GENERAL, "value"} & set(needs):
        stated = sum(weight for _, weight, _ in checks)
        general = GENERAL_CRITERIA[kind]
        scale = stated * GENERAL_SHARE / (1 - GENERAL_SHARE) / sum(weight for _, weight, _, _ in general)
        checks += [(f"general:{id_}", weight * scale, check) for id_, weight, _, check in general]
    return checks


def assess(criteria, candidate):
    """Raw check results for one candidate: [(criterion id, weight, Result)]."""
    return [(id_, weight, check(candidate.specs, candidate.name, candidate.category_name))
            for id_, weight, check in _criteria(criteria.needs, candidate.kind)]


def uninformative(assessments):
    """Criteria no candidate has data for (or, for curated categories, no candidate belongs to): they cannot tell
    candidates apart, so they are dropped for this candidate set instead of lowering everyone's N."""
    statuses = {}
    for rows in assessments:
        for id_, _, result in rows:
            statuses.setdefault(id_, set()).add(result.status)
    return frozenset(id_ for id_, seen in statuses.items()
                     if (MET not in seen if id_.startswith("category:") else seen == {MISSING}))


def need_score(rows, dropped=frozenset()):
    """Weighted mean of graded checks; missing data scores 0. Returns (N, matched, gaps, completeness)."""
    active = [(weight, result) for id_, weight, result in rows if id_ not in dropped]
    total = sum(weight for weight, _ in active)
    if not total:
        return None, [], [], 1.0
    got = sum(weight * result.score for weight, result in active)
    present = sum(weight for weight, result in active if result.status != MISSING)
    # Need rows come before the balanced profile, so when both quote the same fact ("chip … (nhóm tầm trung)") the
    # stated need's verdict is the one shown, once.
    matched, gaps, seen = [], [], set()
    for _, result in active:
        if result.evidence and result.evidence not in seen:
            seen.add(result.evidence)
            (matched if result.status == MET else gaps).append(result.evidence)
    return got / total, matched, gaps, present / total


def evaluate(criteria, candidate, *, budget_max, rows=None, dropped=frozenset()):
    rows = assess(criteria, candidate) if rows is None else rows
    result, parts = Evaluation(None), {}
    n, result.matched, result.gaps, result.completeness = need_score(rows, dropped)
    if n is not None:
        parts["N"] = n
    if budget_max:
        # Inside the budget, a moderate preference for savings; never "the more expensive the better".
        parts["B"] = max(0.0, min(1.0, 0.70 + 0.30 * float(Decimal(budget_max) - Decimal(candidate.price)) / budget_max))
    if criteria.soft_brand_ids:
        result.soft_brand = candidate.brand_id in criteria.soft_brand_ids
        parts["T"] = 1.0 if result.soft_brand else 0.0
    result.parts = parts
    if parts:
        result.score = sum(WEIGHTS[key] * value for key, value in parts.items()) / sum(WEIGHTS[key] for key in parts)
    return result


def ranking_key(evaluation, candidate, position):
    """Higher score first, compared at the two decimals shown to the model (a smaller difference is noise, often
    only the budget term). Ties: better need fit N, more complete data, lower price, then ProductId, so a cheaper
    product never passes a better-fitting one on a hair's breadth. Without any score the catalog order is kept."""
    if evaluation is None or evaluation.score is None:
        return (1, position)
    return (0, -round(evaluation.score, 2), -round(evaluation.parts.get("N", 0.0), 6),
            -round(evaluation.completeness, 6), Decimal(candidate.price), candidate.product_id)


def rank(criteria, candidates, *, budget_max, dropped=None):
    """Score a hard-filtered candidate set and sort it. `dropped` reuses the criteria a previous search dropped."""
    assessments = [assess(criteria, candidate) for candidate in candidates]
    if dropped is None:
        dropped = uninformative(assessments)
    evaluations = [evaluate(criteria, candidate, budget_max=budget_max, rows=rows, dropped=dropped)
                   for candidate, rows in zip(candidates, assessments)]
    order = sorted(range(len(candidates)), key=lambda i: ranking_key(evaluations[i], candidates[i], i))
    return [(candidates[i], evaluations[i]) for i in order], dropped
