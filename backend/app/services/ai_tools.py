"""Read-only catalog tools and server-rendered facts; no ORM/admin objects leave this boundary."""

import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from app.core.search_text import fold
from app.schemas.ai_chat import (GetProductArguments, ListOffersArguments, PresentAnswerArguments,
                                  SearchProductsArguments)

from .ai_grounding import Facts, ProductFacts, check_message
from .ai_intent import (CATEGORY_ALIASES, BrandInfo, CategoryInfo, ConversationState, ShoppingIntent, Vocabulary,
                        analyze, budget_ceiling, budget_floor, soften_category)  # noqa: F401 (budget_* stay importable here)
from .catalog import BrandService, CategoryService, ProductService
from .exceptions import AiUnavailableError, BusinessRuleError, NotFoundError
from .pricing import PricingService
from .recommendation import (CANDIDATE_MAX, CANDIDATE_PAGE, NEEDS, RESULT_LIMIT, Candidate, RankingCriteria,
                             detect_needs, model_key, rank)

TOOL_SCHEMAS = {
    "search_products": (SearchProductsArguments, "Tìm sản phẩm đang bán và còn hàng. Tách hãng, danh mục và giá thành trường riêng; keyword chỉ chứa tên/model, không đưa nhu cầu/ngân sách vào keyword. category/brand nhận tên hoặc slug công khai. Backend tự áp điều kiện của khách (kể cả điều kiện kế thừa từ lượt trước) và tự loại sản phẩm đã giới thiệu khi khách xin thêm lựa chọn. Khi Ranked=true, Ranking.Rank 1 phù hợp nhất theo nhu cầu, ngân sách và hãng ưu tiên; Matched/Gaps là bằng chứng từ thông số."),
    "get_product": (GetProductArguments, "Đọc sản phẩm và thông số hiện tại theo product_id/slug, product_ids (2–3 sản phẩm cần so sánh, đọc trong một lần gọi), hoặc rank = thứ tự trong danh sách đã gợi ý gần nhất (chưa có danh sách thì là thứ tự trong kết quả search_products gần nhất). Không cần gọi nếu sản phẩm đã có trong dữ liệu tham chiếu của lượt này."),
    "list_offers": (ListOffersArguments, "Đọc coupon công khai còn hiệu lực, tùy chọn theo product_id. Giá sản phẩm đã bao gồm giảm tự động; coupon còn điều kiện giỏ hàng."),
    "present_answer": (PresentAnswerArguments, "Kết thúc lượt. intent và products (product_id, product_variant_id, specification_keys tùy chọn) phải là sản phẩm có thật trong dữ liệu lượt này; backend dựng tối đa ba thẻ với giá/tồn kho hiện tại. message là câu trả lời tự nhiên bằng tiếng Việt cho khách: chỉ dùng số liệu có trong dữ liệu lượt này, nêu sản phẩm theo đúng thứ tự products. Hỏi thêm bằng intent=clarify; trò chuyện chung dùng intent=chat; đơn/bảo hành/đổi trả dùng handoff."),
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
HANDOFF = ("Trợ lý AI hỗ trợ tư vấn sản phẩm và ưu đãi. Với đơn hàng, thanh toán, bảo hành hoặc đổi trả, bạn vui lòng "
           "xem thông tin trong tài khoản hoặc trang chính sách của VieTech.")
CHAT = ("Mình là trợ lý tư vấn sản phẩm của VieTech. Bạn đang cần tìm điện thoại, laptop hay phụ kiện nào, "
        "dùng cho việc gì và ngân sách khoảng bao nhiêu để mình gợi ý nhé?")


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


def money(value):
    amount = Decimal(str(value))
    result = f"{amount:,.0f}" if amount == amount.to_integral_value() else f"{amount:,.2f}"
    return result.replace(",", "_").replace(".", ",").replace("_", ".") + " đ"


def public_specifications(specifications):
    """Bounded flattening of public technical data; preserves values instead of inferring specs."""
    result = {}
    visited = 0

    def collect(data, prefix="", depth=0):
        nonlocal visited
        if not isinstance(data, dict) or depth > 3:
            return
        for key, value in data.items():
            visited += 1
            if len(result) >= 12 or visited > 100:
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


def _price(variant):
    return variant.SalePrice if variant.SalePrice is not None else variant.Price


class AiTools:
    """Called inside the orchestrator's short authorized transaction; never commits or calls the model."""

    def __init__(self, session, *, clock, ranking=True):
        self.catalog = ProductService(session, clock=clock)
        self.categories = CategoryService(session, clock=clock)
        self.brands = BrandService(session, clock=clock)
        self.pricing = PricingService(session, clock=clock)
        self.clock = clock
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
        if context.intent.clarification:
            return
        try:
            if context.intent.references:
                ids = [uuid.UUID(ref["ProductId"]) for ref in context.intent.references]
                details = self.catalog.get_product_details(ids)
                for ref in context.intent.references:
                    detail = details.get(uuid.UUID(ref["ProductId"]))
                    if detail is not None:
                        context.referenced.append(self._read(detail, context, variant_limit=4))
            if context.intent.recommending and context.intent.category_id:
                text = fold(context.question)
                sort = next((sort for terms, sort in PREFETCH_SORTS if any(term in text for term in terms)), "price_asc")
                context.prefetched = self.search_products(SearchProductsArguments(sort=sort), context)
        except (BusinessRuleError, NotFoundError):
            pass  # The model can still read the catalog with its own tool calls.

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
        if filters.get("category_ids") and str(detail.CategoryId) not in filters["category_ids"]:
            return []
        rows = []
        for variant in detail.Variants:
            price = _price(variant)
            if (not variant.IsActive or variant.StockQuantity <= 0
                    or (filters.get("min_price") is not None and price < Decimal(str(filters["min_price"])))
                    or (filters.get("max_price") is not None and price > Decimal(str(filters["max_price"])))):
                continue
            rows.append(variant)
        return sorted(rows, key=lambda v: (_price(v), str(v.ProductVariantId)))

    def _public_product(self, detail, filters, *, summary=False, variant_limit=12):
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
            facts["Specifications"] = public_specifications(detail.Specifications)
            facts["WarrantyMonths"] = detail.WarrantyMonths
        return facts

    def _excluded(self, product_id, name, context):
        intent = context.intent
        return bool(intent and intent.recommending and (
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
        if not brand_id and args.brand:
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
                    # Four variants each keeps three products well under the 14.000-character tool result limit.
                    products.append(self._read(self.catalog.get_product_detail(product_id), context, variant_limit=4))
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

    def _read(self, detail, context, *, variant_limit=12):
        key = str(detail.ProductId)
        # A detail lookup must not widen the filters used to select this product in the same turn.
        filters = context.filters.get(key)
        if filters is None:
            filters = self._constraints(context)
        public = self._public_product(detail, filters, variant_limit=variant_limit)
        context.products[key], context.filters[key] = public, filters
        return public

    def list_offers(self, args, context):
        coupons = self.pricing.public_coupons(product_id=args.product_id)
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
        """Reload critical facts and return (text, cards, references, notes) from current public services.

        Gemini's `message` is shown only if every fact in it is grounded (ai_grounding); otherwise the backend's own
        wording is used. Cards, prices and stock always come from the backend.
        """
        self._ensure(context)
        notes = {"AnswerIntent": decision.intent, "AnswerSource": "backend"}
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
            loaded = self._next_candidates(context, max_products)
            notes["Replaced"] = True
            if not loaded:
                return self._no_results_text(context), [], [], {**notes, "AnswerIntent": "no_results"}
        evaluations = self._rank_selection(loaded, context) if intent == "recommend" else {}
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
            lines.append(f"{rank_}. {detail.Name}")
            if variant:
                lines.append(f"Phiên bản: {variant.VariantName}; giá: {money(price)}; còn hàng.")
                images = detail.VariantImages.get(variant.ProductVariantId) or detail.Images
                image = next((image for image in images if image.IsDefault), images[0] if images else None)
                card = {"ProductId": key, "Slug": detail.Slug, "ProductName": detail.Name,
                    "ProductVariantId": str(variant.ProductVariantId), "VariantName": variant.VariantName,
                    "Price": str(price), "OriginalPrice": str(variant.OriginalPrice if variant.OriginalPrice is not None else variant.Price),
                    "ImageUrl": image.ImageUrl if image else None,
                    "InStock": True, "Rank": rank_, "SnapshotAt": self.clock().isoformat()}
                if len(cards) < max_products:
                    cards.append(card)
                lines.extend(self._reasons(evaluations.get(key), filters))
            else:
                lines.append("Hiện không có phiên bản còn hàng thỏa điều kiện đã tra cứu.")
            if intent in ("product", "compare"):
                facts = self._public_product(detail, filters).get("Specifications", {})
                keys = selection.specification_keys or self._relevant_keys(context.question, facts)
                known = context.products[key].get("Specifications", {})
                if selection.specification_keys and any(name not in known for name in keys):
                    raise AiUnavailableError("AI chọn thông số chưa được tra cứu.", code="ai_ungrounded_output")
                lines.extend(f"{name}: {facts.get(name, 'catalog chưa có thông tin')}" for name in keys)
                lines.append(f"Bảo hành: {detail.WarrantyMonths} tháng.")
        if evaluations and "battery" in context.ranking.needs:
            lines.append("Dung lượng pin chỉ là tín hiệu từ thông số; thời lượng thực tế tùy cách sử dụng.")
        if evaluations and "camera" in context.ranking.needs:
            lines.append("Camera được đánh giá theo chống rung/ống kính ghi trong thông số, không theo số MP.")
        fallback = "\n".join([self._intro(intent, context, len(products)), *lines]).strip()
        if intent == "recommend" and products:
            fallback += "\nBạn muốn mình so sánh chi tiết các mẫu này hoặc xem thêm lựa chọn khác không?"
        order = [str(detail.ProductId) for detail, _ in products]
        text = self._worded(decision, context, fallback, notes, selected=products, order=order)
        wanted = context.intent.requested_count
        if (intent == "recommend" and context.intent.intent == "recommend_more" and wanted
                and len(cards) < min(wanted, max_products) and f"{len(cards)} mẫu" not in text):
            # "Thêm 3 mẫu" when only two new ones exist: say so rather than letting it look like a full answer.
            text += f"\nHiện chỉ còn {len(cards)} mẫu mới phù hợp với điều kiện này."
        return text, cards, references, notes

    def _intro(self, intent, context, count):
        if intent == "compare":
            return "So sánh nhanh theo thông số hiện có:"
        if intent == "product":
            return "Thông tin bạn hỏi:" if count else ""
        conditions = self._conditions(context)
        if context.intent.intent == "recommend_more":
            return f"Ngoài các mẫu đã giới thiệu, đây là {count} lựa chọn khác phù hợp{conditions}:"
        return f"Đây là {count} lựa chọn phù hợp nhất hiện có tại VieTech{conditions}:"

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
        return f" với {'; '.join(parts)}" if parts else ""

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
        for scope in context.offer_scopes:
            for coupon in self.pricing.public_coupons(product_id=uuid.UUID(scope) if scope else None):
                coupons[coupon.Code] = coupon
        lines = ["Các mã ưu đãi công khai hiện có:"]
        for coupon in list(coupons.values())[:5]:
            discount = f"{format(coupon.DiscountValue.normalize(), 'f')}%" if coupon.DiscountType == "Percentage" else money(coupon.DiscountValue)
            maximum = f", giảm tối đa {money(coupon.MaxDiscountAmount)}" if coupon.MaxDiscountAmount is not None else ""
            lines.append(f"• {coupon.Code}: giảm {discount}{maximum}; đơn tối thiểu {money(coupon.MinOrderValue)}; "
                         f"hạn {coupon.EndDate.isoformat()}; tối đa {coupon.PerCustomerUsageLimit} lượt/khách.")
        if not coupons:
            lines = ["VieTech hiện chưa tìm thấy mã ưu đãi công khai còn hiệu lực trong phạm vi vừa tra cứu."]
        lines.append("Điều kiện và khả năng áp dụng được kiểm tra lại tại giỏ hàng; giá sản phẩm đã tính ưu đãi tự động phù hợp.")
        return "\n".join(lines)

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
        if issues:
            notes["GroundingIssues"] = issues[:5]
            return fallback
        notes["AnswerSource"] = "model"
        return message

    def _facts(self, context, selected, order):
        products = {}
        for key, public in context.products.items():
            texts = [public["Name"], public.get("Brand"), public.get("Category")]
            texts += [f"{v['VariantName']} {v['SalePrice']}" for v in public.get("Variants", [])]
            texts += [f"{k}: {v}" for k, v in (public.get("Specifications") or {}).items()]
            ranking = public.get("Ranking") or {}
            texts += ranking.get("Matched", []) + ranking.get("Gaps", [])
            if public.get("WarrantyMonths") is not None:
                texts.append(f"bảo hành {public['WarrantyMonths']} tháng")
            amounts = {int(Decimal(v["SalePrice"])) for v in public.get("Variants", [])}
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
                     bool(context.offer_scopes) or discounted, list(order))

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
        lines = [f"Phù hợp: {'; '.join(why)}."] if why else []
        if evaluation.gaps:
            lines.append(f"Lưu ý: {'; '.join(evaluation.gaps[:3])}.")
        return lines
