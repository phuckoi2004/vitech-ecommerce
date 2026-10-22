"""Hard filters first, then Score = Σ wᵢ·sᵢ / Σ wᵢ over N 0.40, B 0.25, T 0.20 (no purchase history H).

Pure formula tests plus real catalog/pricing services on isolated SQLite with a scripted model; no Gemini calls.
"""

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.ai_config import AiSettings
from app.core.auth_state import MemoryStateStore
from app.models import Brand, Category, Conversation, Message, Product, ProductVariant, User
from app.schemas.ai_chat import AiMessageCreate
from app.services.actor import Actor
from app.services.ai_chat import AiChatService
from app.services.recommendation import (WEIGHTS, Candidate, RankingCriteria, assess, detect_needs, evaluate,
                                         need_score, ranking_key)
from tests.sqlite_schema import create_tables
from tests.test_ai_grounded import ScriptedModel, call, finish
from tests.test_ai_personalization import TABLES, sqlite_functions

DEV = {"Dung lượng RAM": "16GB", "Ổ cứng": "512GB SSD PCIe (M.2 2280)", "Loại CPU": "AMD Ryzen 7 7735HS (8 lõi, 16 luồng)",
       "Số khe ram": "2 khe, nâng cấp tối đa 64GB"}


def candidate(**overrides):
    values = {"product_id": "p1", "brand_id": "asus", "name": "Laptop p1", "category_name": "Laptop lập trình",
              "kind": "laptop", "specs": DEV, "price": Decimal("15000000"), **overrides}
    return Candidate(**values)


def score(criteria=RankingCriteria(), budget_max=None, **overrides):
    return evaluate(criteria, candidate(**overrides), budget_max=budget_max)


def n_of(needs, kind, specs, category="Laptop"):
    return need_score(assess(RankingCriteria(needs), candidate(kind=kind, specs=specs, category_name=category)))


@pytest.mark.parametrize("question,needs", [
    ("Laptop học lập trình dưới 20 triệu", ("programming",)), ("laptop chơi game", ("gaming",)),
    ("điện thoại pin trâu chụp ảnh đẹp", ("battery", "camera")), ("laptop mỏng nhẹ cho sinh viên", ("study", "portable")),
    ("Tư vấn laptop", ()),
])
def test_needs_are_mapped_from_phrases_not_keywords(question, needs):
    assert detect_needs(question) == needs


def test_inactive_criteria_are_dropped_and_weights_renormalized():
    assert score(kind=None, category_name="Tai nghe").score is None  # Nothing to measure: catalog order is kept.
    budget_only = score(kind=None, category_name="Tai nghe", budget_max=20000000)
    assert budget_only.parts == {"B": pytest.approx(0.70 + 0.30 * 5 / 20)} and budget_only.score == budget_only.parts["B"]
    both = score(RankingCriteria(needs=("programming",)), budget_max=20000000)
    assert set(both.parts) == {"N", "B"} and both.parts["N"] > 0.9  # Only GPU/battery of the balanced share are unknown.
    assert both.score == pytest.approx((0.40 * both.parts["N"] + 0.25 * both.parts["B"]) / 0.65)
    every = score(RankingCriteria(needs=("programming",), soft_brand_ids=frozenset({"asus"})), budget_max=20000000)
    assert every.score == pytest.approx((0.40 * every.parts["N"] + 0.25 * every.parts["B"] + 0.20 * 1.0) / 0.85)
    assert score(kind=None, budget_max=15000000).parts["B"] == pytest.approx(0.70)  # At the ceiling: not "dearer is better".


def test_the_formula_has_no_purchase_history_term():
    assert WEIGHTS == {"N": 0.40, "B": 0.25, "T": 0.20}
    assert set(RankingCriteria.__dataclass_fields__) == {"needs", "soft_brand_ids"}
    soft = RankingCriteria(soft_brand_ids=frozenset({"asus"}))
    assert score(soft, kind=None).parts == {"T": 1.0} and score(soft, kind=None, brand_id="dell").parts == {"T": 0.0}


def test_missing_or_unstated_data_never_counts_as_met():
    empty, matched, gaps, completeness = n_of(("programming",), "laptop", {})
    assert empty == 0.0 and matched == [] and completeness < 0.2  # Only the curated-category check is known.
    assert "chưa có dữ liệu RAM" in gaps and "chưa có dữ liệu ổ cứng" in gaps
    phone = {"Camera sau": "Camera chính 200MP, f/1.7; camera góc rộng 12MP", "Pin": "5.000 mAh", "Công nghệ sạc": "Sạc nhanh 45W"}
    rows = assess(RankingCriteria(("camera",)), candidate(kind="phone", specs=phone, category_name="Điện thoại"))
    camera = {id_: result for id_, _, result in rows}
    assert camera["ois"].score == 0.0 and camera["ois"].evidence == "chưa xác nhận chống rung quang học"  # 200 MP proves nothing.
    _, matched, _, _ = n_of(("battery",), "phone", phone, "Điện thoại")
    assert matched[:2] == ["pin 5.000 mAh", "sạc 45 W"]


def test_ties_prefer_need_fit_then_complete_data_then_price_then_product_id():
    full = score(RankingCriteria(needs=("programming",)))
    partial = score(RankingCriteria(needs=("programming",)), specs={**DEV, "Số khe ram": "Không rõ"})
    partial.score, partial.parts, partial.completeness = full.score, dict(full.parts), 0.5
    a, b, c = candidate(product_id="a"), candidate(product_id="b"), candidate(product_id="c")
    cheaper = candidate(product_id="z", price=Decimal("14000000"))
    rows = [(b, partial), (c, None), (a, full), (cheaper, full)]
    ordered = sorted(enumerate(rows), key=lambda item: ranking_key(item[1][1], item[1][0], item[0]))
    assert [row[0].product_id for _, row in ordered] == ["z", "a", "b", "c"]


@pytest.fixture
def laptops():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", sqlite_functions)
    counters = {"connections": 0}
    event.listen(engine, "checkout", lambda *_: counters.update(connections=counters["connections"] + 1))
    event.listen(engine, "checkin", lambda *_: counters.update(connections=counters["connections"] - 1))
    create_tables(engine, TABLES)
    now = datetime(2026, 10, 22, 8, tzinfo=timezone.utc)
    with Session(engine) as db:
        owner = User(Email="owner@example.test", PhoneNumber="0912345678", PasswordHash="test-only",
                     FullName="Customer", Role="Customer", AccountStatus="Active")
        root = Category(Name="Laptop", Slug="laptop")
        db.add_all([owner, root]); db.flush()
        dev = Category(Name="Laptop lập trình", Slug="laptop-lap-trinh", ParentCategoryId=root.CategoryId)
        office = Category(Name="Laptop văn phòng", Slug="laptop-van-phong", ParentCategoryId=root.CategoryId)
        brands = {name: Brand(Name=name, Slug=name.lower()) for name in ("ASUS", "Lenovo", "Dell", "Acer")}
        db.add_all([dev, office, *brands.values()]); db.flush()
        cid = uuid.uuid4()
        db.add(Conversation(ConversationId=cid, CustomerId=owner.UserId, Mode="AI", Status="Open"))
        products = {}
        for name, brand, category, price, stock, specs in [
            ("dev-pro", "Lenovo", dev, 19500000, 4, DEV),
            ("mid-dev", "ASUS", dev, 17000000, 4, {"Dung lượng RAM": "16 GB", "Ổ cứng": "512 GB NVMe",
                                                    "Loại CPU": "Intel Core i5-13420H"}),
            ("office-basic", "Acer", office, 12000000, 4, {"Dung lượng RAM": "8GB", "Ổ cứng": "256GB SSD",
                                                          "Loại CPU": "Intel Core i3-1215U"}),
            ("too-expensive", "Dell", dev, 25000000, 4, DEV),  # Hard filter: over the stated budget.
            ("sold-out", "Dell", dev, 15000000, 0, DEV),  # Hard filter: no variant in stock.
        ]:
            product = Product(Name=name, Slug=name, BrandId=brands[brand].BrandId, CategoryId=category.CategoryId,
                              Status="Active", WarrantyMonths=24, Specifications=specs)
            db.add(product); db.flush()
            db.add(ProductVariant(ProductId=product.ProductId, Sku=name, VariantName="Bản tiêu chuẩn", Price=price,
                                  CostPrice=price // 2, StockQuantity=stock))
            products[name] = str(product.ProductId)
        actor = Actor(owner.UserId, "Customer")
        db.commit()
    state = MemoryStateStore()
    sessions = []

    def service(steps, ranking=True):
        session = Session(engine, autoflush=False)
        sessions.append(session)
        model = ScriptedModel(steps, counters)
        return AiChatService(session, settings=AiSettings(api_key="test", ranking_enabled=ranking), model=model,
                             state=state, clock=lambda: now), model

    yield SimpleNamespace(engine=engine, cid=cid, actor=actor, products=products, service=service)
    for session in sessions:
        session.close()
    engine.dispose()


def ask(s, svc, content):
    return svc.ask(s.actor, s.cid, AiMessageCreate(ClientRequestId=uuid.uuid4(), Content=content))


def result_of(messages):
    return json.loads(messages[-1]["content"])


def question_metadata(s, content):
    with Session(s.engine) as db:
        return db.scalar(select(Message).where(Message.Content == content)).Metadata


def test_hard_filters_then_ranked_top_k_with_reasons_from_confirmed_facts(laptops):
    s, p = laptops, laptops.products

    def ranked(messages):
        result = result_of(messages)
        assert result["Ranked"] is True and result["Eligible"] == 3  # Over budget and sold out never compete.
        assert [item["Slug"] for item in result["Products"]] == ["dev-pro", "mid-dev", "office-basic"]
        top = result["Products"][0]["Ranking"]
        budget = 0.70 + 0.30 * 500000 / 20000000
        assert top["Rank"] == 1 and set(top["Parts"]) == {"N", "B"} and top["Parts"]["N"] == 1.0
        assert top["Score"] == pytest.approx((0.40 * 1.0 + 0.25 * budget) / 0.65, abs=0.006)
        assert "RAM 16 GB" in top["Matched"] and "chưa có dữ liệu khe RAM" in result["Products"][1]["Ranking"]["Gaps"]
        # The model lists the weaker one first; the formula decides the order shown to the customer.
        return [call("present_answer", **finish("recommend", p["office-basic"], p["dev-pro"]))]

    svc, _ = s.service([[call("search_products", category="laptop", max_price=20000000)], ranked])
    response = ask(s, svc, "Laptop học lập trình dưới 20 triệu")
    cards = response.AiMessages[1:]
    assert [(c.Metadata["Slug"], c.Metadata["Rank"]) for c in cards] == [("dev-pro", 1), ("office-basic", 2)]
    assert all("Score" not in c.Metadata and "Ranking" not in c.Metadata for c in cards)
    answer = response.AiMessages[0].Content
    assert answer.index("dev-pro") < answer.index("office-basic")
    assert ("Phù hợp: RAM 16 GB; SSD 512 GB; CPU AMD Ryzen 7 7735HS (nhóm hiệu năng cao); RAM nâng cấp được; "
            "trong ngân sách 20.000.000 đ.") in answer
    assert "Lưu ý: RAM 8 GB (dưới 16 GB); SSD 256 GB (dưới 512 GB); CPU Intel Core i3-1215U (nhóm phổ thông)." in answer
    assert "Thông tin sản phẩm từ catalog" not in answer and "yêu thích" not in answer
    assert "AiRanking" not in (response.CustomerMessage.Metadata or {})
    ranking = question_metadata(s, "Laptop học lập trình dưới 20 triệu")["AiRanking"]
    assert ranking["Ordered"] is True and ranking["Needs"] == ["programming"]
    assert [item["ProductId"] for item in ranking["Products"]] == [p["dev-pro"], p["office-basic"]]


def test_soft_brand_preference_moves_a_brand_up_without_filtering_others(laptops):
    s = laptops

    def asus_first(messages):
        result = result_of(messages)
        assert [item["Slug"] for item in result["Products"]] == ["mid-dev", "dev-pro", "office-basic"]
        assert result["Products"][0]["Ranking"]["Parts"]["T"] == 1.0
        return finish("recommend", s.products["mid-dev"])

    svc, _ = s.service([[call("search_products", category="laptop")], asus_first])
    response = ask(s, svc, "Laptop học lập trình dưới 20 triệu, ưu tiên ASUS")
    assert "đúng hãng bạn ưu tiên" in response.AiMessages[0].Content


def test_requested_order_and_baseline_mode_are_not_reranked(laptops):
    s, p = laptops, laptops.products

    def cheapest(messages):
        result = result_of(messages)
        assert result["Ranked"] is False and "Ranking" not in result["Products"][0]
        assert [item["Slug"] for item in result["Products"]] == ["office-basic", "mid-dev", "dev-pro"]
        return finish("recommend", p["office-basic"], p["dev-pro"])

    svc, _ = s.service([[call("search_products", category="laptop")], cheapest])
    response = ask(s, svc, "Laptop học lập trình rẻ nhất dưới 20 triệu")
    assert [c.Metadata["Slug"] for c in response.AiMessages[1:]] == ["office-basic", "dev-pro"]
    assert "Phù hợp:" in response.AiMessages[0].Content  # Still explained, just not reordered.
    assert question_metadata(s, "Laptop học lập trình rẻ nhất dưới 20 triệu")["AiRanking"]["Ordered"] is False

    def baseline(messages):
        result = result_of(messages)
        assert result["Ranked"] is False and [item["Slug"] for item in result["Products"]][0] == "office-basic"
        return finish("recommend", p["office-basic"], p["dev-pro"])

    svc, _ = s.service([[call("search_products", category="laptop")], baseline], ranking=False)
    response = ask(s, svc, "Laptop học lập trình dưới 20 triệu")
    assert [c.Metadata["Slug"] for c in response.AiMessages[1:]] == ["office-basic", "dev-pro"]
    assert "Phù hợp:" not in response.AiMessages[0].Content
    assert "AiRanking" not in question_metadata(s, "Laptop học lập trình dưới 20 triệu")


def test_without_a_stated_need_the_balanced_profile_ranks_and_no_results_are_not_forced(laptops):
    s = laptops

    def plain(messages):
        result = result_of(messages)
        # No budget: the 25-million model is eligible. No need: laptops are compared on the balanced profile.
        assert result["Ranked"] is True and result["Returned"] == 4
        assert [p["Ranking"]["Parts"].keys() for p in result["Products"]][0] == {"N"}
        assert [p["Slug"] for p in result["Products"]][-1] == "office-basic"
        return {"intent": "clarify", "clarification": "usage"}

    svc, _ = s.service([[call("search_products", category="laptop")], plain])
    assert ask(s, svc, "Tư vấn laptop").Status == "Completed"

    def nothing(messages):
        result = result_of(messages)
        assert result["Products"] == [] and result["Eligible"] == 0
        return {"intent": "no_results"}

    svc, _ = s.service([[call("search_products", category="laptop")], nothing])
    response = ask(s, svc, "Laptop lập trình dưới 10 triệu")
    assert response.AiMessages[0].Content.startswith("VieTech chưa chọn được sản phẩm phù hợp")


def test_storage_without_a_stated_type_counts_by_capacity_but_a_stated_hdd_does_not():
    for value, expected in (("512GB", (1.0, "ổ cứng 512 GB")), ("512 GB PCIe NVMe", (1.0, "SSD 512 GB")),
                            ("1TB HDD 5400rpm", (0.0, "ổ cứng HDD 1024 GB (không phải SSD)"))):
        result, matched, gaps, _ = n_of(("programming",), "laptop", {"Ổ cứng": value})
        assert (expected[1] in matched) == bool(expected[0]) and (expected[1] in gaps) == (not expected[0])


def test_a_need_named_child_category_is_scored_softly_not_used_as_a_hard_filter(laptops):
    s = laptops

    def widened(messages):
        result = result_of(messages)
        # "Laptop lập trình" is VieTech's need group: the office laptop still competes, ranked by the formula.
        assert result["Eligible"] == 3
        assert [item["Slug"] for item in result["Products"]] == ["dev-pro", "mid-dev", "office-basic"]
        assert result["Products"][0]["Ranking"]["Parts"]["N"] == 1.0  # Includes the curated-category criterion.
        return finish("recommend", s.products["dev-pro"])

    svc, _ = s.service([[call("search_products", category="laptop")], widened])
    assert ask(s, svc, "Laptop lập trình dưới 20 triệu").Status == "Completed"


def test_batched_details_match_single_product_details_including_automatic_prices(laptops):
    from datetime import timedelta

    from app.models import Promotion, PromotionCategory, PromotionProduct
    from app.services.catalog import ProductService

    s = laptops
    now = datetime(2026, 10, 22, 8, tzinfo=timezone.utc)
    with Session(s.engine) as db:
        dev = db.scalar(select(Category).where(Category.Slug == "laptop-lap-trinh"))
        window = {"CreatedByUserId": s.actor.user_id, "ApplyMode": "Automatic", "Status": "Active", "MinOrderValue": 0,
                  "StartDate": now - timedelta(days=1), "EndDate": now + timedelta(days=1)}
        by_product = Promotion(Name="Giảm mid-dev", DiscountType="FixedAmount", DiscountValue=1000000, **window)
        by_category = Promotion(Name="Giảm laptop lập trình", DiscountType="Percentage", DiscountValue=5, **window)
        db.add_all([by_product, by_category]); db.flush()
        db.add(PromotionProduct(PromotionId=by_product.PromotionId, ProductId=uuid.UUID(s.products["mid-dev"])))
        db.add(PromotionCategory(PromotionId=by_category.PromotionId, CategoryId=dev.CategoryId))
        db.commit()
    with Session(s.engine) as db:
        catalog = ProductService(db, clock=lambda: now)
        ids = [uuid.UUID(product_id) for product_id in s.products.values()]
        batch = catalog.get_product_details(ids)
        assert set(batch) == set(ids)
        for product_id in ids:
            assert batch[product_id].model_dump() == catalog.get_product_detail(product_id).model_dump()
        assert batch[uuid.UUID(s.products["mid-dev"])].Variants[0].SalePrice < Decimal("17000000")
