"""Read-only catalog tools and server-rendered facts; no ORM/admin objects leave this boundary."""

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.core.search_text import fold
from app.schemas.ai_chat import (GetProductArguments, ListOffersArguments, PresentAnswerArguments,
                                  SearchProductsArguments)

from .ai_grounding import Facts, ProductFacts, check_message
from .ai_customer_wording import customer_notes, customer_text
from .ai_comparison import build_comparison, closest_products, colour_only_default, normalized_specs, spec_signature
from .ai_compatibility import AiCompatibility
from .ai_product_requirements import feature_evidence, meets_features
from .ai_policy import (PROMOTION_LINE, PROMOTION_USAGE_LINES, policy_text, promotion_usage,
                        requested_coupon, return_lines, return_message_issue, warranty_lines, warranty_message_issue)
from .ai_intent import (CATEGORY_ALIASES, BrandInfo, CategoryInfo, ConversationState, ShoppingIntent, Vocabulary,
                        analyze, budget_ceiling, budget_floor, soften_category)  # noqa: F401 (budget_* stay importable here)
from .catalog import BrandService, CategoryService, ProductService
from .exceptions import AiUnavailableError, BusinessRuleError, NotFoundError
from .pricing import PricingService
from .recommendation import (CANDIDATE_MAX, CANDIDATE_PAGE, NEEDS, RESULT_LIMIT, Candidate, RankingCriteria,
                             detect_needs, model_key, priorities, rank)
from .warranty_period import VIETNAM_TZ

TOOL_SCHEMAS = {
    "search_products": (SearchProductsArguments, "Tìm sản phẩm đang bán và còn hàng. Tách hãng, danh mục và giá thành trường riêng; keyword chỉ chứa tên/model, không đưa nhu cầu/ngân sách vào keyword. category/brand nhận tên hoặc slug công khai. Backend tự áp điều kiện của khách (kể cả điều kiện kế thừa từ lượt trước) và tự loại sản phẩm đã giới thiệu khi khách xin thêm lựa chọn. Khi Ranked=true, Ranking.Rank 1 phù hợp nhất theo nhu cầu, ngân sách và hãng ưu tiên; Matched/Gaps là bằng chứng từ thông số."),
    "get_product": (GetProductArguments, "Đọc sản phẩm và thông số hiện tại theo product_id/slug, product_ids (2–5 sản phẩm cần so sánh, đọc trong một lần gọi), hoặc rank = thứ tự trong danh sách đã tư vấn gần nhất (chưa có danh sách thì là thứ tự trong kết quả search_products gần nhất). Không cần gọi nếu sản phẩm đã có trong dữ liệu tham chiếu của lượt này."),
    "list_offers": (ListOffersArguments, "Đọc mã giảm giá còn hiệu lực đúng sản phẩm/danh mục khách hỏi. Với sản phẩm, chỉ trả mã đủ mức chi tiêu theo giá sau giảm tự động của phiên bản đang xem; ưu tiên mã tiết kiệm nhiều nhất. Không giới thiệu mã của danh mục khác hoặc yêu cầu mua thêm để đủ mức tối thiểu."),
    "present_answer": (PresentAnswerArguments, "Kết thúc lượt. intent và products (product_id, product_variant_id, specification_keys tùy chọn) phải là sản phẩm có thật trong dữ liệu lượt này; backend dựng tối đa năm thẻ với giá/tồn kho hiện tại. message là câu trả lời tự nhiên bằng tiếng Việt cho khách: chỉ dùng số liệu có trong dữ liệu lượt này, nêu sản phẩm theo đúng thứ tự products. Hỏi thêm bằng intent=clarify; trò chuyện chung dùng intent=chat; chính sách bảo hành/đổi trả/khuyến mãi dùng intent=policy; giải thích vì sao đã đề xuất các mẫu dùng intent=explain; trạng thái một đơn hàng/thanh toán cụ thể dùng handoff."),
}

# An order the customer asks for ("mới nhất") is used by the backend's own first search; ranking is then skipped.
PREFETCH_SORTS = ((("moi nhat", "moi ra mat"), "newest"), (("gia giam dan", "dat nhat"), "price_desc"))

# Usage phrases are preferences, never mandatory words in a product's name.
USAGE_KEYWORDS = {"hoc lap trinh", "lap trinh", "hoc tap", "van phong", "choi game", "pin tot", "pin trau",
                  "chup anh dep", "chup anh", "mong nhe", "gaming", "sinh vien"}

# Single words of specification keys that are too common in questions to mean that key ("trong", "nhỏ", "dùng").
KEY_STOPWORDS = {"dung", "luong", "loai", "cong", "nghe", "tinh", "nang", "thoi", "diem", "trong", "sau", "truoc",
                 "khi", "mat", "tro", "phan", "giai", "kich", "thuoc", "nho", "mang", "the", "toi"}

CLARIFY = {"category": "Bạn đang muốn tìm loại sản phẩm nào (điện thoại, laptop, máy tính bảng, phụ kiện…)?",
           "budget": "Ngân sách tối đa của bạn khoảng bao nhiêu để mình lọc đúng tầm giá?",
           "usage": "Bạn dùng máy chủ yếu cho việc gì (học tập, làm việc, chơi game, chụp ảnh…)?",
           "brand": "Bạn có muốn chọn một hãng cụ thể không?",
           "products": "Bạn muốn so sánh hoặc hỏi về những mẫu nào?"}
HANDOFF = ("Trợ lý AI hỗ trợ tư vấn sản phẩm, ưu đãi và chính sách chung. Với tình trạng một đơn hàng, thanh toán hay "
           "yêu cầu bảo hành/đổi trả cụ thể, bạn vui lòng xem trong tài khoản hoặc chat với nhân viên VieTech.")
ORDER_ACTION = ("Mình là trợ lý tư vấn nên không thể đặt hàng hay thanh toán thay bạn. Bạn mở trang sản phẩm, chọn "
                "phiên bản, bấm \"Thêm vào giỏ hàng\" rồi đặt hàng và thanh toán từ giỏ hàng nhé. Để an toàn, bạn đừng "
                "gửi số thẻ hay mã OTP trong khung chat. Nếu cần chọn mẫu, mình có thể tư vấn giúp bạn.")
CHAT = ("Mình là trợ lý tư vấn sản phẩm của VieTech. Bạn đang cần tìm điện thoại, laptop hay phụ kiện nào, "
        "và ngân sách khoảng bao nhiêu? Bạn nói thêm nhu cầu sử dụng để mình tư vấn nhé.")
COMPARISON_GUIDANCE = ("Mình vẫn so sánh được các mục có thông số rõ ràng. Riêng mục bị thiếu sẽ ghi “Chưa rõ”, "
                      "không tự đoán hoặc kết luận mẫu nào hơn ở mục đó.")


def tool_definitions(*, final_only=False):
    """final_only: the last allowed round offers only present_answer, so the turn ends instead of hitting the limit."""
    return [{"type": "function", "function": {"name": name, "description": description,
             "parameters": schema.model_json_schema()}}
            for name, (schema, description) in TOOL_SCHEMAS.items() if not final_only or name == "present_answer"]


@dataclass
class GroundingContext:
    question: str
    state: ConversationState = field(default_factory=ConversationState)
    intent: ShoppingIntent | None = None
    vocab: Vocabulary = field(default_factory=Vocabulary)
    references: list[dict] = field(default_factory=list)  # The latest product list shown, for get_product(rank).
    products: dict[str, dict] = field(default_factory=dict)  # Public facts read this turn, by ProductId.
    filters: dict[str, dict] = field(default_factory=dict)
    searched: bool = False
    offer_scopes: list[str | None] = field(default_factory=list)
    offers: list[dict] = field(default_factory=list)
    constraints: dict = field(default_factory=dict)
    ranking: RankingCriteria = field(default_factory=RankingCriteria)
    dropped: frozenset | None = None  # Criteria the latest ranked search dropped as uninformative.
    ranking_log: dict | None = None
    # Stage 10.7: models read get_product(rank) as the position in this turn's search; kept for that fallback.
    search_order: list[str] = field(default_factory=list)
    hidden: int = 0  # Eligible products the latest search left out because they were already shown or rejected.
    prefetched: dict | None = None  # search_products result the backend ran before the first model round.
    referenced: list[dict] = field(default_factory=list)  # Facts of the products the question refers to.
    nearest: dict | None = None  # Cheapest product just above the ceiling when a search found nothing within it.
    policy: dict | None = None  # Store policy lines by topic (Warranty/Returns/Promotion) read for this turn.
    explained: dict = field(default_factory=dict)  # explain_recommendation: Evaluation per shown ProductId.
    comparison: dict | None = None  # Verified Smart Compare snapshot; set once the 2–3 exact SKUs are resolved.
    compatibility: dict | None = None
    compatibility_options: list[dict] = field(default_factory=list)
    compatibility_fallback: bool = False


def money(value):
    amount = Decimal(str(value))
    result = f"{amount:,.0f}" if amount == amount.to_integral_value() else f"{amount:,.2f}"
    return result.replace(",", "_").replace(".", ",").replace("_", ".") + " đ"


# "So sánh camera, pin và hiệu năng của …": these are criteria, not product names.
_ASPECT = (r"(?:camera|pin|man hinh|hieu nang|cau hinh|thong so|gia ban|gia|thiet ke|am thanh|chip|cpu|gpu"
           r"|ram|ssd|rom|o cung|bo nho|sac|toc do sac|trong luong|kich thuoc)")
_ASPECT_OF = re.compile(rf"{_ASPECT}(?:\s*(?:[,;]|\bva\b)\s*{_ASPECT})*\s+(?:cua|giua)\s+")


def _strip_aspect(query):
    typed = unicodedata.normalize("NFC", query)
    folded = fold(typed)
    match = _ASPECT_OF.match(folded)
    return typed[match.end():] if match and len(folded) == len(typed) else query


def _mentions_variant(value, question):
    tokens = re.findall(r"[a-z]+|\d+", fold(value or ""))
    return bool(tokens and re.search(r"(?<![a-z0-9])" + r"[^a-z0-9]*".join(map(re.escape, tokens))
                                     + r"(?![a-z0-9])", fold(question)))


def public_specifications(specifications, limit=12):
    """Bounded flattening of public technical data; preserves values instead of inferring specs."""
    result = {}
    visited = 0

    def collect(data, prefix="", depth=0):
        nonlocal visited
        if not isinstance(data, dict) or depth > 3:
            return
        for key, value in data.items():
            visited += 1
            if len(result) >= limit or visited > 100:
                return
            label = f"{prefix} / {key}" if prefix else str(key)
            if len(label) > 60:
                continue
            if isinstance(value, dict):
                collect(value, label, depth + 1)
            elif isinstance(value, (str, int, float, bool)):
                result[label] = str(value)[:160]
            elif isinstance(value, list) and all(isinstance(v, (str, int, float, bool)) for v in value):
                result[label] = ", ".join(str(v) for v in value[:8])[:160]
    collect(specifications or {})
    return result


# A description leads with what tells products apart; other keys keep the catalog order.
KEY_SPECS = ("chip", "cpu", "ram", "o cung", "bo nho", "card", "man hinh", "tan so", "pin", "sac", "camera",
             "trong luong", "he dieu hanh")
DESCRIBED_SPECS = 20  # Specifications read for a description (12 for other reads); 8 are listed in the fallback text.


def _price(variant):
    return variant.SalePrice if variant.SalePrice is not None else variant.Price


def _gigabytes(value):
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(tb|gb)\b", fold(value or ""))
    return float(match[1].replace(",", ".")) * (1024 if match[2] == "tb" else 1) if match else None


def _has_memory(detail, variant, filters):
    """The SKU's own RAM/storage (as Smart Compare reads it) meets the stated minimums. A capacity the catalog does
    not state cannot be confirmed, so it does not pass a hard filter."""
    wanted = {"ram": filters.get("min_ram_gb"), "storage": filters.get("min_storage_gb")}
    if not any(wanted.values()):
        return True
    specs = normalized_specs(detail.Specifications, variant, None)
    return all((size := _gigabytes(specs.get(key))) is not None and size >= minimum
               for key, minimum in wanted.items() if minimum)


class AiTools:
    """Called inside the orchestrator's short authorized transaction; never commits or calls the model."""

    def __init__(self, session, *, clock, ranking=True, actor=None):
        self.catalog = ProductService(session, clock=clock)
        self.categories = CategoryService(session, clock=clock)
        self.brands = BrandService(session, clock=clock)
        self.pricing = PricingService(session, clock=clock)
        self.clock = clock
        self.actor = actor
        self.ranking = ranking  # False = baseline catalog order, for the stage 10.7 comparison.

    # --- Turn preparation ----------------------------------------------------------------------------------------

    def vocabulary(self):
        return Vocabulary(
            tuple(CategoryInfo(str(c.CategoryId), c.Name, c.Slug, str(c.ParentCategoryId) if c.ParentCategoryId else None)
                  for c in self.categories.list_categories(active_only=True)),
            tuple(BrandInfo(str(b.BrandId), b.Name, b.Slug) for b in self.brands.list_brands(active_only=True)))

    def prepare(self, context):
        """Read the question with its context, then fetch what the answer will obviously need, before the model runs:
        the referenced products for "máy thứ hai", and the ranked search for a recommendation in a known category."""
        context.vocab = self.vocabulary()
        context.intent = analyze(context.question, context.vocab, context.state)
        context.references = context.state.last_list()
        context.constraints = context.intent.filters()
        context.ranking = RankingCriteria(context.intent.needs, context.intent.soft_brands())
        if context.intent.intent == "comparison_guidance":
            return
        if context.intent.intent == "product_compatibility":
            AiCompatibility(self.catalog, context, clock=self.clock, variant_match=_mentions_variant).prepare()
            return
        if context.intent.clarification:
            return
        try:
            if context.intent.comparison_search:
                self._select_comparison_products(context)
                if context.intent.clarification or not context.intent.references:
                    return
            self._resolve_comparison_products(context)
            self._resolve_named_products(context)
            if context.intent.clarification:
                return
            if context.intent.references:
                ids = [uuid.UUID(ref["ProductId"]) for ref in context.intent.references]
                details = self.catalog.get_product_details(ids)
                describe = context.intent.intent == "product_description"
                for ref in context.intent.references:
                    detail = details.get(uuid.UUID(ref["ProductId"]))
                    if detail is not None:
                        context.referenced.append(self._read(detail, context, variant_limit=8 if describe else 4,
                                                             spec_limit=DESCRIBED_SPECS if describe else 12))
                if context.intent.intent == "explain_recommendation":
                    self._explain(context, details)
                elif context.intent.intent == "product_comparison":
                    self._comparison_items(context, details)
            if context.intent.intent == "policy_inquiry":
                context.policy = self._policy(context)
            elif context.intent.intent == "promotion_inquiry":
                context.policy = {"Promotion": self._promotion_lines(context)}
            if context.intent.recommending and context.intent.category_id:
                text = fold(context.question)
                sort = next((sort for terms, sort in PREFETCH_SORTS if any(term in text for term in terms)), "price_asc")
                context.prefetched = self.search_products(SearchProductsArguments(sort=sort), context)
        except (BusinessRuleError, NotFoundError):
            pass  # The model can still read the catalog with its own tool calls.

    def _select_comparison_products(self, context):
        """A shopping comparison uses the existing filtered/ranked search and locks one eligible SKU per model."""
        text = fold(context.question)
        sort = next((sort for terms, sort in PREFETCH_SORTS if any(term in text for term in terms)), "price_asc")
        context.prefetched = self.search_products(SearchProductsArguments(sort=sort), context)
        products = context.prefetched["Products"][:context.intent.requested_count]
        if not products:
            return
        if len(products) == 1:
            context.intent.clarification = ("Hiện mình chỉ tìm được 1 mẫu đáp ứng điều kiện của bạn, "
                                            "chưa đủ 2 mẫu để lập bảng so sánh. Bạn muốn nới ngân sách hoặc bớt tiêu chí nào?")
            return
        context.intent.references = tuple({"ProductId": product["ProductId"], "ProductName": product["Name"],
            "Slug": product["Slug"], "ProductVariantId": product["Variants"][0]["ProductVariantId"], "Rank": index}
            for index, product in enumerate(products, 1))

    def _resolve_comparison_products(self, context):
        """Resolve explicitly named subjects via the public catalog, before Gemini can pick a match."""
        intent = context.intent
        if intent.intent != "product_comparison" or intent.references or intent.clarification:
            return
        question = re.sub(r"^.*?\bso s[áa]nh\s+(?:(?:giúp|giùm|hộ|cho)\s+(?:mình|tôi|em|tui|anh|chị)\s+)?", "",
                          context.question, flags=re.I).strip(" .?!")
        if (not context.state.last_list() and re.search(r"\b(?:may|mau|san pham|cai|con|laptop|dien thoai) nao\b", fold(question))
                and not re.search(r"\d", question)):
            intent.clarification = "Mình chưa xác định được các mẫu cần so sánh. Bạn muốn so sánh 2 hoặc 3 sản phẩm nào?"
            return
        # A trailing question ('… khác nhau thế nào?', '…, máy nào tốt hơn?') is not part of the last model name.
        question = re.split(r"(?:\s+|\s*,\s*)(?:khác nhau|khác gì|có gì|có khác|thì|nên|cái nào|máy nào|mẫu nào|con nào"
                            r"|loại nào|tốt hơn|ra sao|thế nào|như thế nào)\b", question, maxsplit=1, flags=re.I)[0]
        # Remove criteria before splitting/counting subjects: their commas and 'và' do not name more products.
        question = _strip_aspect(question)
        question = re.split(r"\s+(?:về|theo)(?:\s*:\s*|\s+)", question, maxsplit=1, flags=re.I)[0].rstrip(" .,;?!")
        if re.fullmatch(rf"{_ASPECT}(?:\s*(?:[,;]|\bva\b)\s*{_ASPECT})*", fold(question)):
            return  # "… rồi so sánh CPU, RAM, SSD…" contains criteria only; it names no products.
        # The user text alone supplies queries; the limit applies to actual subjects only.
        chunks = re.split(r"\s+(?:v[àa]|v[ớo]i|vs\.?|versus)\s+|\s*[,;]\s*", question, flags=re.I)
        if len(chunks) < 2:
            return
        if len(chunks) > 3:
            intent.clarification = "Mỗi bảng so sánh hỗ trợ tối đa 3 sản phẩm. Bạn chọn 2 hoặc 3 mẫu nhé."
            return
        references = []
        for index, chunk in enumerate(chunks, 1):
            query = re.split(r"\s+(?:về|theo|cho|để)\s+", chunk, maxsplit=1, flags=re.I)[0].strip(" .?!")
            query = _strip_aspect(re.sub(r"^(?:giữa\s+)?(?:(?:máy|mẫu|sản phẩm)\s+)?", "", query, flags=re.I))
            if not query:
                return  # Nothing to look up; the model can still read the catalog.
            found = self.catalog.search_products(keyword=query[:100], page_size=10, sort="relevance")
            if not found.Items:
                intent.clarification = f"Mình chưa tìm thấy {query} đang hiển thị tại VieTech. Bạn kiểm tra lại tên hoặc phiên bản nhé."
                return
            exact = [p for p in found.Items if fold(p.Name) == fold(query)]
            if len(exact) == 1:
                matches = exact
            elif found.Total == 1:
                matches = found.Items
            elif found.Total <= len(found.Items):
                matches = closest_products(query, found.Items)
            else:
                matches = []
            if len(matches) != 1:
                names = ", ".join(p.Name for p in (matches or found.Items)[:5])
                intent.clarification = f"Có nhiều sản phẩm khớp với {query}: {names}. Bạn chọn mẫu và phiên bản cụ thể nhé."
                return
            product = matches[0]
            references.append({"ProductId": str(product.ProductId), "ProductName": product.Name,
                               "Slug": product.Slug, "Rank": index})
        intent.references = tuple(references)

    def _comparison_items(self, context, details):
        """Lock referenced SKUs, including out-of-stock ones. Never substitute another version."""
        items = []

        def colour_default(detail, variants):
            kind = context.vocab.kind(str(detail.CategoryId))
            return colour_only_default(variants, spec_signature(detail.Specifications, kind))

        # The version question names the first product still lacking a version, so a reply ("Bản 16GB / 512GB")
        # chooses for that one. Others are matched only when the question names them. Versions that differ only in
        # colour compare the same, so they are never asked about.
        pending = next((ref for ref in context.intent.references if not ref.get("ProductVariantId")
                        and (detail := details.get(uuid.UUID(ref["ProductId"]))) is not None
                        and len(active := [v for v in detail.Variants if v.IsActive]) > 1
                        and colour_default(detail, active) is None), None)
        for ref in context.intent.references:
            detail = details.get(uuid.UUID(ref["ProductId"]))
            if detail is None:
                context.intent.clarification = "Một sản phẩm không còn được hiển thị hoặc đã ngừng bán. Bạn chọn lại mẫu để so sánh nhé."
                return []
            active = variants = [v for v in detail.Variants if v.IsActive]
            if ref.get("ProductVariantId"):
                variants = [v for v in variants if str(v.ProductVariantId) == ref["ProductVariantId"]]
            elif len(variants) > 1 and (ref is pending or fold(detail.Name) in fold(context.question)):
                matched = [v for v in variants if _mentions_variant(v.VariantName, context.question)]
                if not matched:
                    matched = [v for v in variants if v.Storage and _mentions_variant(v.Storage, context.question)]
                if len(matched) == 1:
                    variants = matched
            colour_only = colour_default(detail, active) if len(active) > 1 else None
            if len(variants) > 1 and colour_only is not None:
                variants = [colour_only]
            if len(variants) != 1:
                context.intent.clarification = (f"Bạn muốn so sánh phiên bản nào của {detail.Name}? "
                    + ", ".join(v.VariantName for v in variants[:6]) if variants else
                    f"Phiên bản của {detail.Name} không còn được hiển thị. Bạn chọn lại phiên bản nhé.")
                return []
            if context.intent.comparison_search and variants[0].ProductVariantId not in {
                    v.ProductVariantId for v in self._variants(detail, self._constraints(context))}:
                context.intent.clarification = (f"{detail.Name} hiện không còn phiên bản đã chọn đáp ứng ngân sách "
                    "hoặc tình trạng còn hàng. Bạn thử lại để mình chọn các mẫu phù hợp nhé.")
                return []
            ref["ProductVariantId"] = str(variants[0].ProductVariantId)
            items.append((detail, variants[0]))
        if not 2 <= len(items) <= 3 or len({v.ProductVariantId for _, v in items}) != len(items):
            context.intent.clarification = "Bạn chọn từ 2 đến 3 sản phẩm hoặc phiên bản khác nhau để so sánh nhé."
            return []
        context.comparison = build_comparison(items, context, self.clock().isoformat())
        if context.intent.comparison_search and len(items) < context.intent.requested_count:
            context.comparison["Caveats"].append(
                f"Hiện chỉ tìm được {len(items)} mẫu đáp ứng điều kiện của bạn, so với {context.intent.requested_count} mẫu yêu cầu.")
        return items

    def _resolve_named_products(self, context):
        """Resolve a model for offers, price or availability without substituting another product."""
        intent = context.intent
        if not intent.product_query or intent.references or intent.clarification:
            return
        found = self.catalog.search_products(keyword=intent.product_query, page_size=6, sort="relevance")
        if not found.Items:
            intent.clarification = (f"Mình chưa tìm thấy sản phẩm {intent.product_query} đang bán tại VieTech. "
                                    "Bạn kiểm tra lại tên hoặc gửi link sản phẩm giúp mình nhé.")
            return
        if found.Total > 5:
            intent.clarification = f"Bạn muốn hỏi mẫu hoặc phiên bản {intent.product_query} nào?"
            return
        intent.references = tuple({"ProductId": str(product.ProductId), "ProductName": product.Name,
                                   "Rank": index, "Slug": product.Slug} for index, product in enumerate(found.Items, 1))
        categories = {str(product.CategoryId) for product in found.Items}
        if len(categories) == 1:
            intent.category_id = categories.pop()

    def _explain(self, context, details):
        """Why the products just shown were chosen: the ranking formula re-applied to them with the conditions still in
        force. Their shown order is kept; Matched/Gaps are the evidence the answer quotes."""
        candidates, ranks = [], {}
        for ref in context.intent.references:
            key = ref["ProductId"]
            detail = details.get(uuid.UUID(key))
            if detail is None or key not in context.products:
                continue
            shown = next((v for v in detail.Variants if str(v.ProductVariantId) == ref.get("ProductVariantId")), None)
            variant = shown or next(iter(self._variants(detail, context.filters[key])), None)
            if variant is not None:
                candidates.append(self._candidate(detail, variant, context))
                ranks[key] = ref.get("Rank")
        ordered, _ = rank(context.ranking, candidates, budget_max=context.intent.filters()["max_price"])
        for candidate, evaluation in ordered:
            if evaluation.score is None:
                continue
            context.explained[candidate.product_id] = evaluation
            reasons = {"Rank": ranks[candidate.product_id], "Matched": evaluation.matched[:4],
                       "Gaps": evaluation.gaps[:3], "WithinBudget": "B" in evaluation.parts,
                       "PreferredBrand": evaluation.soft_brand}
            context.products[candidate.product_id]["Ranking"] = {k: v for k, v in reasons.items() if v not in (False, [])}

    def _policy(self, context):
        """Policy lines for the topics asked, with the warranty months of the products just shown."""
        policy = {}
        for topic in context.intent.topics:
            if topic == "promotion":
                policy["Promotion"] = self._promotion_lines(context)
            elif topic == "warranty":
                shown = (context.intent.references or context.state.last_list() or context.state.last_focus())[:5]
                details = self.catalog.get_product_details([uuid.UUID(ref["ProductId"]) for ref in shown]) if shown else {}
                if "category" in context.intent.explicit and context.intent.category_id:
                    root = context.vocab.root_id(context.intent.category_id)
                    details = {key: detail for key, detail in details.items()
                               if context.vocab.root_id(str(detail.CategoryId)) == root}
                months = [f"{ref.get('Rank', index)}. {detail.Name}: "
                          + (f"{detail.WarrantyMonths} tháng" if detail.WarrantyMonths else "không có bảo hành")
                          for index, ref in enumerate(shown, 1)
                          if (detail := details.get(uuid.UUID(ref["ProductId"]))) is not None]
                lines = list(warranty_lines(context.question, has_products=bool(months)))
                if months:
                    lines = ["Thời hạn bảo hành của các mẫu vừa giới thiệu:", *months, *lines]
                policy["Warranty"] = lines
            elif topic == "returns":
                policy["Returns"] = list(return_lines(context.question))
        return policy

    def _ensure(self, context):
        if context.intent is None:  # Direct tool use without prepare() (scripts, older callers).
            context.vocab = self.vocabulary()
            context.intent = analyze(context.question, context.vocab, context.state)
            context.constraints = context.intent.filters()
            context.ranking = RankingCriteria(context.intent.needs, context.intent.soft_brands())

    # --- Tools ---------------------------------------------------------------------------------------------------

    @staticmethod
    def _match(value, rows, aliases=None):
        if value is None:
            return None
        needle = fold(value.replace("-", " "))
        needle = (aliases or {}).get(needle, needle)
        matches = [row for row in rows if needle in {fold(row.name), fold(row.slug.replace("-", " "))}]
        if len(matches) != 1:
            raise BusinessRuleError("Tên hãng/danh mục không rõ hoặc không đang hiển thị", code="ai_unknown_filter")
        return matches[0]

    def _category(self, value, vocab):
        try:
            return self._match(value, vocab.categories, CATEGORY_ALIASES)
        except BusinessRuleError:
            roots = ", ".join(c.name for c in vocab.categories if not c.parent_id)
            raise BusinessRuleError(f"Danh mục không rõ. Dùng tên danh mục VieTech, ví dụ: {roots}",
                                    code="ai_unknown_filter") from None

    @staticmethod
    def _category_tree(category_id, categories):
        if not category_id:
            return None
        allowed = {str(category_id)}
        for _ in range(len(categories)):
            expanded = allowed | {c.id for c in categories if c.parent_id in allowed}
            if expanded == allowed:
                break
            allowed = expanded
        return allowed

    def _constraints(self, context):
        self._ensure(context)
        guard = context.intent.filters()
        return {**guard, "category_ids": self._category_tree(guard["category_id"], context.vocab.categories)}

    @staticmethod
    def _variants(detail, filters):
        if filters.get("brand_id") and str(detail.BrandId) != filters["brand_id"]:
            return []
        if str(detail.BrandId) in filters.get("excluded_brand_ids", []):
            return []
        if filters.get("brand_ids") and str(detail.BrandId) not in filters["brand_ids"]:
            return []
        if not meets_features(detail, filters.get("required_features", ())):
            return []
        if filters.get("category_ids") and str(detail.CategoryId) not in filters["category_ids"]:
            return []
        rows = []
        for variant in detail.Variants:
            price = _price(variant)
            if (not variant.IsActive or variant.StockQuantity <= 0
                    or (filters.get("min_price") is not None and price < Decimal(str(filters["min_price"])))
                    or (filters.get("max_price") is not None and price > Decimal(str(filters["max_price"])))):
                continue
            if not _has_memory(detail, variant, filters):
                continue
            rows.append(variant)
        return sorted(rows, key=lambda v: (_price(v), str(v.ProductVariantId)))

    def _public_product(self, detail, filters, *, summary=False, variant_limit=12, spec_limit=12):
        eligible = self._variants(detail, filters)
        # Eligible variants first, so a shortened list (batch read) keeps the ones that can be recommended.
        listed = eligible + [v for v in detail.Variants if v not in eligible]
        facts = {
            "ProductId": str(detail.ProductId), "Slug": detail.Slug, "Name": detail.Name,
            "Brand": detail.Brand.Name, "Category": detail.Category.Name,
            "EligibleForRecommendation": bool(eligible),
            "Variants": [{"ProductVariantId": str(v.ProductVariantId), "VariantName": v.VariantName,
                "SalePrice": str(_price(v)), "InStock": v.StockQuantity > 0}
                for v in (eligible[:1] if summary else listed[:variant_limit])],
        }
        if not summary:
            facts["Specifications"] = public_specifications(detail.Specifications, spec_limit)
            facts["WarrantyMonths"] = detail.WarrantyMonths
        if filters.get("required_features"):
            facts["RequiredFeatureEvidence"] = [feature_evidence(detail, feature)
                for feature in filters["required_features"] if feature_evidence(detail, feature)]
        return facts

    def _excluded(self, product_id, name, context):
        intent = context.intent
        return bool(intent and (intent.recommending or intent.comparison_search) and (
            product_id in intent.excluded_product_ids or model_key(name) in intent.excluded_model_keys))

    def _candidate(self, detail, variant, context):
        return Candidate(str(detail.ProductId), str(detail.BrandId), detail.Name, detail.Category.Name,
                         context.vocab.kind(str(detail.CategoryId)), detail.Specifications or {}, _price(variant))

    def search_products(self, args, context):
        self._ensure(context)
        intent, vocab = context.intent, context.vocab
        guard = intent.filters()
        question = fold(context.question)
        # What the customer's own words fix (with context) wins; the model's value only fills a gap, so a guessed name
        # cannot fail a search the customer phrased clearly.
        category_id = guard["category_id"] or (
            soften_category(self._category(args.category, vocab), vocab).id if args.category else None)
        brand_id = guard["brand_id"]
        if not brand_id and not guard.get("brand_ids") and args.brand:
            brand = self._match(args.brand, vocab.brands)
            named = re.search(r"\b" + re.escape(fold(brand.name)) + r"\b", question)
            # A brand the customer did not name must not narrow a recommendation; a soft brand is scored by T.
            if ((named or not intent.recommending) and brand.id not in intent.soft_brands()
                    and brand.id not in guard["excluded_brand_ids"]):
                brand_id = brand.id
        prices = [v for v in (args.max_price, guard["max_price"]) if v is not None]
        ceiling = min(prices) if prices else None
        floors = [v for v in (args.min_price, guard["min_price"]) if v is not None]
        floor = max(floors) if floors else None
        if floor is not None and ceiling is not None and floor > ceiling:
            floor = None  # A model-added floor never empties a range the customer set.
        filters = {**guard, "category_ids": self._category_tree(category_id, vocab.categories),
                   "brand_id": brand_id, "max_price": ceiling, "min_price": floor}
        keyword = args.keyword
        if keyword and (fold(keyword) in USAGE_KEYWORDS or detect_needs(keyword)):
            keyword = None
        listing = dict(keyword=keyword, category_id=uuid.UUID(category_id) if category_id else None,
                       brand_id=uuid.UUID(brand_id) if brand_id else None, include_descendants=True,
                       min_price=floor, max_price=ceiling, in_stock=True, sort=args.sort, match_variant_price=True,
                       excluded_brand_ids=[uuid.UUID(value) for value in guard["excluded_brand_ids"]])
        rows, page = [], 1
        while True:  # Pages of 30; a second (third) page only when the first is full and shown products were dropped.
            items = self.catalog.search_products(**listing, page=page, page_size=CANDIDATE_PAGE).Items
            rows += items
            if len(items) < CANDIDATE_PAGE or len(rows) >= CANDIDATE_MAX + len(intent.excluded_product_ids) or page == 3:
                break
            page += 1
        # One batch instead of a detail query per candidate: scoring needs every eligible candidate's specs.
        details = self.catalog.get_product_details([row.ProductId for row in rows])
        eligible, hidden = [], 0
        for row in rows:
            detail = details.get(row.ProductId)
            variants = self._variants(detail, filters) if detail is not None else []
            if not variants:
                continue  # Price filtering in the listing can use a cheaper out-of-stock variant.
            if self._excluded(str(detail.ProductId), detail.Name, context):
                hidden += 1  # Already shown in this need group, or rejected: never repeated by memory alone.
                continue
            if len(eligible) < CANDIDATE_MAX:
                eligible.append((detail, variants[0]))
        ranked = self.ranking and not intent.explicit_order
        if ranked:
            ordered, context.dropped = rank(context.ranking, [self._candidate(d, v, context) for d, v in eligible],
                                            budget_max=ceiling)
            by_id = {str(d.ProductId): d for d, _ in eligible}
            ordered = [(by_id[candidate.product_id], evaluation) for candidate, evaluation in ordered]
            ranked = any(evaluation.score is not None for _, evaluation in ordered)
        else:
            ordered = [(detail, None) for detail, _ in eligible]
        result = []
        for position, (detail, evaluation) in enumerate(ordered[:RESULT_LIMIT], 1):
            public = self._public_product(detail, filters, summary=True)
            if evaluation is not None and evaluation.score is not None:
                public["Ranking"] = {"Rank": position, "Score": round(evaluation.score, 2),
                                     "Parts": {key: round(value, 2) for key, value in evaluation.parts.items()},
                                     "Matched": evaluation.matched[:4], "Gaps": evaluation.gaps[:3]}
            key = str(detail.ProductId)
            context.products[key], context.filters[key] = public, filters
            result.append(public)
        context.searched, context.hidden = True, hidden
        context.search_order = [p["ProductId"] for p in result]
        response = {"Products": result, "Returned": len(result), "Eligible": len(eligible),
                    "CandidateLimit": CANDIDATE_MAX, "Ranked": ranked, "Constraints": context.constraints,
                    "Note": "Kết quả có giới hạn; thông số chi tiết dùng get_product. Gaps là tiêu chí chưa đạt hoặc chưa có dữ liệu."}
        if hidden:
            response["AlreadyShownExcluded"] = hidden
            if not eligible:
                response["Note"] = ("Mọi sản phẩm phù hợp đã được giới thiệu trước đó. Hãy nói rõ là đã hết lựa chọn mới "
                                    "và gợi ý khách nới ngân sách, đổi hãng hoặc bớt tiêu chí; không lặp lại sản phẩm cũ.")
        elif not eligible and ceiling is not None:
            nearest = self._nearest_above(listing, filters, context)
            if nearest:
                response["NearestAboveBudget"] = nearest
        return response

    def _nearest_above(self, listing, filters, context):
        """The cheapest product that meets every other condition but the ceiling, so "không có" can say how far off."""
        rows = self.catalog.search_products(**{**listing, "max_price": None, "sort": "price_asc"}, page=1,
                                            page_size=CANDIDATE_PAGE).Items
        details = self.catalog.get_product_details([row.ProductId for row in rows])
        relaxed = {**filters, "max_price": None}
        for row in rows:
            detail = details.get(row.ProductId)
            variants = self._variants(detail, relaxed) if detail is not None else []
            if variants and not self._excluded(str(detail.ProductId), detail.Name, context):
                context.nearest = {"ProductId": str(detail.ProductId), "Name": detail.Name,
                                   "Brand": detail.Brand.Name, "Price": str(_price(variants[0]))}
                return context.nearest
        return None

    def get_product(self, args, context):
        if args.product_ids:
            # Each product is read like a single call; one that is not on sale does not hide the others.
            products = []
            for product_id in args.product_ids:
                try:
                    # Shorter variant lists keep five products inside the bounded tool result.
                    products.append(self._read(self.catalog.get_product_detail(product_id), context,
                                               variant_limit=2 if len(args.product_ids) > 3 else 4))
                except NotFoundError as error:
                    products.append({"ProductId": str(product_id), "error": error.code})
            return {"Products": products}
        if args.rank:
            reference = next((p["ProductId"] for p in context.references if p.get("Rank") == args.rank), None)
            if reference is None and not context.references and args.rank <= len(context.search_order):
                reference = context.search_order[args.rank - 1]
            if reference is None:
                raise NotFoundError("Không có sản phẩm ở thứ tự này; dùng product_id từ search_products",
                                    code="ai_reference_not_found")
            detail = self.catalog.get_product_detail(uuid.UUID(reference))
        elif args.product_id:
            detail = self.catalog.get_product_detail(args.product_id)
        else:
            detail = self.catalog.get_product_detail_by_slug(args.slug)
        return self._read(detail, context)

    def _read(self, detail, context, *, variant_limit=12, spec_limit=12):
        key = str(detail.ProductId)
        # A detail lookup must not widen the filters used to select this product in the same turn.
        filters = context.filters.get(key)
        if filters is None:
            filters = self._constraints(context)
        public = self._public_product(detail, filters, variant_limit=variant_limit, spec_limit=spec_limit)
        context.products[key], context.filters[key] = public, filters
        return public

    def list_offers(self, args, context):
        self._ensure(context)
        self._resolve_named_products(context)
        if context.intent.clarification:
            raise BusinessRuleError(context.intent.clarification, code="ai_reference_not_found")
        if args.product_id is None and context.intent.references:
            coupons = {}
            for ref in context.intent.references:
                result = self.list_offers(ListOffersArguments(product_id=uuid.UUID(ref["ProductId"])), context)
                coupons.update((coupon["Code"], coupon) for coupon in result["Coupons"])
            return {**result, "Coupons": list(coupons.values())[:5]}
        category_ids = self._offer_category_ids(context) if args.product_id is None else None
        shown = next((ref.get("ProductVariantId") for ref in context.intent.references
                      if ref["ProductId"] == str(args.product_id)), None)
        coupons = self.pricing.public_coupons(product_id=args.product_id,
                                             actor=self.actor,
                                             single_item=args.product_id is not None or category_ids is not None,
                                             product_variant_id=uuid.UUID(shown) if shown else None,
                                             **({"category_ids": category_ids} if category_ids is not None else {}))
        code = requested_coupon(fold(context.question))
        if code:
            coupons = [coupon for coupon in coupons if fold(coupon.Code) == code]
        scope = str(args.product_id) if args.product_id else None
        if scope not in context.offer_scopes:
            context.offer_scopes.append(scope)
        listed = [self._coupon(c) for c in coupons[:5]]
        context.offers += listed
        return {"Coupons": listed,
                "Note": "Coupon có điều kiện; không phải giá mua cuối cùng hoặc cam kết đủ điều kiện cho khách."}

    @staticmethod
    def _coupon(coupon):
        return {"Code": coupon.Code, "Name": coupon.Name, "DiscountType": coupon.DiscountType,
                "DiscountValue": str(coupon.DiscountValue), "MinOrderValue": str(coupon.MinOrderValue),
                "MaxDiscountAmount": str(coupon.MaxDiscountAmount) if coupon.MaxDiscountAmount is not None else None,
                "EndDate": coupon.EndDate.isoformat(), "PerCustomerUsageLimit": coupon.PerCustomerUsageLimit}

    # --- Final answer --------------------------------------------------------------------------------------------

    def finish(self, decision, context, max_products):
        text, cards, references, notes = self._finish_answer(decision, context, max_products)
        return customer_text(text), cards, references, customer_notes(notes)

    def _finish_answer(self, decision, context, max_products):
        """Reload critical facts and return (text, cards, references, notes) from current public services.

        Gemini's `message` is shown only if every fact in it is grounded (ai_grounding); otherwise the backend's own
        wording is used. Cards, prices and stock always come from the backend.
        """
        self._ensure(context)
        self._resolve_named_products(context)
        notes = {"AnswerIntent": decision.intent, "AnswerSource": "backend"}
        if context.intent.transaction:  # An order or payment request, whatever else the question asks.
            return ORDER_ACTION, [], [], {**notes, "AnswerIntent": "handoff"}
        if context.intent.intent == "comparison_guidance":
            return COMPARISON_GUIDANCE, [], [], {**notes, "AnswerIntent": "chat"}
        if context.intent.clarification:
            return context.intent.clarification, [], [], {**notes, "AnswerIntent": "clarify"}
        if context.intent.intent == "product_compatibility":
            return AiCompatibility(self.catalog, context, clock=self.clock, variant_match=_mentions_variant).finish(decision, notes)
        if decision.intent == "compatibility":
            return CLARIFY["products"], [], [], {**notes, "AnswerIntent": "clarify"}
        if context.intent.intent == "promotion_inquiry" and not context.policy:
            # Direct/older callers may skip prepare(); they still must answer within the customer's scope.
            context.policy = {"Promotion": []}
        # Questions the backend answers from its own data: the model only words the answer, whatever it chose.
        if context.intent.intent == "explain_recommendation" and context.intent.references:
            return self._explanation(decision, context, {**notes, "AnswerIntent": "explain"})
        if context.intent.intent == "product_description" and context.referenced:
            return self._description(decision, context, {**notes, "AnswerIntent": "describe"})
        if context.intent.intent in ("policy_inquiry", "promotion_inquiry") and context.policy:
            policy = dict(context.policy)
            if "Promotion" in policy:  # Coupons are read again: one that just expired is not offered.
                context.offers.clear()
                context.offer_scopes.clear()
                policy["Promotion"] = self._promotion_lines(context)
            context.policy = policy
            notes["AnswerIntent"] = "offers" if context.intent.intent == "promotion_inquiry" else "policy"
            text = policy_text(policy)
            issue = return_message_issue(decision.message) if "Returns" in policy else None
            if "Warranty" in policy:
                warranty_message = decision.message or ""
                if "Returns" in policy:
                    warranty_message = ". ".join(part for part in re.split(r"[.!?\n]", warranty_message)
                                                 if "bao hanh" in fold(part))
                issue = issue or warranty_message_issue(warranty_message)
            unscoped_warranty = "Warranty" in policy and not context.referenced
            unavailable_code = ("Promotion" in policy and requested_coupon(fold(context.question))
                                and not context.offers)
            if issue:
                notes["GroundingIssues"] = [issue]
            if decision.intent in ("policy", "offers") and not (issue or unavailable_code or unscoped_warranty):
                text = self._worded(decision, context, text, notes)
            return text, [], list(context.intent.references), notes
        if (context.intent.intent == "product_comparison" and context.intent.references) or decision.intent == "compare":
            return self._comparison(decision, context, notes, max_products)
        intent = decision.intent
        if intent == "clarify":
            fallback = context.intent.clarification or CLARIFY[decision.clarification]
            if context.intent.clarification:
                return fallback, [], [], notes  # A reference the backend could not resolve: its own question.
            return self._worded(decision, context, fallback, notes), [], [], notes
        if intent == "handoff":
            return self._worded(decision, context, HANDOFF, notes), [], [], notes
        if intent == "chat":
            return self._worded(decision, context, CHAT, notes), [], [], notes
        if intent == "offers":
            return self._offers_text(context), [], [], notes
        if intent == "no_results":
            if not context.searched:
                raise AiUnavailableError("AI chưa tìm kiếm để xác nhận kết quả.", code="ai_ungrounded_output")
            return self._worded(decision, context, self._no_results_text(context), notes), [], [], notes

        wanted = context.intent.requested_count
        limit = min(max_products, wanted or max_products)
        selection_changed = False
        loaded = []
        for selection in decision.products:
            key = str(selection.product_id)
            if key not in context.products:
                raise AiUnavailableError("AI chọn sản phẩm chưa được tra cứu.", code="ai_ungrounded_output")
            if intent == "recommend" and self._excluded(key, context.products[key]["Name"], context):
                continue  # Already shown or rejected: the backend never repeats it as a "new" option.
            try:
                detail = self.catalog.get_product_detail(selection.product_id)
            except NotFoundError:
                loaded.append((selection, None, None))
                continue
            loaded.append((selection, detail, self._selected_variant(detail, selection, context)))
        if intent == "recommend" and not loaded:
            loaded = self._next_candidates(context, limit)
            notes["Replaced"] = True
            if not loaded:
                return self._no_results_text(context), [], [], {**notes, "AnswerIntent": "no_results"}
        if intent == "recommend" and wanted and len(loaded) < limit and context.searched:
            selected = {str(selection.product_id) for selection, _, _ in loaded}
            for extra in self._next_candidates(context, limit):
                if str(extra[0].product_id) not in selected:
                    loaded.append(extra)
                    selected.add(str(extra[0].product_id))
                    selection_changed = True
                if len(loaded) >= limit:
                    break
        evaluations = self._rank_selection(loaded, context) if intent == "recommend" else {}
        if intent == "recommend" and len(loaded) > limit:
            loaded = loaded[:limit]
            selection_changed = True
        cards, references, lines, products = [], [], [], []
        for rank_, (selection, detail, variant) in enumerate(loaded, 1):
            key = str(selection.product_id)
            if detail is None:
                lines.append(f"Lựa chọn {rank_} không còn được hiển thị. Vui lòng tìm lại sản phẩm.")
                continue
            filters = context.filters[key]
            if intent == "recommend" and variant is None:
                lines.append(f"{rank_}. {detail.Name}: hiện không có phiên bản còn hàng thỏa điều kiện đã tra cứu.")
                continue
            products.append((detail, variant))
            price = _price(variant) if variant else None
            references.append({"Rank": rank_, "ProductId": key, "Slug": detail.Slug,
                               "ProductVariantId": str(variant.ProductVariantId) if variant else None,
                               "ProductName": detail.Name, "ModelKey": model_key(detail.Name),
                               "Price": str(price) if price is not None else None,
                               "SnapshotAt": self.clock().isoformat()})
            lines.append(f"\n**{rank_}. {detail.Name}**")
            if variant:
                lines.append(f"- Phiên bản: {variant.VariantName}, giá: {money(price)}, còn hàng.")
                images = detail.VariantImages.get(variant.ProductVariantId) or detail.Images
                image = next((image for image in images if image.IsDefault), images[0] if images else None)
                card = {"ProductId": key, "Slug": detail.Slug, "ProductName": detail.Name,
                    "ProductVariantId": str(variant.ProductVariantId), "VariantName": variant.VariantName,
                    "Price": str(price), "OriginalPrice": str(variant.OriginalPrice if variant.OriginalPrice is not None else variant.Price),
                    "ImageUrl": image.ImageUrl if image else None,
                    "InStock": True, "Rank": rank_, "SnapshotAt": self.clock().isoformat()}
                if len(cards) < limit:
                    cards.append(card)
                lines.extend(self._reasons(evaluations.get(key), filters))
                lines.extend("- " + evidence + "." for feature in filters.get("required_features", ())
                             if (evidence := feature_evidence(detail, feature)))
            else:
                lines.append("Hiện không có phiên bản còn hàng thỏa điều kiện đã tra cứu.")
            if intent in ("product", "compare"):
                facts = self._public_product(detail, filters).get("Specifications", {})
                known = context.products[key].get("Specifications", {})
                # A key this turn did not read is dropped, never shown: "Bảo hành" is WarrantyMonths, listed below.
                keys = ([name for name in selection.specification_keys if name in known]
                        or self._relevant_keys(context.question, facts))
                lines.extend(f"- {name}: {facts.get(name, 'Chưa có thông tin')}" for name in keys)
                lines.append(f"- Bảo hành: {detail.WarrantyMonths} tháng.")
        fallback = "\n".join([self._intro(intent, context, len(products)), *lines]).strip()
        if intent == "recommend" and products:
            fallback += "\nBạn muốn mình so sánh chi tiết các mẫu này hoặc xem thêm lựa chọn khác không?"
        order = [str(detail.ProductId) for detail, _ in products]
        text = fallback if selection_changed else self._worded(decision, context, fallback, notes,
                                                               selected=products, order=order)
        if (intent == "recommend" and wanted
                and len(cards) < min(wanted, max_products) and f"{len(cards)} mẫu" not in text):
            scope = "mẫu mới" if context.intent.intent == "recommend_more" else "mẫu"
            text += f"\nHiện mình chỉ tìm được {len(cards)} {scope} phù hợp với nhu cầu này."
        return text, cards, references, notes

    def _comparison(self, decision, context, notes, max_products):
        if context.intent.intent != "product_comparison" or not context.intent.references:
            # The model chose to compare (the backend resolved no subjects, or read the question as another intent
            # such as "máy thứ hai có gì hơn …"): use its selection, limited to products read in this turn.
            refs = []
            for index, selection in enumerate(decision.products, 1):
                key = str(selection.product_id)
                public = context.products.get(key)
                if public is None:
                    raise AiUnavailableError("AI chọn sản phẩm chưa được tra cứu.", code="ai_ungrounded_output")
                if selection.product_variant_id and str(selection.product_variant_id) not in {
                        v["ProductVariantId"] for v in public["Variants"]}:
                    raise AiUnavailableError("AI chọn phiên bản chưa được tra cứu.", code="ai_ungrounded_output")
                refs.append({"ProductId": key, "Rank": index,
                             "ProductVariantId": str(selection.product_variant_id) if selection.product_variant_id else None})
            context.intent.references = tuple(refs)
        ids = [uuid.UUID(ref["ProductId"]) for ref in context.intent.references]
        items = self._comparison_items(context, self.catalog.get_product_details(ids))
        if context.intent.clarification:
            return context.intent.clarification, [], [], {**notes, "AnswerIntent": "clarify"}
        snapshot = context.comparison
        # Derive analysis from explicit specs, documented architecture facts and Recommendation Engine evidence.
        # Numeric grounding alone cannot prove 'chạy Android Studio mượt' or 'camera đẹp hơn'.
        notes.update(AnswerIntent="compare", Comparison=snapshot)
        if decision.message:
            _, issues = check_message(decision.message, self._facts(context, items, [str(d.ProductId) for d, _ in items]))
            if issues:
                notes["GroundingIssues"] = issues[:5]
        lines = ["So sánh các mẫu sau:"]
        cards, references = [], []
        for index, (product, (detail, variant)) in enumerate(zip(snapshot["Products"], items), 1):
            references.append({"Rank": index, "ProductId": product["ProductId"], "Slug": product["Slug"],
                "ProductName": product["ProductName"], "ProductVariantId": product["ProductVariantId"],
                "Price": product["Price"], "ModelKey": model_key(detail.Name), "SnapshotAt": snapshot["SnapshotAt"]})
            lines.append(f"\n### {product['ProductName']}\nPhiên bản: {product['VariantName']}.")
            for row in snapshot['Rows']:
                value = row['Values'][index - 1]
                lines.append(f"- {row['Label']}: " + value.replace('\n', '\n  '))
            if product['Strengths']:
                lines.append('\nCách sử dụng phù hợp:')
                lines.extend('- ' + line.replace('\n', '\n  ') for line in product['Strengths'])
            if len(cards) < max_products:
                cards.append({**{k: product[k] for k in ("ProductId", "ProductVariantId", "ProductName", "VariantName",
                    "Slug", "ImageUrl", "Price", "InStock")}, "Rank": index, "SnapshotAt": snapshot["SnapshotAt"],
                    "OriginalPrice": str(variant.OriginalPrice if variant.OriginalPrice is not None else variant.Price)})
        if snapshot["Recommendation"]:
            lines.append('\n### Chọn theo nhu cầu\n' + snapshot["Recommendation"])
        return "\n".join(lines), cards, references, notes

    def _explanation(self, decision, context, notes):
        """Text only (the cards were shown before); the references keep their ranks so "máy thứ hai" still works."""
        lines, references = [self._method(context)], []
        for ref in context.intent.references:
            key = ref["ProductId"]
            if key not in context.products:
                continue
            references.append(dict(ref))
            lines.append(f"\n**{ref.get('Rank', len(references))}. {context.products[key]['Name']}**")
            lines.extend(self._reasons(context.explained.get(key), context.filters[key])
                         or ["Chưa có đủ thông số để giải thích chi tiết mức phù hợp của mẫu này."])
        text = self._worded(decision, context, "\n".join(lines), notes, order=[ref["ProductId"] for ref in references])
        return text, [], references, notes

    def _description(self, decision, context, notes):
        """Each product the customer asked about, in its shown order: version and price, key specs, warranty. Text
        only, like an explanation; the references keep their ranks."""
        lines, references = [], []
        for ref in context.intent.references:
            public = context.products.get(ref["ProductId"])
            if public is None:
                continue
            references.append(dict(ref))
            variants = public["Variants"]
            variant = next((v for v in variants if v["ProductVariantId"] == ref.get("ProductVariantId")),
                           variants[0] if variants else None)
            lines.append(f"\n**{ref.get('Rank', len(references))}. {public['Name']}** ({public['Brand']})")
            if variant:
                stock = "còn hàng" if variant["InStock"] else "tạm hết hàng"
                lines.append(f"- Phiên bản {variant['VariantName']}: {money(variant['SalePrice'])}, {stock}.")
            specs = sorted((public.get("Specifications") or {}).items(), key=lambda item: next(
                (i for i, word in enumerate(KEY_SPECS) if word in fold(item[0])), len(KEY_SPECS)))
            lines += [f"- {name}: {value}" for name, value in specs[:8]]
            if not specs:
                lines.append("- Chưa có thông số chi tiết cho mẫu này.")
            lines.append(f"- Bảo hành: {public['WarrantyMonths']} tháng." if public.get("WarrantyMonths")
                         else "- Không có bảo hành.")
        lines.append("Bạn muốn mình so sánh các mẫu này hay giải thích vì sao chúng phù hợp với nhu cầu của bạn?")
        text = self._worded(decision, context, "\n".join(lines), notes, order=[ref["ProductId"] for ref in references])
        return text, [], references, notes

    def _method(self, context):
        intent = context.intent
        focus = ", ".join(priorities(intent.needs, intent.kind)[:4])
        basis = [f"mức đáp ứng nhu cầu theo thông số thực tế ({focus})" if focus else "mức đáp ứng nhu cầu theo thông số thực tế"]
        if intent.filters()["max_price"] is not None:
            basis.append("mức giá so với ngân sách")
        if intent.soft_brands():
            basis.append("hãng bạn ưu tiên")
        return (f"Mình chọn từ các sản phẩm đang bán và còn hàng tại VieTech{self._conditions(context)}, rồi xếp hạng theo "
                f"{', '.join(basis)}. Lý do từng mẫu:")

    def _intro(self, intent, context, count):
        if intent == "compare":
            return "So sánh nhanh theo thông số hiện có:"
        if intent == "product":
            return "Mẫu bạn hỏi:" if count else ""
        conditions = self._conditions(context)
        if context.intent.intent == "recommend_more":
            return f"Mình tìm thêm được {count} mẫu khác{conditions}:"
        return f"Mình tư vấn {count} mẫu này{conditions}:"

    def _conditions(self, context):
        intent, vocab = context.intent, context.vocab
        filters = intent.filters()
        parts = []
        if intent.needs:
            parts.append("nhu cầu " + ", ".join(NEEDS[need].label for need in intent.needs))
        if filters["max_price"] is not None and filters["min_price"] is not None:
            parts.append(f"giá từ {money(filters['min_price'])} đến {money(filters['max_price'])}")
        elif filters["max_price"] is not None:
            parts.append(f"giá không quá {money(filters['max_price'])}")
        elif filters["min_price"] is not None:
            parts.append(f"giá từ {money(filters['min_price'])}")
        brand = vocab.brand(filters["brand_id"])
        if brand:
            parts.append(f"hãng {brand.name}")
        if filters.get("min_ram_gb"):
            parts.append(f"RAM từ {filters['min_ram_gb']} GB")
        if filters.get("min_storage_gb"):
            size = filters["min_storage_gb"]
            parts.append(f"bộ nhớ từ {size // 1024} TB" if size % 1024 == 0 else f"bộ nhớ từ {size} GB")
        return f" với {', '.join(parts)}" if parts else ""

    def _no_results_text(self, context):
        category = context.vocab.category(context.intent.filters()["category_id"]) if context.intent else None
        subject = f"{category.name.lower()} " if category else ""
        if context.hidden:
            return (f"Mình đã giới thiệu hết {context.hidden} mẫu {subject}đang có hàng phù hợp{self._conditions(context)}. "
                    "Bạn có muốn nới ngân sách, đổi hãng hoặc bớt tiêu chí để mình tìm thêm không?")
        if context.nearest:
            nearest = context.nearest
            return ("VieTech chưa chọn được sản phẩm phù hợp trong phạm vi vừa tra cứu"
                    f"{self._conditions(context)}. Mẫu gần nhất là {nearest['Name']} với giá {money(nearest['Price'])}. "
                    "Bạn có muốn nới ngân sách hoặc đổi hãng không?")
        return ("VieTech chưa chọn được sản phẩm phù hợp trong phạm vi vừa tra cứu"
                f"{self._conditions(context)}. Bạn muốn điều chỉnh ngân sách hoặc hãng không?")

    def _offers_text(self, context):
        if not context.offer_scopes:
            raise AiUnavailableError("AI chưa tra cứu ưu đãi để trả lời.", code="ai_ungrounded_output")
        coupons = {}
        context.offers.clear()
        for scope in tuple(context.offer_scopes):
            result = self.list_offers(ListOffersArguments(product_id=uuid.UUID(scope) if scope else None), context)
            coupons.update((coupon["Code"], coupon) for coupon in result["Coupons"])
        lines = self._automatic_offer_lines(context) if None in context.offer_scopes and not context.intent.references else []
        if coupons:
            lines.append("Các mã ưu đãi công khai hiện có:")
            lines += [f"• {self._coupon_line(coupon)}" for coupon in list(coupons.values())[:5]]
        else:
            lines.append("VieTech hiện chưa tìm thấy mã ưu đãi công khai còn hiệu lực trong phạm vi vừa tra cứu.")
        lines.append("Điều kiện và khả năng áp dụng được kiểm tra lại tại giỏ hàng, giá sản phẩm đã tính ưu đãi tự động phù hợp.")
        return "\n".join(lines)

    def _offer_category_ids(self, context):
        intent = context.intent
        if intent and "category" in intent.explicit and intent.category_id:
            return [uuid.UUID(value) for value in self._category_tree(intent.category_id, context.vocab.categories)]
        return None

    def _promotion_lines(self, context):
        """Answer the asked product, category, code or usage question; never substitute store-wide offers."""
        question = fold(context.question)
        code, usage = requested_coupon(question), promotion_usage(question)
        if usage and not code:
            return list(PROMOTION_USAGE_LINES)
        refs = context.intent.references
        lines = []
        if refs:
            details = self.catalog.get_product_details([uuid.UUID(ref["ProductId"]) for ref in refs])
            if not code:
                lines.extend(self._automatic_offer_lines(context, category_ids={str(detail.CategoryId)
                                                                               for detail in details.values()}))
            for ref in refs:
                detail = details.get(uuid.UUID(ref["ProductId"]))
                if detail is None:
                    lines.append(f"{ref.get('ProductName', 'Sản phẩm này')}: hiện không còn thông tin ưu đãi công khai.")
                    continue
                public = self._read(detail, context)
                product_lines = [f"**{detail.Name}**"]
                variants = [v for v in detail.Variants if v.StockQuantity > 0]
                variant = next((v for v in variants if str(v.ProductVariantId) == ref.get("ProductVariantId")),
                               min(variants, key=lambda v: (_price(v), str(v.ProductVariantId))) if variants else None)
                if not code:
                    if variant:
                        sale = _price(variant)
                        original = variant.OriginalPrice if variant.OriginalPrice is not None else variant.Price
                        discount = max(Decimal(0), original - sale)
                        # These amounts also ground Gemini's wording.
                        chosen = next(v for v in public["Variants"] if v["ProductVariantId"] == str(variant.ProductVariantId))
                        chosen.update(OriginalPrice=str(original), DiscountAmount=str(discount))
                        info = (f"giảm {money(discount)}, còn {money(sale)} (giá gốc {money(original)})"
                                if discount else f"chưa có giảm giá tự động, giá hiện tại {money(sale)}")
                    else:
                        info = "hiện chưa có phiên bản còn hàng để xác nhận ưu đãi"
                    product_lines.append(f"- {info}.")
                coupons = self.list_offers(ListOffersArguments(product_id=detail.ProductId), context)["Coupons"]
                product_lines.extend(f"- {self._coupon_line(coupon)}" for coupon in coupons)
                if not coupons:
                    product_lines.append("- " + (f"Chưa tìm thấy mã {code.upper()} còn hiệu lực áp dụng cho sản phẩm này."
                                         if code else "Chưa có mã giảm giá phù hợp với giá hiện tại của sản phẩm này."))
                lines.append("\n".join(product_lines))
        else:
            coupons = self.list_offers(ListOffersArguments(), context)["Coupons"]
            if not code:
                lines.extend(self._automatic_offer_lines(context))
            lines.extend(f"Mã {self._coupon_line(coupon)}" for coupon in coupons)
            if not coupons:
                lines.append(f"Chưa tìm thấy mã {code.upper()} còn hiệu lực trong phạm vi bạn hỏi."
                             if code else "Hiện chưa có mã giảm giá công khai còn hiệu lực trong phạm vi bạn hỏi.")
        return lines + (list(PROMOTION_USAGE_LINES) if usage else [PROMOTION_LINE])

    def _automatic_offer_lines(self, context, *, category_ids=None):
        lines = []
        scoped = self._offer_category_ids(context)
        roots = {context.vocab.root_id(category_id) for category_id in category_ids} if category_ids is not None else (
            {context.vocab.root_id(context.intent.category_id)} if scoped is not None else None)
        for offer in self.pricing.category_offers():
            category = context.vocab.category(str(offer.CategoryId))
            if roots is not None and str(offer.CategoryId) not in roots:
                continue
            if category is not None and offer.AvailableProductCount and offer.MaxDiscountAmount > 0:
                lines.append(f"{category.name}: đang có sản phẩm giảm giá tự động, giảm tới {money(offer.MaxDiscountAmount)} "
                             f"(tối đa {int(offer.MaxDiscountPercent)}% giá niêm yết).")
        return lines

    @staticmethod
    def _coupon_line(coupon):
        value = Decimal(coupon["DiscountValue"])
        discount = f"{format(value.normalize(), 'f')}%" if coupon["DiscountType"] == "Percentage" else money(value)
        maximum = f", giảm tối đa {money(coupon['MaxDiscountAmount'])}" if coupon["MaxDiscountAmount"] is not None else ""
        end = datetime.fromisoformat(coupon["EndDate"]).astimezone(VIETNAM_TZ).strftime("%d/%m/%Y")
        return (f"{coupon['Code']}: giảm {discount}{maximum}, đơn tối thiểu {money(coupon['MinOrderValue'])}, "
                f"hạn {end}.")

    @staticmethod
    def _relevant_keys(question, specifications):
        """Specification keys the question asks about ("pin bao nhiêu" → Pin, "màn hình" → Kích thước màn hình),
        else the first four. Words of one to three key words are matched; generic single words are not."""
        text = fold(question)
        asked = []
        for key in specifications:
            words = fold(key).replace("/", " ").split()
            grams = {" ".join(words[i:j]) for i in range(len(words)) for j in range(i + 1, min(len(words), i + 3) + 1)}
            if any(len(gram) >= 3 and (" " in gram or gram not in KEY_STOPWORDS)
                   and re.search(r"\b" + re.escape(gram) + r"\b", text) for gram in grams):
                asked.append(key)
        return asked[:4] or list(specifications)[:4]

    def _worded(self, decision, context, fallback, notes, *, selected=(), order=()):
        """The model's message when every fact in it is grounded, else the backend's text."""
        if not decision.message:
            return fallback
        message, issues = check_message(decision.message, self._facts(context, selected, order))
        if not customer_text(message):
            issues.append("câu trả lời chỉ có lời kết mặc định")
        if issues:
            notes["GroundingIssues"] = issues[:5]
            return fallback
        notes["AnswerSource"] = "model"
        return message

    def _facts(self, context, selected, order):
        products = {}
        for key, public in context.products.items():
            texts = [public["Name"], public.get("Brand"), public.get("Category")]
            texts += [f"{v['VariantName']} {v['SalePrice']} "
                      f"giảm {v.get('DiscountAmount', '0')} đ, giá gốc {v.get('OriginalPrice', v['SalePrice'])} đ"
                      for v in public.get("Variants", [])]
            texts += [f"{k}: {v}" for k, v in (public.get("Specifications") or {}).items()]
            ranking = public.get("Ranking") or {}
            texts += ranking.get("Matched", []) + ranking.get("Gaps", [])
            if public.get("WarrantyMonths") is not None:
                texts.append(f"bảo hành {public['WarrantyMonths']} tháng")
            amounts = {int(Decimal(v[name])) for v in public.get("Variants", [])
                       for name in ("SalePrice", "OriginalPrice", "DiscountAmount") if v.get(name) is not None}
            products[key] = ProductFacts(key, public["Name"], public.get("Brand") or "", texts, amounts)
        discounted = False
        for detail, variant in selected:  # Current data of the products shown, read again in this transaction.
            facts = products.setdefault(str(detail.ProductId), ProductFacts(str(detail.ProductId), detail.Name,
                                                                            detail.Brand.Name))
            facts.texts += [f"{k}: {v}" for k, v in public_specifications(detail.Specifications).items()]
            facts.texts += [v.VariantName for v in detail.Variants] + [f"bảo hành {detail.WarrantyMonths} tháng"]
            facts.money |= {int(_price(v)) for v in detail.Variants}
            if variant is not None and variant.OriginalPrice is not None and variant.OriginalPrice > _price(variant):
                discounted = True
                facts.money.add(int(variant.OriginalPrice))
        intent, vocab = context.intent, context.vocab
        shared = [context.question, *(str(offer) for offer in context.offers)]
        shared += [line for lines in (context.policy or {}).values() for line in lines]
        # Names the analysis stands on (the inherited "hãng ASUS", the category) and products shown in earlier,
        # already checked answers may be named again; their numbers are not re-checked against this turn's data.
        shared += [row.name for row in (vocab.category(intent.category_id), vocab.brand(intent.brand_id),
                                        *map(vocab.brand, (*intent.soft_brand_ids, *intent.excluded_brand_ids))) if row]
        earlier = context.state.last_list() + context.state.last_focus()
        shared += [ref["ProductName"] for ref in earlier if ref.get("ProductName")]
        amounts = {int(v) for v in (intent.min_budget, intent.max_budget, intent.cheaper_than) if v is not None}
        amounts |= {int(Decimal(ref["Price"])) for ref in earlier if ref.get("Price")}
        if context.nearest:
            shared.append(f"{context.nearest['Name']} {context.nearest['Brand']}")
            amounts.add(int(Decimal(context.nearest["Price"])))
        for offer in context.offers:
            for name in ("DiscountValue", "MinOrderValue", "MaxDiscountAmount"):
                if offer.get(name) is not None:
                    amounts.add(int(Decimal(offer[name])))
        return Facts(list(products.values()), shared, amounts, tuple(b.name for b in context.vocab.brands),
                     bool(context.offer_scopes) or discounted or "Promotion" in (context.policy or {}), list(order))

    def _selected_variant(self, detail, selection, context):
        key = str(selection.product_id)
        eligible = self._variants(detail, context.filters[key])
        if selection.product_variant_id:
            known = {v["ProductVariantId"] for v in context.products[key]["Variants"]}
            if str(selection.product_variant_id) not in known:
                raise AiUnavailableError("AI chọn phiên bản chưa được tra cứu.", code="ai_ungrounded_output")
            eligible = [v for v in eligible if v.ProductVariantId == selection.product_variant_id]
        else:
            # "Máy thứ hai" keeps the version shown on its earlier card while it is still eligible.
            shown = next((ref.get("ProductVariantId") for ref in context.intent.references if ref["ProductId"] == key), None)
            preferred = [v for v in eligible if str(v.ProductVariantId) == shown]
            eligible = preferred or eligible
        return eligible[0] if eligible else None

    def _next_candidates(self, context, count):
        """When every product the model picked was already shown, take the next ranked new ones from the search."""
        loaded = []
        for key in context.search_order:
            if len(loaded) == count:
                break
            if self._excluded(key, context.products[key]["Name"], context):
                continue
            try:
                detail = self.catalog.get_product_detail(uuid.UUID(key))
            except NotFoundError:
                continue
            selection = PresentAnswerArguments.model_validate(
                {"intent": "recommend", "products": [{"product_id": key}]}).products[0]
            variant = self._selected_variant(detail, selection, context)
            if variant is not None:
                loaded.append((selection, detail, variant))
        return loaded

    def _rank_selection(self, loaded, context):
        """The model picks among ranked candidates; the formula on current price/stock decides their order."""
        if not self.ranking:
            return {}
        rows = [(selection, detail, variant) for selection, detail, variant in loaded if variant is not None]
        if not rows:
            return {}
        budget = context.filters[str(rows[0][0].product_id)].get("max_price")
        ordered, dropped = rank(context.ranking, [self._candidate(detail, variant, context) for _, detail, variant in rows],
                                budget_max=budget, dropped=context.dropped)
        evaluations = {candidate.product_id: evaluation for candidate, evaluation in ordered
                       if evaluation.score is not None}
        if not evaluations:
            return {}
        reorder = not context.intent.explicit_order  # "Rẻ nhất" keeps the price order; reasons are still shown.
        if reorder:
            position = {candidate.product_id: index for index, (candidate, _) in enumerate(ordered)}
            loaded.sort(key=lambda item: position.get(str(item[0].product_id), len(position)))
        context.ranking_log = {
            "Ordered": reorder, "Needs": list(context.ranking.needs), "SoftBrands": len(context.ranking.soft_brand_ids),
            "Dropped": sorted(dropped),
            "Products": [{"ProductId": str(selection.product_id), "Score": round(evaluations[str(selection.product_id)].score, 4),
                          "Parts": {k: round(v, 4) for k, v in evaluations[str(selection.product_id)].parts.items()}}
                         for selection, _, _ in loaded if str(selection.product_id) in evaluations],
        }
        return evaluations

    @staticmethod
    def _reasons(evaluation, filters):
        """Why a recommended product fits, from confirmed catalog facts and the active criteria only."""
        if evaluation is None:
            return []
        why = list(evaluation.matched[:4])
        if "B" in evaluation.parts:
            why.append(f"trong ngân sách {money(filters['max_price'])}")
        if evaluation.soft_brand:
            why.append("đúng hãng bạn ưu tiên")
        lines = [f"- Phù hợp: {', '.join(why)}."] if why else []
        if evaluation.gaps:
            lines.append(f"- Lưu ý: {', '.join(evaluation.gaps[:3])}.")
        return lines
