"""Intent detection, slot extraction and conversation context for catalog-based advice.

Pure functions over the folded question, the visible category/brand names and the slots saved with earlier turns; no
database or model access. The backend, not the model's memory, decides what a follow-up inherits, which products
"máy thứ hai" means and which products "đề xuất thêm" must not show again. Gemini receives the result as data.

Context rules (docs/stage10-ai-advisor-upgrade.md):
1. What the current question states wins.
2. A follow-up in the same category inherits the earlier category, budget, brands and needs that it does not restate.
3. A new budget replaces the old range; "bỏ giới hạn ngân sách" clears it.
4. Naming another root category starts a new need group: nothing from the old group is inherited.
5. A question about named or referenced products applies only the constraints it states itself.
6. Shown products and their order are read from the saved ProductReferences, so "máy thứ hai" is resolved by the
   backend; an ordinal or "máy này" that cannot be resolved is answered with a clarifying question, never a guess.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.core.search_text import fold

from .ai_policy import POLICY_TERMS, RETURN_TERMS, policy_topics
from .recommendation import NEEDS, detect_needs, model_key, priorities, product_type

INTENTS = ("product_recommendation", "recommend_more", "product_comparison", "product_information",
           "product_description", "price_inquiry", "promotion_inquiry", "policy_inquiry", "explain_recommendation",
           "follow_up_question", "general_chat")
RECOMMENDING = frozenset({"product_recommendation", "recommend_more"})
ABOUT_PRODUCTS = frozenset({"product_comparison", "product_information", "product_description", "price_inquiry",
                            "follow_up_question"})
# Answers about products already shown; they never start a new list for "máy thứ hai".
ABOUT_SHOWN = frozenset({"explain", "describe"})

# --- Budget -----------------------------------------------------------------------------------------------------

_MONEY_NUMBER = r"\d[\d., ]*?"
_MONEY_UNIT = r"trieu|tr\b|tr(?=\d)|vnd|dong|d\b|₫"
_MONEY_RANGE = re.compile(rf"({_MONEY_NUMBER})\s*({_MONEY_UNIT})?\s*(?:den|toi|[-–—])\s*"
                          rf"({_MONEY_NUMBER})\s*({_MONEY_UNIT})")
_CLEAR_BUDGET = ("bo gioi han ngan sach", "khong gioi han ngan sach", "bo gioi han gia", "khong gioi han gia",
                 "bao nhieu cung duoc", "khong quan trong gia", "gia nao cung duoc")


def _budget_amount(number, unit, tail=""):
    number = number.replace(" ", "")
    try:
        if unit.startswith("tr"):
            number = number.replace(",", ".")
            if number.count(".") > 1:
                return None
            amount = Decimal(number) * 1_000_000
            suffix = re.match(r"(\d{1,3})(?!\d)", tail)
            if suffix and "." not in number:
                amount += Decimal(suffix[1].ljust(3, "0")) * 1000
        else:
            amount = Decimal(number.replace(".", "").replace(",", ""))
        return int(amount) if 0 < amount <= 10**12 else None
    except InvalidOperation:
        return None


def _budget_ranges(text):
    for match in _MONEY_RANGE.finditer(text):
        lower, lower_unit, upper, upper_unit = match.groups()
        floor = _budget_amount(lower, lower_unit or upper_unit)
        ceiling = _budget_amount(upper, upper_unit, text[match.end():])
        if floor is not None and ceiling is not None:
            yield floor, ceiling


def budget_ceiling(question):
    """Recognize explicit Vietnamese ceilings; ambiguous prose still goes through a clarification turn."""
    text = fold(question)
    # "Tôi chỉ có 20 triệu thôi", "còn 15 triệu", "20 triệu trở xuống" state a ceiling too.
    pattern = (r"(?:khong qua|toi da|duoi|den|len|ngan sach(?: la)?|tam|khoang|re hon|thap hon|it hon"
               r"|\b(?:chi co|chi con|chi|co|con))\s*"
               rf"({_MONEY_NUMBER})\s*({_MONEY_UNIT})")
    suffix = rf"({_MONEY_NUMBER})\s*({_MONEY_UNIT})\s*(?:thoi|tro xuong|tro lai|do lai|la toi da|la max)\b"
    ceilings = [ceiling for _, ceiling in _budget_ranges(text)]
    ranges = list(_MONEY_RANGE.finditer(text))
    for match in [*re.finditer(pattern, text), *re.finditer(suffix, text)]:
        if any(band.start() <= match.start(1) < band.start(3) for band in ranges):
            continue  # "Khoảng 18 triệu đến 20 triệu": 18 is the lower bound, not another ceiling.
        number, unit = match.groups()
        amount = _budget_amount(number, unit, text[match.end():])
        if amount is not None:
            ceilings.append(amount)
    return min(ceilings) if ceilings else None


def budget_floor(question):
    text = fold(question)
    floors = [floor for floor, _ in _budget_ranges(text)]
    pattern = rf"(?:toi thieu|it nhat|tren)\s*({_MONEY_NUMBER})\s*({_MONEY_UNIT})"
    for match in re.finditer(pattern, text):
        amount = _budget_amount(*match.groups(), text[match.end():])
        if amount is not None:
            floors.append(amount)
    return max(floors) if floors else None


def budget_cleared(question):
    text = fold(question)
    return any(term in text for term in _CLEAR_BUDGET)


# --- Vocabulary and saved conversation state ---------------------------------------------------------------------

@dataclass(frozen=True)
class CategoryInfo:
    id: str
    name: str
    slug: str
    parent_id: str | None = None


@dataclass(frozen=True)
class BrandInfo:
    id: str
    name: str
    slug: str


@dataclass(frozen=True)
class Vocabulary:
    """Visible categories and brands of this turn (names only; no products)."""
    categories: tuple[CategoryInfo, ...] = ()
    brands: tuple[BrandInfo, ...] = ()

    def category(self, category_id):
        return next((c for c in self.categories if c.id == category_id), None)

    def brand(self, brand_id):
        return next((b for b in self.brands if b.id == brand_id), None)

    def root(self, category_id):
        category, seen = self.category(category_id), set()
        while category is not None and category.parent_id and category.id not in seen:
            seen.add(category.id)
            parent = self.category(category.parent_id)
            if parent is None:
                break
            category = parent
        return category

    def root_id(self, category_id):
        root = self.root(category_id)
        return root.id if root else category_id

    def kind(self, category_id):
        root = self.root(category_id)
        return product_type(root.name) if root else None


@dataclass(frozen=True)
class PastTurn:
    """One completed AI turn, as saved: the slots in force, the answer's intent and the products shown, in order."""
    slots: dict
    answer_intent: str | None = None
    references: tuple = ()


@dataclass(frozen=True)
class ConversationState:
    turns: tuple[PastTurn, ...] = ()

    def latest(self):
        return self.turns[-1] if self.turns else None

    def last_list(self):
        """The latest answer that showed products as a list (recommend/compare), for "máy thứ hai"."""
        for turn in reversed(self.turns):
            if turn.references and turn.answer_intent not in ABOUT_SHOWN and (
                    turn.answer_intent in (None, "recommend", "compare") or len(turn.references) > 1):
                return list(turn.references)
        return []

    def last_focus(self):
        """Products of the latest answer that showed any, for "máy này"/"máy vừa nói"."""
        for turn in reversed(self.turns):
            if turn.references:
                return list(turn.references)
        return []


def slots_from_constraints(constraints):
    """Slots for turns saved before AiIntent existed (only the applied hard constraints were kept)."""
    constraints = constraints or {}
    return {"CategoryId": constraints.get("category_id"), "MinBudget": constraints.get("min_price"),
            "MaxBudget": constraints.get("max_price"), "BrandId": constraints.get("brand_id"),
            "SoftBrandIds": [], "ExcludedBrandIds": list(constraints.get("excluded_brand_ids") or []),
            "Needs": [], "Rejected": [], "RejectedKeys": []}


# --- Phrase patterns (on folded text) ----------------------------------------------------------------------------

CATEGORY_ALIASES = {
    # Stage 10.7: models and customers often name categories in English ("phone", "tablet").
    "phone": "dien thoai", "phones": "dien thoai", "smartphone": "dien thoai", "smartphones": "dien thoai",
    "mobile": "dien thoai", "mobile phone": "dien thoai", "dt": "dien thoai", "dtdd": "dien thoai",
    "dien thoai di dong": "dien thoai",
    "tablet": "may tinh bang", "tablets": "may tinh bang",
    "laptops": "laptop", "notebook": "laptop", "may tinh xach tay": "laptop",
    "headphone": "tai nghe", "headphones": "tai nghe", "earphone": "tai nghe", "earphones": "tai nghe",
    "earbuds": "tai nghe", "headset": "tai nghe",
    "speaker": "loa", "speakers": "loa", "keyboard": "ban phim", "mouse": "chuot",
    "monitor": "man hinh", "power bank": "pin sac du phong", "powerbank": "pin sac du phong",
    "sac du phong": "pin sac du phong", "pin du phong": "pin sac du phong",
}
# Product families that imply a category when the question names none ("iPhone 17 giá bao nhiêu?").
FAMILY_HINTS = (
    (r"\biphone\b|\bgalaxy (?:s|a|z|m|note)\s*\d|\bgalaxy z\b|\bredmi note\b|\bpoco\b|\breno\s*\d|\bfind (?:x|n)\s*\d",
     "dien thoai"),
    (r"\bipad\b|\bgalaxy tab\b|\b(?:xiaomi|redmi) pad\b|\bmatepad\b", "may tinh bang"),
    (r"\bmacbook\b|\bthinkpad\b|\bthinkbook\b|\bideapad\b|\bvivobook\b|\bzenbook\b|\bvictus\b|\bpavilion\b"
     r"|\binspiron\b|\bvostro\b|\baspire\b|\bnitro\b|\blegion\b|\btuf\b|\brog\b", "laptop"),
    (r"\bairpods\b|\bgalaxy buds\b", "tai nghe"),
)
PRODUCT_FAMILY = re.compile("|".join(pattern for pattern, _ in FAMILY_HINTS))

# Words that make a named brand a preference, not a filter ("ưu tiên ASUS", "ASUS hoặc Lenovo").
SOFT_TERMS = ("uu tien", "cung duoc", "hoac", "khong bat buoc")
# A comparison names several products, so a single brand in it is not the customer's only brand.
COMPARE_TERMS = ("so sanh", "khac nhau", "khac gi", "nen chon", " hay ", " vs ")
# A requested order is kept as asked instead of being re-ranked.
EXPLICIT_ORDER = ("re nhat", "gia thap nhat", "gia tang dan", "gia giam dan", "dat nhat", "moi nhat")

_NOUN = r"(?:may|mau|san pham|sp|con|cai|chiec|em|lua chon|phuong an|option|dong|laptop|dien thoai)"
_ITEM = r"(?:may|mau|san pham|sp|con|cai|chiec|lua chon|phuong an|option)"
_ORDINAL_VALUES = {"nhat": 1, "dau tien": 1, "1": 1, "hai": 2, "2": 2, "ba": 3, "3": 3,
                   "tu": 4, "bon": 4, "4": 4, "nam": 5, "5": 5, "cuoi cung": -1, "cuoi": -1}
# "máy thứ hai", "mẫu số 2", "máy 2", "cái cuối"; not "laptop 2 trong 1" or "máy 2 sim".
_ORDINAL = re.compile(rf"\b{_NOUN}\s+(?:thu|so)\s+(nhat|hai|ba|tu|bon|nam|[1-5])\b"
                      rf"|\b{_ITEM}\s+(dau tien|cuoi cung|cuoi|[1-5])\b(?!\s*(?:sim|khe|nhan|camera|loa|gb|tb|trong))")
# A bare "thứ hai" counts only next to a full ordinal ("máy thứ nhất và thứ hai"); alone it can mean "firstly".
_BARE_ORDINAL = re.compile(r"\bthu\s+(nhat|hai|ba|tu|bon|nam)\b")
_FIRST_N = re.compile(rf"\b(hai|2|ba|3|bon|4|nam|5)\s+{_ITEM}\s+(?:dau|dau tien)\b")
_DEMONSTRATIVE = re.compile(rf"\b{_NOUN}\s+(?:nay|do|kia|tren|vua (?:roi|noi|nhac|tu van|goi y|de xuat|gioi thieu)"
                            r"|ban vua (?:noi|goi y|tu van))\b|\bvua (?:noi|nhac) (?:den|toi)\b")
_WHOLE_LIST = re.compile(rf"\b(?:(?:cac|nhung|may|ca|tat ca)\s+(?:\d\s+|hai\s+|ba\s+|bon\s+|nam\s+)?|(?:\d|hai|ba|bon|nam)\s+){_NOUN}\s+"
                         r"(?:tren|nay|do|vua (?:roi|noi|tu van|goi y|de xuat))\b"
                         r"|\btrong (?:so )?(?:do|nay|cac mau tren|[2-5] mau|hai mau|ba mau|bon mau|nam mau)\b")

_GREETING = re.compile(r"^(?:xin\s+)?(?:chao|hello|hi|hey|alo)\b|\bcam on\b|\bthank|\btam biet\b|\bbye\b")
_PROMO = re.compile(r"\b(?:khuyen mai|ma giam|giam gia|uu dai|coupon|voucher|ma uu dai|ma khuyen mai|flash sale"
                    r"|sale|dang giam)\b")
_COUPON_CODE = re.compile(r"(?:\b[mM][ãÃ]|\b[cC]ode)\s+[A-Z0-9]{4,}\b")
_REJECT = re.compile(rf"\b(?:khong\s+(?:thich|ung|muon|lay|chon|hop)|bo)\s+{_NOUN}\s+(?:nay|do|kia|thu|so|vua)\b")
_MORE = re.compile(
    r"\b(?:de xuat|goi y|gioi thieu|tu van|cho (?:toi|minh|em|tui)(?: xem)?|liet ke|show|xem)\s+(?:them|nua)\b"
    r"|\bthem\s+(?:\d+\s+|mot vai\s+|vai\s+|mot so\s+)?(?:mau|may|lua chon|san pham|option|phuong an|loai)\b"
    r"|\b(?:mau|may|lua chon|san pham|option|phuong an|loai|cai)\s+(?:nao\s+)?khac\b(?!\s+(?:nhau|gi|biet))"
    r"|\bcon\s+(?:mau|may|san pham|lua chon|cai|con|gi|loai)\s*(?:nao|gi)?\s*(?:khac|nua|khong|ko|k)\b"
    r"|\btuong tu\b|\bgiong (?:nhu|vay|the)\b")
_CHEAPER = re.compile(r"\b(?:re|mem|thap) hon\b|\bit tien hon\b|\bhop tui hon\b|\btiet kiem hon\b")
_BETTER_EXIST = re.compile(r"\bco\s+(?:may|mau|san pham|lua chon|cai|con|loai)\s+nao\b.*\bhon\b")
_COMPARE = re.compile(r"\bso sanh\b|\bkhac (?:nhau|gi|biet)\b|\bnen (?:chon|mua|lay)\s+(?:may|mau|cai|con|em)?\s*nao\b"
                      r"|\b(?:may|mau|cai|con|san pham|em)\s+nao\b.*\bhon\b|\bhay\b.*\bhon\b|\b(?:vs|versus)\b"
                      r"|\bhon kem\b|\bdoi dau\b")
_PRICE = re.compile(r"\bbao nhieu tien\b|\bmay tien\b|\bhet bao nhieu\b"
                    r"|\bgia\b(?!\s*(?:re|tot|mem|hop ly|phai chang|sinh vien|tam|duoi|tu)\b)")
_SPEC = re.compile(r"\b(?:pin|ram|rom|bo nho|dung luong|o cung|ssd|chip|chipset|cpu|gpu|card|vga|man hinh"
                   r"|tan so quet|camera|chong rung|ois|zoom|sac|trong luong|nang|kich thuoc|bao hanh|thong so"
                   r"|cau hinh|mau sac|cong ket noi|he dieu hanh|5g|nfc|sim|chong nuoc|khe)\b")
_WARRANTY_DURATION = re.compile(r"\b(?:bao lau|bao nhieu (?:thang|nam)|may (?:thang|nam)"
                                r"|thoi (?:han|gian) bao hanh|han bao hanh)\b")
_POLICY_DETAILS = re.compile(r"\b(?:chinh sach|thu tuc|dieu kien|quy trinh|pham vi|yeu cau|dang ky)\b")
_QUESTION = re.compile(r"\?|\b(?:bao nhieu|bao lau|bn|the nao|ra sao|nhu nao|la gi|loai gi|gi)\b"
                       r"|\bco\b.*\b(?:khong|ko|hong|k)\b")
_RECOMMEND = re.compile(r"\b(?:tu van|goi y|de xuat|gioi thieu|nen mua|muon mua|can mua|dinh mua|tim (?:giup|cho|mot)"
                        r"|chon (?:giup|cho)|muon (?:co|mot|1|chiec|cai|con)|can (?:mot|1|chiec|cai|con))\b"
                        r"|\bco\s+[a-z0-9 ]{0,30}?\bnao\b")
# "Tại sao bạn đề xuất những máy này?": the reasons for products already shown, not a new search.
_WHY = re.compile(r"\b(?:tai sao|vi sao|sao (?:lai|ban|minh)|ly do|can cu|co so nao"
                  r"|dua (?:vao|tren|theo) (?:dau|gi|tieu chi))\b|\blai (?:de xuat|goi y|chon|tu van|gioi thieu)\b")
_CHOSE = re.compile(r"\b(?:de xuat|goi y|chon|tu van|gioi thieu|xep|uu tien|phu hop|dung dau|recommend)\b")
# "Mô tả cụ thể từng máy", "Cho tôi biết thông tin cụ thể hơn 3 chiếc laptop", "Giới thiệu chi tiết máy thứ hai":
# details of products already shown, not a new search. Weak words count only with a reference to those products.
_DESCRIBE = re.compile(r"\b(?:mo ta|chi tiet|cu the|ky hon|ro hon|dac diem|uu nhuoc diem|uu diem|nhuoc diem"
                       r"|diem manh|diem yeu)\b|\b(?:noi|gioi thieu|tu van|biet|tim hieu) them ve\b")
_DESCRIBE_MORE = re.compile(r"\b(?:noi|gioi thieu|tu van|biet|tim hieu) them ve\b")  # Not "đề xuất thêm".
_ABOUT = re.compile(r"\b(?:gioi thieu|thong tin|thong so|cau hinh|review|danh gia)\b")
_LIST_REF = re.compile(rf"\btung\s+{_NOUN}\b|\b(?:\d|hai|ba)\s+(?:chiec|cai|con|mau|may|san pham)\b")
# A reply to the criteria question that leaves the choice to the advisor.
_ANY = re.compile(r"\btuy (?:ban|em|shop|minh|vao ban)\b|^tuy\b|\b(?:gi|nao|sao|the nao) cung (?:duoc|dc|ok)\b"
                  r"|\bkhong quan trong\b|\b(?:chua|khong) biet\b|\bcu (?:goi y|de xuat|tu van|chon)\b")
_CONTINUE = re.compile(r"^(?:the|vay|con|neu)\b|\bthi sao\b|\bthi the nao\b")
_ADDITIVE = re.compile(r"\b(?:nua|kem|kem theo|dong thoi|ngoai ra|va ca)\b|\bcung (?:phai|can|muon)\b")
_CLEAR_BRAND = re.compile(r"\bhang nao cung (?:duoc|dc)\b|\bkhong (?:can|quan trong) (?:dung |la )?hang\b"
                          r"|\bbat ky hang\b|\bhang gi cung\b|\bbo (?:loc )?hang\b|\bmoi hang\b")
_COUNT = re.compile(r"\b(\d{1,2}|mot|hai|ba|bon|nam)\s+(?:mau|may|lua chon|san pham|option|phuong an"
                    r"|laptop|dien thoai|may tinh bang|tablet)\b")
_COUNT_WORDS = {"mot": 1, "hai": 2, "ba": 3, "bon": 4, "nam": 5}
_MODEL_TOKEN = re.compile(r"\b[a-z]{1,8}\d{1,4}[a-z]{0,4}\b|\b\d{1,3}\s?(?:pro|plus|ultra|max|fe|lite|neo|air)\b")
_UNIT_TOKEN = re.compile(r"^\d+(?:gb|tb|mah|wh|w|hz|mp|k|tr|inch|g|kg)$")


@dataclass
class ShoppingIntent:
    """The backend's reading of one question, with conversation context applied."""
    intent: str = "general_chat"
    follow_up: bool = False
    category_id: str | None = None
    brand_id: str | None = None
    soft_brand_ids: tuple[str, ...] = ()
    excluded_brand_ids: tuple[str, ...] = ()
    min_budget: int | None = None
    max_budget: int | None = None
    needs: tuple[str, ...] = ()
    explicit: frozenset = frozenset()  # Slots the current question states: category, budget, brand, needs.
    inherited: tuple[str, ...] = ()
    category_changed: bool = False
    references: tuple[dict, ...] = ()  # Resolved [{Rank, ProductId, ProductVariantId, ProductName, ...}]
    clarification: str | None = None  # Set when a reference cannot be resolved: ask instead of guessing.
    excluded_product_ids: tuple[str, ...] = ()
    excluded_model_keys: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()
    rejected_keys: tuple[str, ...] = ()
    requested_count: int | None = None
    explicit_order: bool = False
    cheaper_than: int | None = None
    kind: str | None = None
    topics: tuple[str, ...] = ()  # policy_inquiry: promotion, warranty, returns.

    @property
    def recommending(self):
        return self.intent in RECOMMENDING

    def _applies(self, slot):
        """Inherited slots filter recommendations; a question about named products keeps only what it states."""
        return slot in self.explicit or (self.intent in RECOMMENDING or self.intent == "explain_recommendation" or (
            self.intent == "follow_up_question" and not self.references))

    def filters(self):
        """Hard constraints for search_products/get_product; same keys as the saved AiConstraints."""
        budget, brand = self._applies("budget"), self._applies("brand")
        return {"min_price": self.min_budget if budget else None, "max_price": self.max_budget if budget else None,
                "brand_id": self.brand_id if brand else None,
                "category_id": self.category_id if self._applies("category") else None,
                "excluded_brand_ids": sorted(self.excluded_brand_ids) if brand else []}

    def soft_brands(self):
        return frozenset(self.soft_brand_ids) if not self.brand_id else frozenset()

    def hard_constraints(self, vocab):
        filters = self.filters()
        return {"Category": _name(vocab.category(filters["category_id"])), "MinBudget": filters["min_price"],
                "MaxBudget": filters["max_price"], "Brand": _name(vocab.brand(filters["brand_id"])),
                "ExcludedBrands": [_name(vocab.brand(id_)) for id_ in filters["excluded_brand_ids"]],
                "ExcludedProducts": len(self.excluded_product_ids), "InStockOnly": True}

    def soft_preferences(self, vocab):
        return {"UsageNeeds": [NEEDS[need].label for need in self.needs],
                "PreferredBrands": [_name(vocab.brand(id_)) for id_ in self.soft_brands()],
                "Priorities": priorities(self.needs, self.kind)}

    def to_metadata(self):
        """Saved with the question (internal Metadata, never returned to the customer)."""
        return {
            "Intent": self.intent, "FollowUp": self.follow_up, "CategoryChanged": self.category_changed,
            "Inherited": list(self.inherited), "References": [ref["ProductId"] for ref in self.references],
            "ExcludedProductIds": list(self.excluded_product_ids),
            **({"Topics": list(self.topics)} if self.topics else {}),
            "Slots": {"CategoryId": self.category_id, "MinBudget": self.min_budget, "MaxBudget": self.max_budget,
                      "BrandId": self.brand_id, "SoftBrandIds": list(self.soft_brand_ids),
                      "ExcludedBrandIds": list(self.excluded_brand_ids), "Needs": list(self.needs),
                      "Rejected": list(self.rejected), "RejectedKeys": list(self.rejected_keys),
                      **({"RequestedCount": self.requested_count} if self.requested_count else {})},
        }

    def model_note(self, vocab):
        """What Gemini is told about this turn: names and numbers from the backend, never raw customer text."""
        hard, soft = self.hard_constraints(vocab), self.soft_preferences(vocab)
        note = {"intent": self.intent, "follow_up": self.follow_up, "category": hard["Category"],
                "budget_min": hard["MinBudget"], "budget_max": hard["MaxBudget"],
                "brand_required": hard["Brand"], "brands_excluded": hard["ExcludedBrands"],
                "brands_preferred": soft["PreferredBrands"], "usage_needs": soft["UsageNeeds"],
                "priorities": soft["Priorities"], "inherited": list(self.inherited)}
        if self.category_changed:
            note["category_changed"] = True
        if self.excluded_product_ids:
            note["already_shown_excluded"] = len(self.excluded_product_ids)
        if self.requested_count:
            note["requested_count"] = self.requested_count
        if self.cheaper_than:
            note["cheaper_than"] = self.cheaper_than
        if self.explicit_order:
            note["explicit_order"] = True
        if self.references:
            note["references"] = [{"rank": ref.get("Rank"), "product_id": ref["ProductId"],
                                   "name": ref.get("ProductName")} for ref in self.references]
        if self.topics:
            note["topics"] = list(self.topics)
        return {key: value for key, value in note.items() if value not in (None, [], ())}


def _name(row):
    return row.name if row else None


def _ranks(text):
    found = [(match.start(), _ORDINAL_VALUES[match[1] or match[2]]) for match in _ORDINAL.finditer(text)]
    if found:
        found += [(match.start(), _ORDINAL_VALUES[match[1]]) for match in _BARE_ORDINAL.finditer(text)]
    for match in _FIRST_N.finditer(text):
        count = _ORDINAL_VALUES[match[1]]
        found += [(match.start() + rank, rank) for rank in range(1, count + 1)]
    return list(dict.fromkeys(rank for _, rank in sorted(found)))


def _describe(references):
    return "; ".join(f"{ref.get('Rank', i)}. {ref['ProductName']}" if ref.get("ProductName") else f"mẫu {ref.get('Rank', i)}"
                     for i, ref in enumerate(references, 1))


def _resolve(text, state, intent_hint):
    """(references, clarification) for ordinals, "máy này" and "các mẫu trên"; never guesses."""
    ranks = _ranks(text)
    listed, focus = state.last_list(), state.last_focus()
    if ranks:
        if not listed:
            return (), "Mình chưa tư vấn mẫu nào trong cuộc trò chuyện này. Bạn muốn hỏi sản phẩm nào?"
        resolved = []
        for rank in ranks:
            ref = listed[-1] if rank == -1 else next((r for r in listed if r.get("Rank") == rank), None)
            if ref is None:
                return (), (f"Danh sách vừa rồi chỉ có {len(listed)} mẫu: {_describe(listed)}. "
                            "Bạn muốn hỏi mẫu nào?")
            if ref not in resolved:
                resolved.append(ref)
        return tuple(resolved), None
    if _WHOLE_LIST.search(text):
        return (tuple(listed), None) if listed else ((), "Bạn đang hỏi về những mẫu nào? Bạn cho mình biết tên sản phẩm nhé.")
    if _DEMONSTRATIVE.search(text):
        if len(focus) == 1:
            return tuple(focus), None
        if focus and intent_hint == "compare":
            return tuple(focus), None
        if focus:
            return (), f"Bạn đang hỏi mẫu nào trong số: {_describe(focus)}?"
        return (), "Bạn đang hỏi về mẫu nào? Bạn cho mình biết tên sản phẩm nhé."
    return (), None


# Curated child categories that describe a need or a price/size segment of phones, laptops and tablets rather than a
# product form. Each product has one primary child, so such a child used as a hard filter would drop suitable products
# filed under a sibling ("Laptop văn phòng" vs "Laptop học tập"). They filter by their root; the need is scored.
# Form/feature children ("Laptop 2 trong 1", "Điện thoại màn hình gập", headphone types) stay hard filters.
SEGMENT_TERMS = ("pin trau", "choi game", "gaming", "chup anh", "mong nhe", "nho gon", "pho thong", "tam trung",
                 "cao cap", "man hinh lon", "hoc tap", "van phong", "do hoa", "lap trinh", "sang tao", "giai tri")


def soften_category(category, vocab):
    if category is not None and category.parent_id and product_type((vocab.root(category.id) or category).name) and any(
            term in fold(category.name) for term in SEGMENT_TERMS):
        return vocab.root(category.id) or category
    return category


def _categories(text, vocab):
    """Explicit category (longest name wins), else an English/Vietnamese alias, else a product-family hint."""
    text = re.sub(r"\bso dien thoai\b", " ", text)  # "số điện thoại" is a phone number, not the category.
    by_name = {fold(c.name): c for c in vocab.categories}
    # A slug that is also a brand ("samsung" on "Điện thoại pin trâu" in the VieTech catalog) is not a category word.
    brand_words = {fold(b.name) for b in vocab.brands} | {fold(b.slug.replace("-", " ")) for b in vocab.brands}
    mentioned = [c for c in vocab.categories if any(re.search(r"\b" + re.escape(name) + r"\b", text)
                 for name in (fold(c.name), fold(c.slug.replace("-", " ")))
                 if len(name) >= 3 and (name == fold(c.name) or name not in brand_words))]
    category = max(mentioned, key=lambda c: len(fold(c.name)), default=None)
    if category is None:
        target = next((name for alias, name in sorted(CATEGORY_ALIASES.items(), key=lambda item: -len(item[0]))
                       if re.search(r"\b" + re.escape(alias) + r"\b", text)), None)
        category = by_name.get(target) if target else None
    hinted = False
    if category is None:
        target = next((name for pattern, name in FAMILY_HINTS if re.search(pattern, text)), None)
        category, hinted = by_name.get(target) if target else None, True
    # "Điện thoại pin trâu" names a need, not a product type: filter by the root, score the need softly.
    return soften_category(category, vocab), hinted


def _brands(text, vocab):
    mentioned = [b for b in vocab.brands if re.search(r"\b" + re.escape(fold(b.name)) + r"\b", text)]
    excluded = [b for b in mentioned if re.search(
        r"(?:khong(?: (?:muon|chon|mua|thich|phai(?: la)?|lay|dung))?|tru|ngoai) (?:hang )?" + re.escape(fold(b.name)),
        text)]
    explicit = [b for b in mentioned if b not in excluded and re.search(
        r"(?<!khong )(?:chi|nhat dinh|bat buoc|phai la) (?:hang )?" + re.escape(fold(b.name)), text)]
    return mentioned, excluded, explicit


def _names_product(text, mentioned_brands):
    tokens = [token for token in _MODEL_TOKEN.findall(text) if not _UNIT_TOKEN.match(token.replace(" ", ""))]
    return bool(PRODUCT_FAMILY.search(text) or (mentioned_brands and tokens))


def _classify(text, *, promo, refs, listed, needs, category, budget, brands, named, previous, describe=False):
    policy = bool(POLICY_TERMS.search(text))
    if _GREETING.search(text) and not (category or needs or budget or brands or refs or promo or policy):
        return "general_chat"
    if describe and _DESCRIBE_MORE.search(text):
        return "product_description"  # "Giới thiệu thêm về máy thứ hai" asks about it, not for more products.
    if _WHY.search(text) and _CHOSE.search(text) and (refs or listed):
        return "explain_recommendation"
    if RETURN_TERMS.search(text) and budget is None and not _RECOMMEND.search(text):
        return "policy_inquiry"  # Exchange/return conditions are not product specifications.
    if policy and not (named or budget is not None or needs or _RECOMMEND.search(text)):
        # "Bảo hành của 2 sản phẩm trên" needs the policy as well as those products' warranty months.
        # Keep a duration-only question, or one also asking other specs, in product_information.
        other_specs = _SPEC.search(POLICY_TERMS.sub(" ", text))
        duration_only = _WARRANTY_DURATION.search(text) and not _POLICY_DETAILS.search(text)
        if not refs or not (other_specs or duration_only):
            return "policy_inquiry"
    if promo:
        return "promotion_inquiry"
    if _REJECT.search(text) or _MORE.search(text):
        return "recommend_more"
    if _CHEAPER.search(text):
        return "product_recommendation"
    if _BETTER_EXIST.search(text) and listed:
        return "recommend_more"
    if _COMPARE.search(text) and (refs or listed or named or "so sanh" in text):
        return "product_comparison"
    if describe:
        return "product_description"
    asks = bool(_QUESTION.search(text))
    if _PRICE.search(text) and (refs or named or not (category or needs)):
        return "price_inquiry"
    if _SPEC.search(text) and asks and (refs or named) and not _RECOMMEND.search(text):
        return "product_information"
    if named and asks and not (needs or budget is not None) and not _RECOMMEND.search(text):
        return "product_information"  # "Có iPhone 16 Plus không?": availability of a named model.
    if _RECOMMEND.search(text) or category or needs or budget is not None or brands:
        return "product_recommendation"
    if refs:
        return "product_information" if _SPEC.search(text) else "follow_up_question"
    if previous and _CONTINUE.search(text):
        return "follow_up_question"
    return "general_chat"


def analyze(question, vocab: Vocabulary, state: ConversationState = ConversationState()):
    text = fold(question)
    previous = state.latest()
    prev = dict(previous.slots) if previous else {}
    needs_now = detect_needs(question)
    category, hinted = _categories(text, vocab)
    mentioned, excluded, explicit_brands = _brands(text, vocab)
    ceiling, floor, cleared = budget_ceiling(question), budget_floor(question), budget_cleared(question)
    named = _names_product(text, mentioned)
    compare_hint = "compare" if _COMPARE.search(text) else None
    refs, clarification = _resolve(text, state, compare_hint)
    listed = state.last_list()
    promo = bool(_PROMO.search(text) or _COUPON_CODE.search(question))  # Codes are matched before folding.
    # A changed or cleared budget refines the search even when the question also names "máy thứ nhất".
    budget_signal = ceiling if ceiling is not None else floor if floor is not None else (0 if cleared else None)
    shown = listed or state.last_focus()
    same_root = category is None or vocab.root_id(category.id) == vocab.root_id(prev.get("CategoryId"))
    describe = bool(shown) and same_root and not (named or needs_now or budget_signal is not None) and bool(
        _DESCRIBE.search(text) or (_ABOUT.search(text) and (refs or clarification or _LIST_REF.search(text))))
    intent = _classify(text, promo=promo, refs=refs or bool(clarification), listed=listed, needs=needs_now,
                       category=category and not hinted, budget=budget_signal,
                       brands=mentioned, named=named, previous=bool(previous), describe=describe)
    asked = bool(previous) and previous.answer_intent == "clarify"
    if intent == "general_chat" and asked and prev.get("CategoryId") and _ANY.search(text):
        intent = "product_recommendation"  # "Tùy bạn" after the criteria question: advise on the balanced profile.
    if intent == "product_comparison" and not refs and not named and listed and not clarification:
        refs = tuple(listed)  # "Máy nào pin tốt hơn?" compares the list just shown.
    if intent == "explain_recommendation" and (not refs or clarification) and not _ranks(text):
        refs, clarification = tuple(listed), None  # "Tại sao lại chọn máy này?" after a list: explain the list.
    if intent == "product_description" and not refs and not clarification:
        # "Từng máy"/"3 chiếc" is the list; "Mô tả chi tiết hơn" is what the latest answer was about.
        refs = tuple(listed if listed and _LIST_REF.search(text) else state.last_focus() or listed)
    if (intent == "promotion_inquiry" and not refs and not clarification and not (category or named or mentioned)
            and re.search(r"\b(?:san pham|sp|may|mau)\b", text)):
        # "Khuyến mãi sản phẩm như nào" after a recommendation is about those products.
        refs = tuple(state.last_focus() or listed)
    if intent in RECOMMENDING and clarification and not _REJECT.search(text):
        clarification = None  # "Còn mẫu khác không?" needs no target; only a rejection does.

    result = ShoppingIntent(intent=intent, references=refs, clarification=clarification,
                            explicit_order=any(term in text for term in EXPLICIT_ORDER),
                            topics=policy_topics(text, promo=promo) if intent == "policy_inquiry" else ())
    explicit, inherited = set(), []

    # Category and need group.
    prev_category = prev.get("CategoryId")
    if category is not None:
        result.category_id = category.id
        explicit.add("category")
    elif prev_category:
        result.category_id = prev_category  # Small talk carries it too, for the next shopping question.
        inherited.append("category")
    same_group = bool(previous) and (category is None or vocab.root_id(category.id) == vocab.root_id(prev_category))
    result.category_changed = bool(prev_category and category is not None and not same_group)
    if intent in ("general_chat", "policy_inquiry") and previous:
        same_group = True  # Small talk and policy questions keep everything for the next shopping question.

    # Budget: a new range replaces the old one.
    if ceiling is not None or floor is not None:
        result.min_budget, result.max_budget = floor, ceiling
        explicit.add("budget")
    elif cleared:
        explicit.add("budget")
    elif same_group and (prev.get("MinBudget") is not None or prev.get("MaxBudget") is not None):
        result.min_budget, result.max_budget = prev.get("MinBudget"), prev.get("MaxBudget")
        inherited.append("budget")

    # Brands: a named brand replaces the old one; exclusions stay until the brand is named again.
    prev_excluded = set(prev.get("ExcludedBrandIds") or []) if same_group else set()
    comparing = any(term in f" {text} " for term in COMPARE_TERMS)
    soft = any(term in text for term in SOFT_TERMS)
    if _CLEAR_BRAND.search(text):
        explicit.add("brand")
    elif mentioned or excluded:
        explicit.add("brand")
        strict = explicit_brands[0] if len(explicit_brands) == 1 else (
            mentioned[0] if len(mentioned) == 1 and not soft and not excluded and not comparing else None)
        result.brand_id = strict.id if strict else None
        # Brands named in a comparison are its subjects, not preferences for later recommendations.
        result.soft_brand_ids = () if strict or comparing else tuple(b.id for b in mentioned if b not in excluded)
        named_again = {b.id for b in mentioned if b not in excluded}
        result.excluded_brand_ids = tuple(sorted((prev_excluded - named_again) | {b.id for b in excluded}))
    elif same_group and (prev.get("BrandId") or prev.get("SoftBrandIds") or prev_excluded):
        result.brand_id = prev.get("BrandId")
        result.soft_brand_ids = tuple(prev.get("SoftBrandIds") or ())
        result.excluded_brand_ids = tuple(sorted(prev_excluded))
        inherited.append("brand")

    # Needs: restated needs replace the old ones unless the customer adds to them ("… nữa", "kèm …").
    prev_needs = tuple(prev.get("Needs") or ()) if same_group else ()
    if needs_now:
        explicit.add("needs")
        result.needs = tuple(dict.fromkeys(prev_needs + needs_now)) if prev_needs and _ADDITIVE.search(text) else needs_now
    elif prev_needs:
        result.needs = prev_needs
        inherited.append("needs")

    # Rejected and already shown products, by ProductId and canonical model name.
    rejected = list(prev.get("Rejected") or []) if same_group else []
    rejected_keys = list(prev.get("RejectedKeys") or []) if same_group else []
    if _REJECT.search(text) and refs:
        rejected += [ref["ProductId"] for ref in refs if ref["ProductId"] not in rejected]
        rejected_keys += [ref["ModelKey"] for ref in refs if ref.get("ModelKey") and ref["ModelKey"] not in rejected_keys]
    result.rejected, result.rejected_keys = tuple(rejected), tuple(rejected_keys)
    excluded_ids, excluded_keys = list(rejected), list(rejected_keys)
    if intent == "recommend_more":
        root = vocab.root_id(result.category_id)
        for turn in reversed(state.turns):
            if vocab.root_id(turn.slots.get("CategoryId")) != root:
                break  # Only the current need group: an older group's products may be shown again.
            for ref in turn.references:
                if ref["ProductId"] not in excluded_ids:
                    excluded_ids.append(ref["ProductId"])
                key = ref.get("ModelKey") or (model_key(ref["ProductName"]) if ref.get("ProductName") else None)
                if key and key not in excluded_keys:
                    excluded_keys.append(key)
    if intent in RECOMMENDING:
        result.excluded_product_ids, result.excluded_model_keys = tuple(excluded_ids), tuple(excluded_keys)

    # "Có mẫu nào rẻ hơn?": below the cheapest product referenced or just shown.
    if _CHEAPER.search(text) and ceiling is None:
        prices = [Decimal(str(ref["Price"])) for ref in (refs or listed or state.last_focus()) if ref.get("Price")]
        if prices:
            result.max_budget, result.min_budget = int(min(prices)) - 1, None
            result.cheaper_than = int(min(prices))
            explicit.add("budget")

    count = _COUNT.search(text)
    if count and intent in RECOMMENDING:
        value = count[1]
        result.requested_count = min(5, int(value) if value.isdigit() else _COUNT_WORDS[value])
    elif intent in RECOMMENDING and asked and (same_group or not prev_category):
        result.requested_count = prev.get("RequestedCount")
    result.explicit, result.inherited = frozenset(explicit), tuple(inherited)
    result.follow_up = bool(previous) and bool(inherited or refs or intent in ("recommend_more", "follow_up_question")
                                               or result.cheaper_than)
    result.kind = vocab.kind(result.category_id)
    # "Tôi muốn mua 1 chiếc điện thoại": no budget, need, brand or order yet, so ask before recommending. Asked once:
    # whatever the next reply leaves open is advised on the balanced profile instead of asking again.
    criteria = (result.min_budget is not None or result.max_budget is not None or "budget" in result.explicit
                or result.needs or result.brand_id or result.soft_brand_ids or result.excluded_brand_ids
                or result.explicit_order or result.cheaper_than or named)
    if intent == "product_recommendation" and not (refs or clarification or criteria or asked):
        result.clarification = criteria_question(vocab.category(result.category_id), result.kind)
    return result


# Uses offered per product type; the phrases are ones detect_needs recognizes, so the reply fills the needs slot.
USAGE_EXAMPLES = {
    "phone": ("dưới 5 triệu, 5–10 triệu hay trên 15 triệu", "chơi game, chụp ảnh đẹp, pin trâu hay chỉ cần máy ngon "
              "trong tầm giá"),
    "laptop": ("dưới 15 triệu, 15–25 triệu hay trên 30 triệu", "học tập/văn phòng, lập trình, đồ họa/dựng video, chơi "
               "game hay cần mỏng nhẹ để mang theo"),
    "tablet": ("dưới 8 triệu, 8–15 triệu hay cao hơn", "học tập, chơi game, pin trâu hay chỉ cần máy ngon trong tầm giá"),
}


def criteria_question(category, kind):
    """The backend's own question when a shopping request has no criteria; no model call is needed for it."""
    if category is None:
        return ("Bạn muốn tìm điện thoại, laptop hay sản phẩm nào khác? Cho mình biết thêm ngân sách và nhu cầu "
                "sử dụng nhé, để mình tư vấn cho sát nhu cầu.")
    name = category.name[:1].lower() + category.name[1:]
    budget, usage = USAGE_EXAMPLES.get(kind, ("", ""))
    lines = [f"Để tư vấn {name} phù hợp với bạn, bạn cho mình biết thêm nhé:",
             f"- Ngân sách khoảng bao nhiêu{f' (ví dụ {budget})' if budget else ''}?",
             f"- Bạn dùng chủ yếu cho việc gì{f': {usage}' if usage else ''}?",
             "- Bạn có thích hãng nào không (không bắt buộc)?"]
    return "\n\n".join((lines[0], "\n".join(lines[1:])))
