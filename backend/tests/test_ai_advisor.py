"""Catalog-based advice end to end: intent and context, hard filters, ranking, no repeats, grounded wording.

Real catalog/pricing services on isolated SQLite. The model is a local fake that answers like Gemini from the data the
backend hands it (analysis, ranked prefetch, referenced products), so the multi-turn script uses no Gemini quota.
"""

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.ai_config import AiSettings
from app.core.auth_state import MemoryStateStore
from app.integrations.ai import ChatCompletion, ToolCall
from app.models import Base, Brand, Category, Conversation, Message, Product, ProductVariant, User
from app.schemas.ai_chat import AiMessageCreate
from app.services.actor import Actor
from app.services.ai_chat import AiChatService
from app.services.ai_grounding import Facts, ProductFacts, check_message
from app.services.ai_intent import (BrandInfo, CategoryInfo, ConversationState, PastTurn, Vocabulary, analyze)
from app.services.recommendation import (Candidate, RankingCriteria, assess, detect_needs, model_key, rank)
from tests.sqlite_schema import create_tables
from tests.test_ai_grounded import ScriptedModel, call, finish
from tests.test_ai_personalization import TABLES, sqlite_functions

NOW = datetime(2026, 10, 22, 8, tzinfo=timezone.utc)

PHONES = [  # name, brand, price, specs
    ("Samsung Galaxy A07 4GB 128GB", "Samsung", 4490000, {"Chipset": "MediaTek Dimensity 6300 5G", "Dung lượng RAM": "4 GB",
     "Bộ nhớ trong": "128 GB", "Pin": "6000 mAh", "Tính năng màn hình": "90Hz"}),
    ("Meizu Lucky 08 8GB 256GB", "Meizu", 5500000, {"Chipset": "Snapdragon 7s Gen 2", "Dung lượng RAM": "8 GB",
     "Bộ nhớ trong": "256 GB", "Pin": "6000mAh", "Tính năng màn hình": "144Hz"}),
    ("HONOR X7d 8GB 256GB", "HONOR", 6890000, {"Chipset": "Qualcomm Snapdragon 6s Gen 3", "Dung lượng RAM": "8 GB",
     "Bộ nhớ trong": "256 GB", "Pin": "7000 mAh"}),
    ("Xiaomi Redmi Note 14 Pro Plus 8GB 256GB", "Xiaomi", 7650000, {"Chipset": "Snapdragon 7s Gen 3", "Dung lượng RAM": "8 GB",
     "Bộ nhớ trong": "256 GB", "Pin": "5110 mAh", "Camera sau": "200MP OIS", "Tính năng màn hình": "120Hz"}),
    ("Itel P55 Plus 8GB 256GB", "Itel", 3409000, {"Chipset": "Unisoc T606", "Dung lượng RAM": "8 GB",
     "Bộ nhớ trong": "256 GB", "Pin": "5000mAh", "Tính năng màn hình": "90Hz"}),
    ("Meizu Mblu 22 Pro 4GB 128GB", "Meizu", 3315000, {"Chipset": "Mediatek Helio G81", "Dung lượng RAM": "4 GB",
     "Bộ nhớ trong": "128 GB", "Pin": "5000 mAh"}),
    ("Xiaomi Redmi 13 8GB 128GB", "Xiaomi", 3990000, {"Chipset": "Helio G91", "Dung lượng RAM": "8 GB",
     "Bộ nhớ trong": "128 GB", "Pin": "5030 mAh", "Tính năng màn hình": "90Hz"}),
    ("Samsung Galaxy A17 6GB 128GB", "Samsung", 5290000, {"Chipset": "Exynos 1330", "Dung lượng RAM": "6 GB",
     "Bộ nhớ trong": "128 GB", "Pin": "5000 mAh", "Tính năng màn hình": "90Hz"}),
    ("HONOR X6c 6GB 128GB", "HONOR", 3690000, {"Chipset": "Helio G81", "Dung lượng RAM": "6 GB", "Bộ nhớ trong": "128 GB",
     "Pin": "5300 mAh"}),
    ("OPPO Reno15 12GB 256GB", "OPPO", 13990000, {"Chipset": "Snapdragon 7 Gen 4", "Pin": "6500 mAh"}),  # Over 8 triệu.
    ("Samsung Galaxy A37 8GB 128GB", "Samsung", 9990000, {"Chipset": "Exynos 1480", "Pin": "5000 mAh"}),  # Over 8 triệu.
]
LAPTOPS = [  # name, brand, child category?, price, specs
    ("Laptop Dell Inspiron 14 5440", "Dell", True, 18990000, {"Loại CPU": "Intel Core 5 120U", "Dung lượng RAM": "16GB",
     "Ổ cứng": "512GB SSD", "Pin": "54WHr", "Loại card đồ họa": "Intel Graphics"}),
    ("Laptop Acer Aspire Lite 14 AL14", "Acer", False, 15990000, {"Loại CPU": "AMD Ryzen 7 7730U", "Dung lượng RAM": "8GB",
     "Ổ cứng": "512GB SSD", "Số khe ram": "2 khe, nâng cấp tối đa 32GB", "Pin": "58Wh", "Loại card đồ họa": "Radeon"}),
    ("Laptop Lenovo IdeaPad Slim 3 15IRH8", "Lenovo", True, 17490000, {"Loại CPU": "Intel Core i5-13420H",
     "Dung lượng RAM": "16GB", "Ổ cứng": "512GB SSD", "Pin": "50Wh", "Loại card đồ họa": "Intel UHD"}),
    ("Laptop ASUS Vivobook 15 X1504ZA", "ASUS", False, 11990000, {"Loại CPU": "Intel Core i3-1215U", "Dung lượng RAM": "8GB",
     "Ổ cứng": "256GB SSD", "Pin": "42WHrs", "Loại card đồ họa": "Intel UHD"}),
    ("Laptop ASUS TUF Gaming F15 FX507VU", "ASUS", False, 19990000, {"Loại CPU": "Intel Core i7-13620H",
     "Dung lượng RAM": "16GB", "Ổ cứng": "512GB SSD", "Loại card đồ họa": "NVIDIA GeForce RTX 3050", "Pin": "56WHrs"}),
    ("Laptop ASUS Zenbook 14 OLED UX3405", "ASUS", False, 24990000, {"Loại CPU": "Intel Core Ultra 7 155H",
     "Dung lượng RAM": "16GB", "Ổ cứng": "1TB SSD", "Pin": "75Wh"}),  # Over 20 triệu.
]
PHONE_SPECS = {name: specs for name, _, _, specs in PHONES}


@pytest.fixture
def store():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", sqlite_functions)
    counters = {"connections": 0}
    event.listen(engine, "checkout", lambda *_: counters.update(connections=counters["connections"] + 1))
    event.listen(engine, "checkin", lambda *_: counters.update(connections=counters["connections"] - 1))
    create_tables(engine, TABLES)
    with Session(engine) as db:
        owner = User(Email="advisor@example.test", PhoneNumber="0912000000", PasswordHash="test-only",
                     FullName="Customer", Role="Customer", AccountStatus="Active")
        phone, laptop = Category(Name="Điện thoại", Slug="dien-thoai"), Category(Name="Laptop", Slug="laptop")
        db.add_all([owner, phone, laptop]); db.flush()
        battery_group = Category(Name="Điện thoại pin trâu", Slug="dien-thoai-pin-trau", ParentCategoryId=phone.CategoryId)
        dev_group = Category(Name="Laptop lập trình", Slug="laptop-lap-trinh", ParentCategoryId=laptop.CategoryId)
        names = {row[1] for row in PHONES} | {row[1] for row in LAPTOPS}
        brands = {name: Brand(Name=name, Slug=name.lower()) for name in names}
        db.add_all([battery_group, dev_group, *brands.values()]); db.flush()
        cid = uuid.uuid4()
        db.add(Conversation(ConversationId=cid, CustomerId=owner.UserId, Mode="AI", Status="Open"))
        products = {}
        rows = [(name, brand, phone, price, specs) for name, brand, price, specs in PHONES]
        rows += [(name, brand, dev_group if child else laptop, price, specs) for name, brand, child, price, specs in LAPTOPS]
        for name, brand, category, price, specs in rows:
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            product = Product(Name=name, Slug=slug, BrandId=brands[brand].BrandId, CategoryId=category.CategoryId,
                              Status="Active", WarrantyMonths=12, Specifications=specs)
            db.add(product); db.flush()
            db.add(ProductVariant(ProductId=product.ProductId, Sku=slug, VariantName="Bản tiêu chuẩn", Price=price,
                                  CostPrice=price // 2, StockQuantity=5))
            products[name] = str(product.ProductId)
        actor = Actor(owner.UserId, "Customer")
        db.commit()
    state = MemoryStateStore()
    clock = SimpleNamespace(now=NOW)
    sessions = []

    def service(model, ranking=True):
        session = Session(engine, autoflush=False)
        sessions.append(session)
        return AiChatService(session, settings=AiSettings(api_key="test", requests_per_minute=60, ranking_enabled=ranking),
                             model=model, state=state, clock=lambda: clock.now)

    def ask(svc, content):
        clock.now += timedelta(seconds=2)
        return svc.ask(actor, cid, AiMessageCreate(ClientRequestId=uuid.uuid4(), Content=content))

    def question(content):
        with Session(engine) as db:
            return db.scalar(select(Message).where(Message.Content == content, Message.SenderType == "Customer")).Metadata

    yield SimpleNamespace(engine=engine, products=products, service=service, ask=ask, question=question,
                          counters=counters, names={value: key for key, value in products.items()})
    for session in sessions:
        session.close()
    engine.dispose()


def turn_data(messages):
    """The analysis, referenced products and prefetched search the backend put into the system instruction."""
    lines = messages[0]["content"].splitlines()
    data = {}
    for header, key in (("PHÂN TÍCH LƯỢT NÀY", "analysis"), ("SẢN PHẨM KHÁCH ĐANG NHẮC TỚI", "referenced"),
                        ("KẾT QUẢ search_products", "search")):
        index = next((i for i, line in enumerate(lines) if line.startswith(header)), None)
        if index is not None:
            data[key] = json.loads(lines[index + 1])
    return data


class AdvisorModel:
    """Answers like a well-behaved Gemini: only from the backend's data, in Rank order, without tool rounds."""

    def __init__(self, counters):
        self.counters, self.calls = counters, []

    def complete(self, messages, **kwargs):
        assert self.counters["connections"] == 0, "Connection held while model is running"
        self.calls.append(messages)
        data, question = turn_data(messages), messages[-1]["content"]
        intent = data["analysis"]["intent"]
        if intent in ("product_recommendation", "recommend_more"):
            products = data.get("search", {}).get("Products", [])[:3]
            if not products:
                return self._answer({"intent": "no_results"})
            lines = ["Mình chọn được mấy mẫu hợp nhu cầu của bạn:"]
            lines += [f"- {p['Name']}: {'; '.join(p['Ranking']['Matched'][:2]) or 'nằm trong tầm giá bạn đặt'}."
                      for p in products]
            return self._answer({"intent": "recommend", "products": [{"product_id": p["ProductId"]} for p in products],
                                 "message": "\n".join(lines)})
        products = data.get("referenced", {}).get("Products", [])
        if intent == "product_information" and products:
            product = products[0]
            key = next(k for k in product["Specifications"] if "pin" in question.lower() and k == "Pin")
            return self._answer({"intent": "product", "products": [{"product_id": product["ProductId"],
                                 "specification_keys": [key]}],
                                 "message": f"{product['Name']} có dung lượng pin {product['Specifications'][key]}."})
        if intent == "product_comparison" and len(products) >= 2:
            lines = ["So sánh nhanh về pin:"] + [f"- {p['Name']}: pin {p['Specifications'].get('Pin')}." for p in products]
            return self._answer({"intent": "compare", "products": [{"product_id": p["ProductId"]} for p in products],
                                 "message": "\n".join(lines)})
        return self._answer({"intent": "chat"})

    @staticmethod
    def _answer(arguments):
        return ChatCompletion("", "advisor-fake", 10, 5,
                              (ToolCall("call_" + uuid.uuid4().hex, "present_answer", json.dumps(arguments)),))


def cards(response):
    return [m.Metadata for m in response.AiMessages if m.MessageType == "Product"]


def test_the_eight_turn_conversation_keeps_context_and_never_repeats(store):
    s = store
    model = AdvisorModel(s.counters)
    svc = s.service(model)
    price = {name: price for name, _, price, _ in PHONES} | {name: price for name, _, _, price, _ in LAPTOPS}
    phones, laptops = {row[0] for row in PHONES}, {row[0] for row in LAPTOPS}

    # 1. Category and hard budget; with no stated need the balanced profile ranks, not "cheapest first".
    first = s.ask(svc, "Tư vấn điện thoại dưới 8 triệu.")
    names1 = [c["ProductName"] for c in cards(first)]
    assert len(names1) == 3 and set(names1) <= phones and all(price[n] <= 8_000_000 for n in names1)
    assert names1[0] == "Xiaomi Redmi Note 14 Pro Plus 8GB 256GB"  # Strongest chip/RAM/OIS under 8 triệu, not the cheapest.
    assert s.question("Tư vấn điện thoại dưới 8 triệu.")["AiAnswerSource"] == "model"
    assert "Thông tin sản phẩm từ catalog" not in first.AiMessages[0].Content

    # 2. A refined need in the same category keeps the 8-triệu budget; the battery need now leads the ranking.
    second = s.ask(svc, "Tôi muốn điện thoại pin trâu.")
    names2 = [c["ProductName"] for c in cards(second)]
    assert all(price[n] <= 8_000_000 for n in names2) and names2[0] == "HONOR X7d 8GB 256GB"  # 7.000 mAh, the largest.
    meta = s.question("Tôi muốn điện thoại pin trâu.")["AiIntent"]
    assert meta["Inherited"] == ["budget"] and meta["Slots"]["Needs"] == ["battery"]

    # 3. "More" excludes everything shown in this need group and keeps budget and need.
    third = s.ask(svc, "Đề xuất thêm 3 mẫu khác.")
    names3 = [c["ProductName"] for c in cards(third)]
    assert len(names3) == 3 and not set(names3) & (set(names1) | set(names2))
    assert all(price[n] <= 8_000_000 and n in phones for n in names3)
    meta = s.question("Đề xuất thêm 3 mẫu khác.")["AiIntent"]
    assert meta["Intent"] == "recommend_more" and set(meta["ExcludedProductIds"]) == {
        s.products[n] for n in set(names1) | set(names2)}

    # 4. "Máy thứ hai" is the second card of the latest list, resolved by the backend; one model call, no tool round.
    calls = len(model.calls)
    fourth = s.ask(svc, "Máy thứ hai pin bao nhiêu?")
    target = names3[1]
    assert [c["ProductName"] for c in cards(fourth)] == [target] and len(model.calls) == calls + 1
    assert PHONE_SPECS[target]["Pin"] in fourth.AiMessages[0].Content

    # 5. Ordinals still refer to that list, not to the single product of turn 4.
    fifth = s.ask(svc, "So sánh máy thứ nhất và thứ hai.")
    assert [c["ProductName"] for c in cards(fifth)] == names3[:2]
    assert all(PHONE_SPECS[n]["Pin"] in fifth.AiMessages[0].Content for n in names3[:2])

    # 6. A new root category starts a new need group: the phone budget and battery need are not carried over.
    sixth = s.ask(svc, "Giờ tôi muốn laptop dưới 20 triệu học lập trình.")
    names6 = [c["ProductName"] for c in cards(sixth)]
    assert set(names6) <= laptops and all(price[n] <= 20_000_000 for n in names6)
    meta = s.question("Giờ tôi muốn laptop dưới 20 triệu học lập trình.")["AiIntent"]
    assert meta["CategoryChanged"] is True and meta["Slots"]["Needs"] == ["programming"] and meta["Inherited"] == []

    # 7. A named brand is a hard filter; the 20-triệu budget and the programming need carry over.
    seventh = s.ask(svc, "Có laptop ASUS nào không?")
    names7 = [c["ProductName"] for c in cards(seventh)]
    assert names7 and all("ASUS" in n and price[n] <= 20_000_000 for n in names7)
    assert "Laptop ASUS Zenbook 14 OLED UX3405" not in names7  # 24,99 triệu: the inherited budget still applies.

    # 8. Nothing new is left for ASUS under 20 triệu: say so instead of repeating.
    eighth = s.ask(svc, "Còn mẫu khác không?")
    assert cards(eighth) == []
    assert eighth.AiMessages[0].Content.startswith("Mình đã giới thiệu hết")
    assert "hãng ASUS" in eighth.AiMessages[0].Content and "20.000.000 đ" in eighth.AiMessages[0].Content


def test_recommend_more_never_repeats_even_when_the_model_picks_a_shown_product(store):
    s = store
    shown = []

    def first(messages):
        result = turn_data(messages)["search"]
        shown.extend(p["ProductId"] for p in result["Products"][:3])
        return finish("recommend", *shown)

    def stubborn(messages):
        data = turn_data(messages)
        assert not {p["ProductId"] for p in data["search"]["Products"]} & set(shown)
        # The model insists on an old product it remembers (read again by ID): the backend replaces it.
        return [call("get_product", product_id=shown[0])]

    svc = s.service(ScriptedModel([first, stubborn, lambda _: finish("recommend", shown[0])], s.counters))
    s.ask(svc, "Tư vấn điện thoại dưới 8 triệu")
    response = s.ask(svc, "Cho tôi lựa chọn khác")
    new = [c["ProductId"] for c in cards(response)]
    assert new and not set(new) & set(shown)


def test_a_rejected_product_stays_out_of_the_need_group(store):
    s = store
    svc = s.service(AdvisorModel(s.counters))
    first = cards(s.ask(svc, "Điện thoại pin trâu dưới 8 triệu"))
    rejected = first[1]["ProductId"]
    second = s.ask(svc, "Tôi không thích máy thứ hai")
    assert rejected not in [c["ProductId"] for c in cards(second)]
    assert s.question("Tôi không thích máy thứ hai")["AiIntent"]["Slots"]["Rejected"] == [rejected]
    third = s.ask(svc, "Có mẫu nào pin tốt hơn không?")
    assert rejected not in [c["ProductId"] for c in cards(third)]


@pytest.mark.parametrize("question,expected,name", [
    ("Laptop dưới 20 triệu", "category", None),  # Wrong category never reaches ranking.
    ("Điện thoại dưới 5 triệu", "budget", None),  # Over a hard ceiling is removed.
    ("Laptop Lenovo dưới 20 triệu", "brand", "Lenovo"),  # A required brand is exact.
])
def test_hard_filters_run_before_ranking(store, question, expected, name):
    s = store
    seen = {}

    def inspect(messages):
        seen.update(turn_data(messages)["search"])
        return finish("no_results")

    svc = s.service(ScriptedModel([inspect], s.counters))
    s.ask(svc, question)
    returned = [s.names[p["ProductId"]] for p in seen["Products"]]
    assert returned
    if expected == "category":
        assert all(n.startswith("Laptop") for n in returned) and seen["Eligible"] == 5
    elif expected == "budget":
        assert all(next(p for p in PHONES if p[0] == n)[2] <= 5_000_000 for n in returned)
    else:
        assert all(name in n for n in returned)


def test_ungrounded_wording_is_replaced_and_recorded(store):
    s = store

    def invent(messages):
        products = turn_data(messages)["search"]["Products"][:2]
        return {"intent": "recommend", "products": [{"product_id": p["ProductId"]} for p in products],
                "message": f"{products[0]['Name']} pin 9000 mAh, dùng cả ngày, đang giảm giá và trả góp 0%."}

    svc = s.service(ScriptedModel([invent], s.counters))
    response = s.ask(svc, "Tư vấn điện thoại dưới 8 triệu")
    text = response.AiMessages[0].Content
    assert "9000" not in text and "trả góp" not in text and text.startswith("Mình tư vấn 2 mẫu này")
    meta = s.question("Tư vấn điện thoại dưới 8 triệu")
    assert meta["AiAnswerSource"] == "backend" and any("9000" in issue for issue in meta["AiGroundingIssues"])


def test_products_outside_the_database_or_this_turn_are_never_recommended(store):
    s = store
    from app.services.exceptions import AiUnavailableError
    svc = s.service(ScriptedModel([finish("recommend", str(uuid.uuid4()))], s.counters))
    with pytest.raises(AiUnavailableError) as error:
        s.ask(svc, "Tư vấn điện thoại dưới 8 triệu")
    assert error.value.code == "ai_ungrounded_output"


def test_no_cart_wishlist_or_order_table_is_needed():
    # The AI fixtures create no cart tables at all, and every turn above works: recommendations do not depend on them.
    assert not {"Carts", "CartItems"} & set(TABLES)
    assert {"Carts", "CartItems"} <= set(Base.metadata.tables)


# --- Pure units -------------------------------------------------------------------------------------------------

def phone(name, price, **specs):
    return Candidate(name, "b", name, "Điện thoại", "phone", specs, Decimal(price))


def test_graded_need_beats_a_cheaper_weaker_product_and_uninformative_checks_are_dropped():
    big = phone("big", 7_900_000, Pin="7000 mAh", Chipset="Snapdragon 7s Gen 2")
    small = phone("small", 4_000_000, Pin="5000 mAh", Chipset="Snapdragon 7s Gen 2")
    ordered, dropped = rank(RankingCriteria(("battery",)), [small, big], budget_max=8_000_000)
    assert [c.product_id for c, _ in ordered] == ["big", "small"]  # Both pass 5.000 mAh; the larger battery wins.
    assert "charge33" in dropped  # No candidate states charging power: it lowers nobody's N.
    assert ordered[0][1].parts["N"] > ordered[1][1].parts["N"] and ordered[0][1].parts["B"] < ordered[1][1].parts["B"]


def test_a_cheaper_product_does_not_pass_a_better_fit_on_a_hairs_breadth():
    from app.services.recommendation import Evaluation, ranking_key
    honor = (phone("honor", 6_890_000), Evaluation(0.7096, {"N": 0.690, "B": 0.742}))  # 7.000 mAh, better fit.
    lucky = (phone("lucky", 5_500_000), Evaluation(0.7099, {"N": 0.657, "B": 0.794}))  # Ahead only by price.
    ordered = sorted([lucky, honor], key=lambda row: ranking_key(row[1], row[0], 0))
    assert [c.product_id for c, _ in ordered] == ["honor", "lucky"]
    clear = (phone("clear", 5_500_000), Evaluation(0.7300, {"N": 0.657, "B": 0.794}))
    assert sorted([honor, clear], key=lambda row: ranking_key(row[1], row[0], 0))[0] == clear  # A real lead stands.


def test_an_empty_search_over_budget_names_the_nearest_product(store):
    s = store
    seen = {}

    def nothing(messages):
        seen.update(turn_data(messages)["search"])
        return finish("no_results")

    svc = s.service(ScriptedModel([nothing], s.counters))
    response = s.ask(svc, "Laptop ASUS dưới 11 triệu")
    assert seen["Products"] == [] and seen["NearestAboveBudget"]["Name"] == "Laptop ASUS Vivobook 15 X1504ZA"
    assert "Mẫu gần nhất là Laptop ASUS Vivobook 15 X1504ZA với giá 11.990.000 đ" in response.AiMessages[0].Content


@pytest.mark.parametrize("value,watt_hours", [("56WHrs, 4S1P, 4-cell Li-ion", 56), ("4-Cell Battery, 54WHr", 54),
                                              ("Pin Li-Po 53,8 watt‑giờ tích hợp", 53.8), ("3 Cells 53.5 Whrs", 53.5)])
def test_laptop_battery_units_are_normalized(value, watt_hours):
    result = {id_: r for id_, _, r in assess(RankingCriteria(("battery",)), Candidate(
        "l", "b", "Laptop", "Laptop", "laptop", {"Pin": value}, Decimal(1)))}["wh50"]
    assert result.status == "met" and f"{watt_hours:g}".replace(".", ",") in result.evidence


@pytest.mark.parametrize("name,cpu,tier", [
    ("MacBook Air M4 13 inch 2025", "CPU 10 lõi với 4 lõi hiệu năng", "Apple M4 (nhóm hiệu năng cao)"),
    ("MacBook Neo 13 inch A18 Pro", "Chip Apple A18 Pro ; CPU 6 lõi", "Apple A18 Pro (nhóm tầm trung)"),
    ("Laptop Dell", "Intel Core i3-1215U", "Intel Core i3-1215U (nhóm phổ thông)"),
    ("Laptop MSI", "Intel Core i7-13620H Gen 13th", "Intel Core i7-13620H Gen 13th (nhóm hiệu năng cao)"),
])
def test_cpu_class_is_read_from_the_stated_chip(name, cpu, tier):
    rows = {id_: r for id_, _, r in assess(RankingCriteria(("programming",)), Candidate(
        "l", "b", name, "Laptop", "laptop", {"Loại CPU": cpu}, Decimal(1)))}
    assert rows["cpu"].evidence == f"CPU {tier}"


def test_needs_are_not_triggered_by_particles_and_models_collapse_storage_variants():
    assert detect_needs("Tư vấn laptop nhé") == () and detect_needs("Laptop nhẹ cho sinh viên") == ("study", "portable")
    assert detect_needs("Thứ nhất là pin phải trâu nhé") == ("battery",)
    assert model_key("Samsung Galaxy A37 5G 8GB 128GB") == model_key("Samsung Galaxy A37 8GB 256GB (Đen)")
    assert model_key("iPhone 17 Pro 256GB") != model_key("iPhone 17 256GB")


VOCAB = Vocabulary(
    (CategoryInfo("phone", "Điện thoại", "dien-thoai"), CategoryInfo("laptop", "Laptop", "laptop"),
     CategoryInfo("dev", "Laptop lập trình", "laptop-lap-trinh", "laptop")),
    (BrandInfo("asus", "ASUS", "asus"), BrandInfo("lenovo", "Lenovo", "lenovo"), BrandInfo("samsung", "Samsung", "samsung")))
LIST = tuple({"Rank": i, "ProductId": f"p{i}", "ProductName": f"Phone {i}", "Price": str(5_000_000 + i)} for i in (1, 2, 3))
STATE = ConversationState((PastTurn({"CategoryId": "phone", "MaxBudget": 8_000_000, "Needs": ["battery"]},
                                    "recommend", LIST),))


@pytest.mark.parametrize("question,intent", [
    ("Tư vấn điện thoại dưới 8 triệu", "product_recommendation"),
    ("Đề xuất thêm 3 mẫu khác", "recommend_more"),
    ("Còn mẫu nào khác không?", "recommend_more"),
    ("Cho tôi lựa chọn khác", "recommend_more"),
    ("Tôi không thích máy này", "recommend_more"),
    ("So sánh máy thứ nhất và thứ hai", "product_comparison"),
    ("Máy nào pin tốt hơn?", "product_comparison"),
    ("Máy thứ hai pin bao nhiêu?", "product_information"),
    ("iPhone 17 Pro Max giá bao nhiêu?", "price_inquiry"),
    ("Có mã giảm giá nào cho laptop không?", "promotion_inquiry"),
    ("Mã VIETECH300K áp dụng cho đơn từ bao nhiêu?", "promotion_inquiry"),
    ("Vậy thì sao?", "follow_up_question"),
    ("Xin chào", "general_chat"),
])
def test_intents_are_detected_from_vietnamese_phrasing(question, intent):
    assert analyze(question, VOCAB, STATE).intent == intent


def test_context_rules_inherit_replace_and_reset():
    more = analyze("Còn mẫu khác không?", VOCAB, STATE)
    assert (more.category_id, more.max_budget, more.needs) == ("phone", 8_000_000, ("battery",))
    assert set(more.excluded_product_ids) == {"p1", "p2", "p3"} and more.filters()["max_price"] == 8_000_000
    cheaper = analyze("Có mẫu nào rẻ hơn?", VOCAB, STATE)
    assert cheaper.max_budget == 5_000_000 and cheaper.cheaper_than == 5_000_001
    only = analyze("Tôi chỉ có 20 triệu thôi", VOCAB, STATE)  # A budget alone refines the current need group.
    assert (only.intent, only.category_id, only.max_budget, only.needs) == (
        "product_recommendation", "phone", 20_000_000, ("battery",))
    new_budget = analyze("Giờ tối đa 6 triệu thôi", VOCAB, STATE)
    assert (new_budget.min_budget, new_budget.max_budget) == (None, 6_000_000)  # A new budget replaces the old one.
    switched = analyze("Không, tôi muốn laptop.", VOCAB, STATE)
    assert switched.category_changed and switched.max_budget is None and switched.needs == ()
    info = analyze("Máy thứ hai pin bao nhiêu?", VOCAB, STATE)
    assert [r["ProductId"] for r in info.references] == ["p2"] and info.filters()["max_price"] is None
    unknown = analyze("Máy thứ tư thế nào?", VOCAB, STATE)  # Not an ordinal the list has: never guessed.
    assert unknown.references == () or unknown.clarification
    assert analyze("Máy thứ ba có chống rung không?", VOCAB,
                   ConversationState((PastTurn({}, "recommend", LIST[:2]),))).clarification.startswith(
        "Danh sách vừa rồi chỉ có 2 mẫu")
    assert analyze("Máy này pin bao nhiêu?", VOCAB, STATE).clarification.startswith("Bạn đang hỏi mẫu nào")
    asus = analyze("Laptop dưới 20 triệu, ưu tiên ASUS nhưng Lenovo cũng được", VOCAB)
    assert asus.brand_id is None and set(asus.soft_brand_ids) == {"asus", "lenovo"}
    assert analyze("Laptop ASUS dưới 20 triệu", VOCAB).brand_id == "asus"
    assert analyze("Laptop không chọn ASUS", VOCAB).excluded_brand_ids == ("asus",)


def test_need_and_segment_children_filter_by_their_root_but_forms_stay_hard():
    vocab = Vocabulary((
        CategoryInfo("phone", "Điện thoại", "dien-thoai"), CategoryInfo("laptop", "Laptop", "laptop"),
        CategoryInfo("tai-nghe", "Tai nghe", "tai-nghe"),
        # VieTech's real data: this child's slug is "samsung", which is also a brand.
        CategoryInfo("battery", "Điện thoại pin trâu", "samsung", "phone"),
        CategoryInfo("mid", "Điện thoại tầm trung", "dien-thoai-tam-trung", "phone"),
        CategoryInfo("two-in-one", "Laptop 2 trong 1", "laptop-2-trong-1", "laptop"),
        CategoryInfo("anc", "Tai nghe chống ồn chủ động", "tai-nghe-chong-on-chu-dong", "tai-nghe")),
        (BrandInfo("samsung", "Samsung", "samsung"),))
    assert analyze("Điện thoại Samsung dưới 10 triệu", vocab).category_id == "phone"  # Not the "samsung"-slug child.
    assert analyze("Điện thoại pin trâu dưới 8 triệu", vocab).category_id == "phone"
    assert analyze("Điện thoại tầm trung dưới 8 triệu", vocab).category_id == "phone"
    assert analyze("Laptop 2 trong 1 dưới 20 triệu", vocab).category_id == "two-in-one"
    assert analyze("Tai nghe chống ồn chủ động dưới 3 triệu", vocab).category_id == "anc"
    assert detect_needs("Laptop đồ họa dựng video") == ("creative",)


def test_grounding_accepts_catalog_facts_and_refuses_invented_ones():
    honor = ProductFacts("h", "HONOR X7d 8GB 256GB", "HONOR", ["HONOR X7d 8GB 256GB", "Pin: 6500 mAh"], {6890000})
    lucky = ProductFacts("m", "Meizu Lucky 08 8GB 256GB", "Meizu", ["Meizu Lucky 08 8GB 256GB", "Pin: 6000mAh"], {5500000})
    facts = Facts([honor, lucky], ["Điện thoại pin trâu dưới 8 triệu"], {8_000_000}, ("HONOR", "Meizu", "Samsung"),
                  False, ["h", "m"])
    good = "Trong tầm 8 triệu, HONOR X7d có pin 6.500 mAh (6.890.000 đ).\nMeizu Lucky 08 rẻ hơn, pin 6000 mAh."
    assert check_message(good, facts) == (good, [])
    for bad in ("Meizu Lucky 08 có pin 6.500 mAh.", "HONOR X7d pin dùng cả ngày.", "Samsung Galaxy A57 cũng tốt.",
                "Meizu Lucky 08 đứng đầu. HONOR X7d thứ hai.", "HONOR X7d phù hợp vì bạn đã mua HONOR trước đây.",
                "HONOR X7d đang giảm giá còn 6 triệu."):
        assert check_message(bad, facts)[1], bad
