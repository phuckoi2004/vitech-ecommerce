"""The six failing October 29 acceptance cases, on isolated SQLite and scripted providers."""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.models import Brand, Category, Product
from app.services.ai_intent import CategoryInfo, BrandInfo, Vocabulary, ConversationState, PastTurn, analyze
from app.services.ai_product_requirements import feature_evidence
from tests.test_ai_grounded import ask, finish, grounded_shop  # noqa: F401
from tests.test_ai_recommendation import laptops  # noqa: F401
from tests.test_ai_compatibility import check, compatibility_shop, show, snapshot  # noqa: F401


VOCAB = Vocabulary((CategoryInfo("laptop", "Laptop", "laptop"),), tuple(
    BrandInfo(name.lower(), name, name.lower()) for name in ("ASUS", "Lenovo", "HP")))


@pytest.mark.parametrize("question", [
    "Laptop ASUS hoặc Lenovo dưới 25 triệu",
    "Laptop gaming RAM 16GB của ASUS hoặc Lenovo dưới 30 triệu",
    "Chỉ lấy laptop ASUS hoặc Lenovo",
    "Chỉ ASUS hoặc Lenovo dưới 25 triệu",
])
def test_ar03_ct03_alternative_brands_are_a_required_union(question):
    intent = analyze(question, VOCAB)
    assert set(intent.brand_ids) == {"asus", "lenovo"}
    assert intent.soft_brand_ids == ()
    assert set(intent.filters()["brand_ids"]) == {"asus", "lenovo"}
    assert set(intent.model_note(VOCAB)["brands_required"]) == {"ASUS", "Lenovo"}


def test_ct03_ram_refinement_and_reload_keep_brand_union_and_budget():
    initial = analyze("Laptop ASUS hoặc Lenovo dưới 25 triệu", VOCAB)
    state = ConversationState((PastTurn(initial.to_metadata()["Slots"], "recommend"),))
    refined = analyze("Chỉ lấy máy RAM từ 16GB", VOCAB, state)
    assert refined.intent == "product_recommendation"
    assert refined.filters()["min_ram_gb"] == 16
    assert refined.filters()["max_price"] == 25000000
    assert set(refined.filters()["brand_ids"]) == {"asus", "lenovo"}
    reloaded = ConversationState((PastTurn(refined.to_metadata()["Slots"], "recommend"),))
    more = analyze("Còn mẫu khác không?", VOCAB, reloaded)
    assert more.filters()["min_ram_gb"] == 16
    assert set(more.filters()["brand_ids"]) == {"asus", "lenovo"}
    reset = analyze("Laptop hãng nào cũng được", VOCAB, reloaded)
    assert not reset.filters().get("brand_ids")


def test_explicit_soft_preferences_still_allow_other_brands():
    intent = analyze("Laptop dưới 25 triệu, ưu tiên ASUS hoặc Lenovo", VOCAB)
    assert not intent.brand_ids
    assert set(intent.soft_brand_ids) == {"asus", "lenovo"}


@pytest.mark.parametrize("question", ["Không cần ANC, tìm mẫu khác", "Không yêu cầu chống ồn nữa"])
def test_explicitly_relaxing_anc_does_not_keep_the_old_hard_filter(question):
    initial = analyze("Tai nghe chống ồn dưới 3 triệu", VOCAB)
    state = ConversationState((PastTurn(initial.to_metadata()["Slots"], "recommend"),))
    assert not analyze(question, VOCAB, state).required_features


def test_ar03_brand_union_and_gaming_class_filter_actual_cards(laptops):
    shop = laptops
    with Session(shop.engine) as db:
        for name in ("dev-pro", "mid-dev", "office-basic"):
            product = db.get(Product, uuid.UUID(shop.products[name]))
            product.Specifications = {**product.Specifications, "GPU": "NVIDIA GeForce RTX 4050" if name == "mid-dev"
                                      else "Intel UHD Graphics"}
        db.commit()
    service, _ = shop.service([finish("recommend", shop.products["mid-dev"])])
    result = ask(shop, service, "Laptop gaming RAM 16GB của ASUS hoặc Lenovo dưới 30 triệu")
    assert [card.Metadata["ProductId"] for card in result.AiMessages[1:]] == [shop.products["mid-dev"]]


def test_ct03_actual_refinement_never_introduces_a_third_brand(laptops):
    shop = laptops
    service, _ = shop.service([finish("recommend", shop.products["mid-dev"], shop.products["dev-pro"])])
    first = ask(shop, service, "Laptop ASUS hoặc Lenovo dưới 25 triệu")
    assert {card.Metadata["ProductId"] for card in first.AiMessages[1:]} == {
        shop.products["mid-dev"], shop.products["dev-pro"]}
    service, _ = shop.service([finish("recommend", shop.products["mid-dev"], shop.products["dev-pro"])])
    second = ask(shop, service, "Chỉ lấy máy RAM từ 16GB")
    assert {card.Metadata["ProductId"] for card in second.AiMessages[1:]} == {
        shop.products["mid-dev"], shop.products["dev-pro"]}


@pytest.mark.parametrize("specs,expected", [
    ({"Tính năng": "Chống ồn chủ động ANC"}, True),
    ({"Âm thanh": {"ANC": True}}, True),
    ({"ANC": False}, False),
    ({"ANC": "Không"}, False),
    ({"Tính năng": "Không hỗ trợ ANC"}, False),
    ({"Micro": "Chống ồn cuộc gọi ENC"}, False),
    ({"Tính năng": "Chống ồn đàm thoại"}, False),
    ({"Pin": "8 giờ khi tắt ANC"}, False),
    ({"Tính năng": "Chống ồn thụ động"}, False),
    ({}, False),
])
def test_r09_only_confirmed_listening_anc_is_eligible(specs, expected):
    detail = SimpleNamespace(Name="Tai nghe", Specifications=specs)
    assert bool(feature_evidence(detail, "anc")) is expected


def test_r09_real_recommendation_filters_unconfirmed_and_call_noise_reduction(grounded_shop):
    shop = grounded_shop
    with Session(shop.engine) as db:
        headphones = Category(Name="Tai nghe", Slug="tai-nghe")
        db.add(headphones); db.flush()
        for name, specs in [("asus-zen", {"Tính năng": "Chống ồn chủ động ANC"}),
                            ("asus-vivo", {"Micro": "ENC chống ồn cuộc gọi"}),
                            ("lenovo-idea", {})]:
            product = db.get(Product, uuid.UUID(shop.products[name]))
            product.CategoryId = headphones.CategoryId
            product.Specifications = specs
        db.commit()
    service, _ = shop.service([finish("recommend", shop.products["asus-zen"])])
    result = ask(shop, service, "Tai nghe chống ồn dưới 25 triệu")
    assert [card.Metadata["ProductId"] for card in result.AiMessages[1:]] == [shop.products["asus-zen"]]
    assert "Có chống ồn chủ động ANC" in result.AiMessages[0].Content


@pytest.mark.parametrize("question", ["Có Dell XPS 13 không?", "Laptop Dell XPS 13 giá bao nhiêu?"])
def test_n03_absent_dell_xps_is_not_replaced_by_another_dell(laptops, question):
    service, model = laptops.service([])
    result = ask(laptops, service, question)
    assert model.calls == []
    assert len(result.AiMessages) == 1
    assert "chưa tìm thấy" in result.AiMessages[0].Content
    assert "dell xps 13" in result.AiMessages[0].Content.lower()


def test_ct02_newer_chip_followup_answers_generation_instead_of_generic_fit(compatibility_shop):
    shop = compatibility_shop
    with Session(shop.engine) as db:
        for name, generation in (("asus-zen", 3), ("lenovo-idea", 4)):
            product = db.get(Product, uuid.UUID(shop.products[name]))
            product.Name = f"iPad Air 11 M{generation}"
            product.Specifications = {**product.Specifications, "Loại CPU": "CPU 8 lõi với các lõi hiệu năng và tiết kiệm điện",
                                      "Chip xử lý": f"Chip Apple M{generation}"}
        db.commit()
    service, _ = shop.service([])
    ask(shop, service, "So sánh iPad Air 11 M3 và iPad Air 11 M4")
    shop.now.value += timedelta(seconds=1)
    service, model = shop.service([])
    result = ask(shop, service, "Máy nào có chip mới hơn?")
    assert not model.calls
    assert "Apple M4, thuộc thế hệ chip mới hơn M3" in result.AiMessages[0].Content
    assert "Chưa đủ căn cứ để chọn" not in result.AiMessages[0].Content
    assert result.AiMessages[0].Metadata["Comparison"]["RecommendedProductVariantId"] is None


def test_ct04_brand_only_monitor_then_mode_followup_keeps_laptop_and_asks_for_model(compatibility_shop):
    shop = compatibility_shop
    shown = show(shop, ["asus-zen", "lenovo-idea"], "Giới thiệu hai laptop dưới 25 triệu")
    second_id = shown.AiMessages[2].Metadata["ProductId"]
    result, _, _ = check(shop, "Máy thứ hai có kết nối được màn hình LG đang bán trong VieTech không?", steps=[])
    assert "LG đang bán" not in result.AiMessages[0].Content
    assert "Có nhiều màn hình" in result.AiMessages[0].Content
    shop.now.value += timedelta(seconds=1)
    result, _, _ = check(shop, "Nếu muốn xuất 4K144Hz thì sao?", steps=[])
    assert "chưa tìm thấy" not in result.AiMessages[0].Content
    assert "Bạn gửi tên/model màn hình" in result.AiMessages[0].Content
    shop.now.value += timedelta(seconds=1)
    result, _, _ = check(shop, "LG 27GR93U")
    data = snapshot(result)
    assert data["Request"]["Width"] == 3840 and data["Request"]["RefreshHz"] == 144
    assert [p["ProductId"] for p in data["Products"]] == [second_id, shop.products["lg-27"]]
