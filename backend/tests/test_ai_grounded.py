"""Read-only AI tools -> real catalog/pricing services -> isolated SQLite, with scripted model calls."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import JSON, MetaData, create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.ai_config import AiSettings
from app.core.auth_state import MemoryStateStore
from app.integrations.ai import ChatCompletion, ToolCall
from app.models import (Brand, Category, Conversation, Coupon, Message, Product, ProductImage, ProductVariant,
                        Promotion, PromotionCategory, PromotionProduct, User)
from app.schemas.ai_chat import AiMessageCancel, AiMessageCreate
from app.services.actor import Actor
from app.services.ai_chat import FINAL_NOTE, REPAIR_NOTE, AiChatService
from app.services.ai_tools import budget_ceiling, budget_floor
from app.services.exceptions import AiUnavailableError
from tests.sqlite_schema import AI_SIGNAL_TABLES, create_tables


def call(name, **args):
    return ToolCall("call_" + uuid.uuid4().hex, name, json.dumps(args))


class ScriptedModel:
    def __init__(self, steps, counters):
        self.steps, self.counters, self.calls = list(steps), counters, []

    def complete(self, messages, **kwargs):
        assert self.counters["connections"] == 0, "Connection held while model is running"
        self.calls.append((list(messages), kwargs))
        step = self.steps.pop(0)
        if callable(step):
            step = step(messages)
        if isinstance(step, dict):
            return ChatCompletion(json.dumps(step), "scripted-model", 10, 5)
        return ChatCompletion("", "scripted-model", 10, 5, tuple(step))


@pytest.fixture
def grounded_shop():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    counters = {"connections": 0}

    @event.listens_for(engine, "connect")
    def functions(connection, _):
        connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat(" "))
        connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)
        connection.create_function("lower", 1, lambda value: value.lower() if value else value, deterministic=True)
        connection.create_function("translate", 3, lambda value, source, target:
                                   value.translate(str.maketrans(source, target)) if value else value, deterministic=True)

    event.listen(engine, "checkout", lambda *_: counters.update(connections=counters["connections"] + 1))
    event.listen(engine, "checkin", lambda *_: counters.update(connections=counters["connections"] - 1))
    metadata = MetaData()
    models = (User, Conversation, Message, Brand, Category, Product, ProductVariant, ProductImage,
              Promotion, PromotionCategory, PromotionProduct, Coupon)
    for model in models:
        table = model.__table__.to_metadata(metadata)
        for column in table.c:
            if isinstance(column.type, JSONB):
                column.type = JSON()
    metadata.create_all(engine)
    create_tables(engine, AI_SIGNAL_TABLES)
    now = SimpleNamespace(value=datetime(2026, 10, 22, 8, tzinfo=timezone.utc))
    with Session(engine) as db:
        owner = User(Email="private-profile@example.test", PhoneNumber="0912345678", PasswordHash="private-password",
                     FullName="Private Customer Name", Role="Customer", AccountStatus="Active")
        category = Category(Name="Laptop", Slug="laptop")
        asus = Brand(Name="ASUS", Slug="asus")
        lenovo = Brand(Name="Lenovo", Slug="lenovo")
        db.add_all([owner, category, asus, lenovo]); db.flush()
        cid = uuid.uuid4()
        db.add(Conversation(ConversationId=cid, CustomerId=owner.UserId, Mode="AI", Status="Open"))
        products, variants = {}, {}
        for name, brand, price, stock, status, deleted in [
            ("asus-zen", asus, 18000000, 5, "Active", False),
            ("asus-vivo", asus, 21000000, 4, "Active", False),
            ("asus-ghost", asus, 15000000, 0, "Active", False),
            ("lenovo-idea", lenovo, 17000000, 3, "Active", False),
            ("asus-draft", asus, 12000000, 5, "Draft", False),
            ("asus-deleted", asus, 12000000, 5, "Active", True),
        ]:
            product = Product(Name=name, Slug=name, BrandId=brand.BrandId, CategoryId=category.CategoryId,
                              Status=status, IsDeleted=deleted, WarrantyMonths=24,
                              Specifications={"RAM": "16 GB", "SSD": "512 GB"})
            db.add(product); db.flush()
            variant = ProductVariant(ProductId=product.ProductId, Sku=name, VariantName="16 GB / 512 GB",
                                     Price=price, CostPrice=price // 2, StockQuantity=stock)
            db.add(variant); db.flush()
            products[name], variants[name] = str(product.ProductId), str(variant.ProductVariantId)
        db.add(ProductVariant(ProductId=uuid.UUID(products["asus-ghost"]), Sku="ghost-expensive", VariantName="Available",
                              Price=25000000, CostPrice=10000000, StockQuantity=3))
        actor = Actor(owner.UserId, "Customer")
        db.commit()
    state = MemoryStateStore()
    sessions = []

    def service(steps, **kwargs):
        session = Session(engine, autoflush=False)
        sessions.append(session)
        model = ScriptedModel(steps, counters)
        return AiChatService(session, settings=AiSettings(api_key="test", timeout_seconds=20), model=model, state=state,
                             clock=lambda: now.value, **kwargs), model

    yield SimpleNamespace(engine=engine, cid=cid, actor=actor, products=products, variants=variants,
                          service=service, now=now, counters=counters)
    for session in sessions:
        session.close()
    engine.dispose()


def ask(shop, svc, content="Laptop ASUS dưới 20 triệu để học lập trình"):
    return svc.ask(shop.actor, shop.cid, AiMessageCreate(ClientRequestId=uuid.uuid4(), Content=content))


def finish(intent, *ids):
    return {"intent": intent, "products": [{"product_id": id_} for id_ in ids]}


def test_cancelled_turn_never_starts_a_repair_model_round(grounded_shop):
    s = grounded_shop
    data = AiMessageCreate(ClientRequestId=uuid.uuid4(), Content="Tôi cần laptop")
    other, _ = s.service([])

    def cancel_during_call(_messages):
        other.cancel(s.actor, s.cid, data.ClientRequestId, AiMessageCancel(Content=data.Content))
        raise AiUnavailableError("Invalid output", code="ai_invalid_output")

    svc, model = s.service([cancel_during_call])
    from app.services.exceptions import ConflictError
    with pytest.raises(ConflictError):
        svc.ask(s.actor, s.cid, data)
    assert len(model.calls) == 1
    assert svc.get_status(s.actor, s.cid, data.ClientRequestId).Status == "Cancelled"


@pytest.mark.parametrize("question,expected", [
    ("Laptop dưới 20 triệu", 20000000), ("không quá 20,5 triệu", 20500000),
    ("tối đa 20tr500", 20500000), ("ngân sách 20.000.000 đồng", 20000000),
    ("khoảng 15tr", 15000000), ("RAM 16 GB SSD 512 GB", None),
])
def test_budget_units(question, expected):
    assert budget_ceiling(question) == expected


@pytest.mark.parametrize("question,lower,upper", [
    ("Laptop từ 18 đến 20 triệu", 18000000, 20000000),
    ("Khoảng 18 triệu đến 20 triệu", 18000000, 20000000),
    ("Laptop 18–20 triệu", 18000000, 20000000),
    ("Laptop từ 18.000.000 đến 20.000.000 đồng", 18000000, 20000000),
    ("Laptop ít nhất 18tr500, tối đa 20 triệu", 18500000, 20000000),
    ("Laptop tối thiểu 18,5 triệu", 18500000, None),
    ("Máy có RAM từ 8 đến 16 GB", None, None),
    ("Laptop dưới 20..5 triệu", None, None),
])
def test_budget_ranges_and_malformed_numbers(question, lower, upper):
    assert (budget_floor(question), budget_ceiling(question)) == (lower, upper)


def test_excluded_brand_is_kept_on_followup_and_can_be_explicitly_reintroduced(grounded_shop):
    s = grounded_shop
    seen = []

    def choose_lenovo(messages):
        result = json.loads(messages[-1]["content"])
        seen.append(result)
        assert {p["ProductId"] for p in result["Products"]} == {s.products["lenovo-idea"]}
        return finish("recommend", s.products["lenovo-idea"])

    def nothing_new(messages):
        result = json.loads(messages[-1]["content"])
        seen.append(result)
        return finish("no_results")

    def choose_asus(messages):
        result = json.loads(messages[-1]["content"])
        assert result["Constraints"]["excluded_brand_ids"] == []
        return finish("recommend", s.products["asus-zen"])

    svc, _ = s.service([[call("search_products", category="Laptop")], choose_lenovo,
                        [call("search_products", category="Laptop")], nothing_new,
                        [call("search_products", category="Laptop", brand="ASUS")], choose_asus])
    ask(s, svc, "Laptop không chọn ASUS dưới 20 triệu")
    more = ask(s, svc, "Có máy nào khác như máy thứ nhất không?")
    # The exclusion is inherited, and the only eligible laptop was already shown: it is not offered again.
    assert seen[0]["Constraints"]["excluded_brand_ids"] == seen[1]["Constraints"]["excluded_brand_ids"]
    assert seen[1]["Constraints"]["excluded_brand_ids"] and seen[1]["Products"] == []
    assert seen[1]["AlreadyShownExcluded"] == 1
    assert more.AiMessages[0].Content.startswith("Mình đã giới thiệu hết 1 mẫu laptop")
    result = ask(s, svc, "Máy thứ nhất ổn, nhưng lần này chỉ ASUS cũng được")
    assert result.AiMessages[1].Metadata["ProductName"] == "asus-zen"


@pytest.mark.parametrize("question,args,expected,price", [
    ("Laptop từ 20 đến 22 triệu", {"category": "Laptop", "max_price": 22000000}, "asus-vivo", 21000000),
    ("Laptop không chọn ASUS dưới 20 triệu", {"category": "Laptop"}, "lenovo-idea", 17000000),
])
def test_price_and_brand_filters_apply_before_the_candidate_limit(grounded_shop, question, args, expected, price):
    s = grounded_shop
    with Session(s.engine) as db:
        template = db.get(Product, uuid.UUID(s.products["asus-zen"]))
        for position in range(20):
            product = Product(Name=f"cheap-{position}", Slug=f"cheap-{position}", BrandId=template.BrandId,
                CategoryId=template.CategoryId, Status="Active", WarrantyMonths=24, Specifications={})
            db.add(product); db.flush()
            db.add(ProductVariant(ProductId=product.ProductId, Sku=f"cheap-{position}", VariantName="Base",
                                  Price=10000000, CostPrice=5000000, StockQuantity=3))
        db.commit()

    def choose(messages):
        result = json.loads(messages[-1]["content"])
        assert {p["ProductId"] for p in result["Products"]} == {s.products[expected]}
        return finish("recommend", s.products[expected])

    # The user's range wins even when the model omits min_price.
    svc, _ = s.service([[call("search_products", **args)], choose])
    result = ask(s, svc, question)
    assert Decimal(result.AiMessages[1].Metadata["Price"]) == price


def test_both_price_bounds_and_stock_must_match_the_same_variant(grounded_shop):
    s = grounded_shop
    with Session(s.engine) as db:
        db.add_all([
            ProductVariant(ProductId=uuid.UUID(s.products["lenovo-idea"]), Sku="lenovo-expensive", VariantName="Large",
                           Price=25000000, CostPrice=10000000, StockQuantity=3),
            ProductVariant(ProductId=uuid.UUID(s.products["asus-vivo"]), Sku="vivo-sold-out", VariantName="Sold out",
                           Price=19000000, CostPrice=10000000, StockQuantity=0),
        ])
        db.commit()

    def choose(messages):
        result = json.loads(messages[-1]["content"])
        assert {p["ProductId"] for p in result["Products"]} == {s.products["asus-zen"]}
        return finish("recommend", s.products["asus-zen"])

    svc, _ = s.service([[call("search_products", category="Laptop")], choose])
    assert ask(s, svc, "Laptop từ 18 đến 20 triệu").Status == "Completed"


def test_detail_lookup_preserves_the_search_price_range(grounded_shop):
    s = grounded_shop
    with Session(s.engine) as db:
        db.add(ProductVariant(ProductId=uuid.UUID(s.products["asus-zen"]), Sku="cheaper-variant",
            VariantName="Cheaper", Price=16000000, CostPrice=8000000, StockQuantity=3))
        db.commit()

    def read_details(messages):
        result = json.loads(messages[-1]["content"])
        assert result["Products"][0]["Variants"][0]["SalePrice"] == "18000000.00"
        return [call("get_product", product_id=s.products["asus-zen"])]

    svc, _ = s.service([[call("search_products", category="Laptop", min_price=18000000, max_price=20000000)],
                        read_details, finish("recommend", s.products["asus-zen"])])
    result = ask(s, svc, "Tư vấn laptop phù hợp cho tôi")
    assert Decimal(result.AiMessages[1].Metadata["Price"]) == 18000000


def test_followup_keeps_range_until_the_customer_reduces_or_clears_budget(grounded_shop):
    s = grounded_shop
    seen = []

    def choose(messages):
        result = json.loads(messages[-1]["content"])
        seen.append(result["Constraints"])
        if not result["Products"]:  # "Mẫu tương tự" never repeats the one product already shown.
            return finish("no_results")
        return finish("recommend", result["Products"][0]["ProductId"])

    svc, _ = s.service([[call("search_products", category="Laptop")], choose,
                        [call("search_products", category="Laptop")], choose,
                        [call("search_products", category="Laptop")], choose,
                        [call("search_products", category="Laptop")], choose])
    ask(s, svc, "Laptop từ 18 đến 20 triệu")
    ask(s, svc, "Máy thứ nhất có mẫu tương tự không?")
    assert (seen[1]["min_price"], seen[1]["max_price"]) == (18000000, 20000000)
    ask(s, svc, "Máy thứ nhất hơi đắt, giờ tối đa 17 triệu")
    assert (seen[2]["min_price"], seen[2]["max_price"]) == (None, 17000000)
    ask(s, svc, "Với máy thứ nhất, bỏ giới hạn ngân sách đi")
    assert (seen[3]["min_price"], seen[3]["max_price"]) == (None, None)


def test_hard_budget_brand_stock_public_fields_and_cards(grounded_shop):
    s = grounded_shop

    def choose(messages):
        result = json.loads(messages[-1]["content"])
        assert result["Constraints"]["max_price"] == 20000000
        assert {p["ProductId"] for p in result["Products"]} == {s.products["asus-zen"]}
        assert "CostPrice" not in str(result) and "private-profile" not in str(messages)
        return [call("present_answer", **finish("recommend", s.products["asus-zen"]))]

    svc, model = s.service([[call("search_products", category="laptop", brand="lenovo", max_price=30000000,
                                 keyword="học lập trình")], choose])
    response = ask(s, svc)
    assert response.Status == "Completed" and len(response.AiMessages) == 2
    card = response.AiMessages[1]
    assert card.MessageType == "Product" and Decimal(card.Metadata["Price"]) == 18000000
    assert card.Metadata["Slug"] == "asus-zen" and card.Metadata["InStock"] is True
    assert "18.000.000 đ" in response.AiMessages[0].Content
    assert len(model.calls) == 2
    replay = svc.get_status(s.actor, s.cid, response.ClientRequestId)
    assert [m.MessageId for m in replay.AiMessages] == [m.MessageId for m in response.AiMessages]


def test_soft_brand_is_not_forced_and_price_is_rechecked(grounded_shop):
    s = grounded_shop

    def change_price(messages):
        result = json.loads(messages[-1]["content"])
        assert {s.products["asus-zen"], s.products["lenovo-idea"]} <= {p["ProductId"] for p in result["Products"]}
        with Session(s.engine) as db:
            db.get(ProductVariant, uuid.UUID(s.variants["lenovo-idea"])).Price = 19000000
            db.commit()
        return finish("recommend", s.products["lenovo-idea"])

    svc, _ = s.service([[call("search_products", category="Laptop", max_price=20000000)], change_price])
    response = ask(s, svc, "Laptop dưới 20 triệu, ưu tiên ASUS nhưng Lenovo cũng được")
    assert Decimal(response.AiMessages[1].Metadata["Price"]) == 19000000
    assert "19.000.000 đ" in response.AiMessages[0].Content


def test_the_question_category_wins_and_english_category_names_are_understood(grounded_shop):
    s = grounded_shop
    seen = []

    def keep(messages):
        seen.append(json.loads(messages[-1]["content"]))
        return [call("search_products", category="gadgets", max_price=20000000)]

    def clarify(messages):
        seen.append(json.loads(messages[-1]["content"]))
        return {"intent": "clarify", "clarification": "category"}

    # Stage 10.7: a guessed English name used to fail the search and end in "which category?".
    # The question without a category runs first: later turns inherit the category from the conversation.
    laptops = {s.products["asus-zen"], s.products["lenovo-idea"]}
    svc, _ = s.service([[call("search_products", category="laptops", max_price=20000000)], keep, clarify])
    assert ask(s, svc, "Máy nào dưới 20 triệu đáng mua?").Status == "Completed"
    assert {p["ProductId"] for p in seen[0]["Products"]} == laptops
    assert seen[1]["error"] == "ai_unknown_filter" and "Laptop" in seen[1]["message"]
    s.now.value += timedelta(seconds=1)
    svc, _ = s.service([[call("search_products", category="phone", max_price=20000000)],
                        lambda m: (seen.append(json.loads(m[-1]["content"])), finish("no_results"))[1]])
    assert ask(s, svc, "Laptop dưới 20 triệu").Status == "Completed"
    assert {p["ProductId"] for p in seen[2]["Products"]} == laptops


def test_a_soft_brand_passed_by_the_model_is_not_a_filter(grounded_shop):
    s = grounded_shop
    seen = []

    def choose(messages):
        seen.append(json.loads(messages[-1]["content"]))
        return finish("recommend", s.products["asus-zen"])

    svc, _ = s.service([[call("search_products", category="laptop", brand="ASUS", max_price=20000000)], choose])
    assert ask(s, svc, "Laptop dưới 20 triệu, ưu tiên ASUS nhưng Lenovo cũng được").Status == "Completed"
    assert s.products["lenovo-idea"] in {p["ProductId"] for p in seen[0]["Products"]}
    assert seen[0]["Products"][0]["Ranking"]["Parts"]["T"] == 1.0  # Both named brands are scored, none filtered.


def test_soft_other_preferences_do_not_erase_explicit_brand_or_budget(grounded_shop):
    s = grounded_shop

    def choose(messages):
        result = json.loads(messages[-1]["content"])
        assert result["Constraints"]["max_price"] == 20000000
        assert {p["ProductId"] for p in result["Products"]} == {s.products["asus-zen"]}
        return finish("recommend", s.products["asus-zen"])

    svc, _ = s.service([[call("search_products", category="laptop", max_price=50000000)], choose])
    assert ask(s, svc, "Laptop chỉ ASUS, ưu tiên nhẹ, không giới hạn RAM nhưng không quá 20 triệu").Status == "Completed"


@pytest.mark.parametrize("mutation", ["out_of_stock", "over_budget", "deleted"])
def test_changed_availability_never_creates_invalid_cards(grounded_shop, mutation):
    s = grounded_shop

    def change(_):
        with Session(s.engine) as db:
            variant = db.get(ProductVariant, uuid.UUID(s.variants["asus-zen"]))
            if mutation == "out_of_stock": variant.StockQuantity = 0
            if mutation == "over_budget": variant.Price = 30000000
            if mutation == "deleted": db.get(Product, uuid.UUID(s.products["asus-zen"])).IsDeleted = True
            db.commit()
        return finish("recommend", s.products["asus-zen"])

    svc, _ = s.service([[call("search_products", category="laptop", max_price=20000000)], change])
    response = ask(s, svc)
    assert [m.MessageType for m in response.AiMessages] == ["Text"]
    assert "18.000.000" not in response.AiMessages[0].Content


def test_product_details_comparison_and_rank_reference(grounded_shop):
    s = grounded_shop
    first, _ = s.service([[call("search_products", category="laptop", max_price=20000000)],
                          finish("recommend", s.products["lenovo-idea"], s.products["asus-zen"])])
    response = ask(s, first, "Laptop dưới 20 triệu")
    assert [m.Metadata["ProductId"] for m in response.AiMessages[1:]] == [s.products["lenovo-idea"], s.products["asus-zen"]]
    s.now.value += timedelta(seconds=1)
    second, model = s.service([[call("get_product", rank=2)], finish("product", s.products["asus-zen"])])
    detail = ask(s, second, "Máy thứ hai có RAM bao nhiêu?")
    assert "RAM: 16 GB" in detail.AiMessages[0].Content
    assert detail.AiMessages[1].Metadata["ProductId"] == s.products["asus-zen"]
    assert "Tham chiếu thẻ" in str(model.calls[0][0])
    s.now.value += timedelta(seconds=1)
    comparison, _ = s.service([[call("get_product", product_id=s.products["asus-zen"]),
                               call("get_product", product_id=s.products["lenovo-idea"])],
                              finish("compare", s.products["asus-zen"], s.products["lenovo-idea"])])
    comparison.settings = AiSettings(api_key="test", max_products=1)
    compared = ask(s, comparison, "So sánh asus-zen và lenovo-idea")
    assert "asus-zen" in compared.AiMessages[0].Content and "lenovo-idea" in compared.AiMessages[0].Content
    assert len(compared.AiMessages) == 2  # Two products compared, one card configured.


def test_rank_without_previous_cards_means_the_latest_search_order(grounded_shop):
    s = grounded_shop
    seen = []

    def read_first(messages):
        seen.append(json.loads(messages[-1]["content"]))
        return [call("get_product", rank=1)]

    def answer(messages):
        seen.append(json.loads(messages[-1]["content"]))
        return finish("recommend", seen[-1]["ProductId"])

    # Stage 10.7: the model reads rank as this turn's search position; that lookup used to fail.
    svc, _ = s.service([[call("search_products", category="laptop", max_price=20000000)], read_first, answer])
    response = ask(s, svc, "Laptop dưới 20 triệu")
    assert seen[1]["ProductId"] == seen[0]["Products"][0]["ProductId"]
    assert response.AiMessages[1].Metadata["ProductId"] == seen[0]["Products"][0]["ProductId"]
    # Only one product was shown: "máy thứ ba" is asked back by the backend, without guessing or a model call.
    s.now.value += timedelta(seconds=1)
    missing, model = s.service([])
    answer = ask(s, missing, "Máy thứ ba thì sao?")
    shown = response.AiMessages[1].Metadata["ProductName"]
    assert model.calls == [] and answer.AiMessages[0].Content.startswith(f"Danh sách vừa rồi chỉ có 1 mẫu: 1. {shown}")
    # A model asking for a rank the list does not have still gets the tool error.
    s.now.value += timedelta(seconds=1)
    unknown, model = s.service([[call("get_product", rank=3)], {"intent": "clarify", "clarification": "products"}])
    ask(s, unknown, "Có gì khác biệt giữa các bản không?")
    assert json.loads(model.calls[1][0][-1]["content"])["error"] == "ai_reference_not_found"


def test_a_comparison_reads_its_products_in_one_call(grounded_shop):
    s = grounded_shop
    seen = []

    def compare(messages):
        seen.append(json.loads(messages[-1]["content"]))
        return finish("compare", s.products["asus-zen"], s.products["lenovo-idea"])

    missing = str(uuid.uuid4())
    svc, model = s.service([[call("get_product", product_ids=[s.products["asus-zen"], s.products["lenovo-idea"], missing])],
                            compare])
    compared = ask(s, svc, "So sánh asus-zen và lenovo-idea")
    products = seen[0]["Products"]
    assert [p["ProductId"] for p in products] == [s.products["asus-zen"], s.products["lenovo-idea"], missing]
    assert products[0]["Specifications"]["RAM"] == "16 GB" and products[2]["error"] == "product_not_found"
    assert "asus-zen" in compared.AiMessages[0].Content and "lenovo-idea" in compared.AiMessages[0].Content
    assert len(model.calls) == 2  # One round reads both products.
    twice, model = s.service([[call("get_product", product_ids=[s.products["asus-zen"]] * 2)],
                              {"intent": "clarify", "clarification": "products"}])
    ask(s, twice, "So sánh hai lần cùng một máy")
    assert json.loads(model.calls[1][0][-1]["content"])["error"] == "invalid_tool_arguments"


def test_a_comparison_naming_one_brand_does_not_filter_by_it(grounded_shop):
    s = grounded_shop
    seen = []

    def compare(messages):
        seen.append(json.loads(messages[-1]["content"]))
        return finish("no_results")

    svc, _ = s.service([[call("search_products", keyword="zen")], compare])
    ask(s, svc, "So sánh máy Lenovo idea với mẫu zen")
    assert [p["ProductId"] for p in seen[0]["Products"]] == [s.products["asus-zen"]]
    assert seen[0]["Constraints"]["brand_id"] is None


def test_a_rejected_call_in_the_last_round_still_gets_its_one_repair(grounded_shop):
    s = grounded_shop

    def rejected(_):
        raise AiUnavailableError("AI trả lệnh gọi công cụ không hợp lệ.", code="ai_invalid_output")

    steps = [[call("get_product", product_id=s.products["asus-zen"])] for _ in range(4)]
    svc, model = s.service([*steps, rejected, finish("product", s.products["asus-zen"])])
    assert ask(s, svc).Status == "Completed" and len(model.calls) == 6
    offered = [[tool["function"]["name"] for tool in kwargs["tools"]] for _, kwargs in model.calls]
    assert offered[-2:] == [["present_answer"], ["present_answer"]]


def test_unknown_ids_and_free_text_facts_are_rejected(grounded_shop):
    s = grounded_shop
    # The backend's own search for "Laptop ASUS…" never returned the Lenovo, so it cannot be recommended.
    svc, _ = s.service([finish("recommend", s.products["lenovo-idea"])])
    with pytest.raises(AiUnavailableError) as error:
        ask(s, svc)
    assert error.value.code == "ai_ungrounded_output"
    bad, _ = s.service([{"intent": "clarify", "answer": "Giá chỉ 1 đồng, RAM 999 GB"}])
    with pytest.raises(AiUnavailableError) as error:
        ask(s, bad, "Câu hỏi khác")
    assert error.value.code == "ai_invalid_output"
    with Session(s.engine) as db:
        assert not list(db.scalars(select(Message).where(Message.SenderType == "AI")))


def test_invalid_final_function_arguments_get_one_bounded_repair(grounded_shop):
    s = grounded_shop
    svc, model = s.service([[call("present_answer", intent="recommend", products=[])],
                            {"intent": "clarify", "clarification": "budget"}])
    result = ask(s, svc)
    assert result.Status == "Completed" and "Ngân sách" in result.AiMessages[0].Content
    assert json.loads(model.calls[1][0][-1]["content"])["error"] == "invalid_final_answer"


def test_a_tool_call_rejected_by_the_provider_gets_one_bounded_repair(grounded_shop):
    s = grounded_shop

    def rejected(_):
        # Invalid provider output is repaired once without leaking the original generation.
        raise AiUnavailableError("AI trả lệnh gọi công cụ không hợp lệ.", code="ai_invalid_output")

    svc, model = s.service([rejected, {"intent": "clarify", "clarification": "budget"}])
    result = ask(s, svc)
    assert result.Status == "Completed" and len(model.calls) == 2
    assert model.calls[1][0][-1] == {"role": "system", "content": REPAIR_NOTE}
    twice, _ = s.service([rejected, rejected])
    with pytest.raises(AiUnavailableError) as error:
        ask(s, twice, "Laptop Lenovo dưới 20 triệu")
    assert error.value.code == "ai_invalid_output"


def test_no_results_and_nonexistent_product_are_not_fabricated(grounded_shop):
    s = grounded_shop
    svc, _ = s.service([[call("search_products", category="laptop", max_price=1000000)], {"intent": "no_results"}])
    result = ask(s, svc, "Laptop ASUS dưới 1 triệu")
    assert len(result.AiMessages) == 1 and "chưa chọn được" in result.AiMessages[0].Content
    missing, model = s.service([[call("get_product", slug="does-not-exist")],
                                {"intent": "clarify", "clarification": "products"}])
    result = ask(s, missing, "Mẫu does-not-exist có không?")
    assert len(result.AiMessages) == 1
    assert json.loads(model.calls[1][0][-1]["content"])["error"] == "product_not_found"


def test_variant_ids_must_have_been_returned_by_the_tool(grounded_shop):
    s = grounded_shop
    svc, _ = s.service([[call("get_product", product_id=s.products["asus-zen"])],
        {"intent": "recommend", "products": [{"product_id": s.products["asus-zen"],
                                               "product_variant_id": s.variants["lenovo-idea"]}]}])
    with pytest.raises(AiUnavailableError) as error:
        ask(s, svc)
    assert error.value.code == "ai_ungrounded_output"


def test_nested_specs_and_requested_keys_are_taken_from_database(grounded_shop):
    s = grounded_shop
    with Session(s.engine) as db:
        db.get(Product, uuid.UUID(s.products["asus-zen"])).Specifications = {
            "Color": "Black", "Ports": ["USB-C", "HDMI"], "Hardware": {"RAM": "32 GB", "CPU": "Test CPU"}}
        db.commit()
    svc, _ = s.service([[call("get_product", product_id=s.products["asus-zen"])],
        {"intent": "product", "products": [{"product_id": s.products["asus-zen"],
                                               "specification_keys": ["Hardware / RAM"]}]}])
    result = ask(s, svc, "asus-zen RAM bao nhiêu?")
    assert "Hardware / RAM: 32 GB" in result.AiMessages[0].Content


def test_unknown_tool_and_extra_sql_argument_never_execute(grounded_shop):
    s = grounded_shop
    svc, model = s.service([[call("delete_product", product_id=s.products["asus-zen"])],
                            [call("search_products", sql="DROP TABLE Products")],
                            {"intent": "clarify", "clarification": "category"}])
    response = ask(s, svc)
    assert response.Status == "Completed"
    assert json.loads(model.calls[1][0][-1]["content"])["error"] == "unknown_tool"
    assert json.loads(model.calls[2][0][-1]["content"])["error"] == "invalid_tool_arguments"
    with Session(s.engine) as db:
        assert not db.get(Product, uuid.UUID(s.products["asus-zen"])).IsDeleted


def test_final_response_after_fourth_tool_round_is_accepted(grounded_shop):
    s = grounded_shop
    steps = [[call("get_product", product_id=s.products["asus-zen"])] for _ in range(4)]
    svc, model = s.service([*steps, finish("product", s.products["asus-zen"])])
    response = ask(s, svc)
    assert response.Status == "Completed" and len(model.calls) == 5
    offered = [[tool["function"]["name"] for tool in kwargs["tools"]] for _, kwargs in model.calls]
    assert offered[-1] == ["present_answer"] and all(len(names) == 4 for names in offered[:-1])
    assert model.calls[-1][0][-1] == {"role": "system", "content": FINAL_NOTE}
    with Session(s.engine) as db:
        question = db.get(Message, response.CustomerMessage.MessageId)
        assert question.Metadata["AiUsage"] == {"Input": 50, "Output": 25}


def test_excess_tool_rounds_and_total_deadline_are_bounded(grounded_shop):
    s = grounded_shop
    steps = [[call("get_product", product_id=s.products["asus-zen"])] for _ in range(5)]
    svc, _ = s.service(steps)
    with pytest.raises(AiUnavailableError) as error:
        ask(s, svc)
    assert error.value.code == "ai_tool_limit"
    timer = SimpleNamespace(value=0)

    def late(_):
        timer.value = 21
        return {"intent": "clarify"}

    delayed, model = s.service([late], timer=lambda: timer.value)
    with pytest.raises(AiUnavailableError):
        ask(s, delayed, "Câu hỏi trễ")
    assert len(model.calls) == 1


def test_sale_price_and_current_public_coupon_conditions(grounded_shop):
    s = grounded_shop
    with Session(s.engine) as db:
        auto = Promotion(CreatedByUserId=s.actor.user_id, Name="Automatic", ApplyMode="Automatic", Status="Active",
                         DiscountType="FixedAmount", DiscountValue=3000000, MinOrderValue=0,
                         StartDate=s.now.value-timedelta(days=1), EndDate=s.now.value+timedelta(days=1))
        live = Promotion(CreatedByUserId=s.actor.user_id, Name="Coupon", ApplyMode="Coupon", Status="Active",
                         DiscountType="FixedAmount", DiscountValue=100000, MinOrderValue=5000000,
                         StartDate=s.now.value-timedelta(days=1), EndDate=s.now.value+timedelta(days=1))
        db.add_all([auto, live]); db.flush()
        live_id = live.PromotionId
        db.add(PromotionProduct(PromotionId=auto.PromotionId, ProductId=uuid.UUID(s.products["asus-vivo"])))
        db.add(Coupon(PromotionId=live.PromotionId, CreatedByUserId=s.actor.user_id,
                      Code="SAVE100", Name="Save", UsageLimit=10, UsedCount=0))
        db.commit()
    svc, _ = s.service([[call("search_products", category="laptop", brand="asus", max_price=20000000)],
                        finish("recommend", s.products["asus-vivo"])])
    result = ask(s, svc)
    assert Decimal(result.AiMessages[1].Metadata["Price"]) == 18000000
    offers, _ = s.service([[call("list_offers")], {"intent": "offers"}])
    response = ask(s, offers, "Có mã giảm giá nào hôm nay?")
    answer = response.AiMessages[0].Content
    assert "SAVE100" in answer and "100.000 đ" in answer and "5.000.000 đ" in answer
    assert "giỏ hàng" in answer

    def expire_offer(_):
        with Session(s.engine) as db:
            db.get(Promotion, live_id).EndDate = s.now.value - timedelta(seconds=1)
            db.commit()
        return {"intent": "offers"}

    refreshed, _ = s.service([[call("list_offers")], expire_offer])
    result = ask(s, refreshed, "Ưu đãi hiện tại?")
    assert "SAVE100" not in result.AiMessages[0].Content


def test_cards_and_answer_are_rolled_back_together(grounded_shop):
    s = grounded_shop
    svc, _ = s.service([[call("search_products", category="laptop", max_price=20000000)],
                        finish("recommend", s.products["asus-zen"], s.products["lenovo-idea"])])
    create = svc.messages.create
    count = {"cards": 0}

    def broken(values):
        if values["MessageType"] == "Product":
            count["cards"] += 1
            if count["cards"] == 2:
                raise RuntimeError("simulated card failure")
        return create(values)

    svc.messages.create = broken
    with pytest.raises(RuntimeError):
        ask(s, svc, "Laptop dưới 20 triệu")
    with Session(s.engine) as db:
        rows = list(db.scalars(select(Message)))
        assert len(rows) == 1 and rows[0].SenderType == "Customer"
        assert rows[0].Metadata["AiProcessingStatus"] == "Failed"


def test_http_returns_product_cards_and_replays_same_ids(grounded_shop):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.core.dependencies import get_current_actor
    from app.routers.chat import router
    from app.routers.dependencies import get_ai_chat_service
    from app.routers.errors import service_error_handler
    from app.services.exceptions import ServiceError

    s = grounded_shop
    svc, _ = s.service([[call("search_products", category="laptop", max_price=20000000)],
                        finish("recommend", s.products["asus-zen"])])
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ServiceError, service_error_handler)
    app.dependency_overrides[get_current_actor] = lambda: s.actor
    app.dependency_overrides[get_ai_chat_service] = lambda: svc
    path = f"/conversations/{s.cid}/ai-messages"
    body = {"ClientRequestId": str(uuid.uuid4()), "Content": "Laptop ASUS dưới 20 triệu"}
    with TestClient(app) as client:
        response = client.post(path, json=body)
        assert response.status_code == 200, response.text
        assert [m["MessageType"] for m in response.json()["AiMessages"]] == ["Text", "Product"]
        card = response.json()["AiMessages"][1]
        assert card["Metadata"]["Price"] == "18000000.00" and card["Metadata"]["Slug"] == "asus-zen"
        replay = client.post(path, json=body)
        assert replay.json()["AiMessages"][1]["MessageId"] == card["MessageId"]
