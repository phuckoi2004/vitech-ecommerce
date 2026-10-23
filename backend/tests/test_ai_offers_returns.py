"""Focused offers and after-sales replies, using the public catalog and current exchange rules."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Brand, Category, Coupon, Product, ProductVariant, Promotion, PromotionCategory, PromotionProduct, User
from app.schemas.ai_chat import ListOffersArguments, PresentAnswerArguments
from app.services.ai_grounding import Facts, ProductFacts, check_message
from app.services.ai_intent import ConversationState, PastTurn, analyze
from app.services.ai_tools import AiTools, GroundingContext
from app.services.pricing import PricingService
from tests.test_ai_advisor import LIST, NOW, VOCAB, cards, store  # noqa: F401
from tests.test_ai_policy_explain import TurnModel, answer, provider_down


def offer(s, code, *, product_id=None, category_id=None, automatic=False, amount=100000, minimum=0,
          discount_type="FixedAmount", maximum=None, description=None):
    with Session(s.engine) as db:
        owner = db.scalar(select(User).where(User.Email == "advisor@example.test"))
        promotion = Promotion(CreatedByUserId=owner.UserId, Name=code, ApplyMode="Automatic" if automatic else "Coupon",
                              Status="Active", DiscountType=discount_type, DiscountValue=amount, MinOrderValue=minimum,
                              MaxDiscountAmount=maximum,
                              Description=description,
                              StartDate=NOW - timedelta(days=1), EndDate=NOW + timedelta(days=10))
        db.add(promotion); db.flush()
        if product_id:
            db.add(PromotionProduct(PromotionId=promotion.PromotionId, ProductId=uuid.UUID(product_id)))
        if category_id:
            db.add(PromotionCategory(PromotionId=promotion.PromotionId, CategoryId=category_id))
        if not automatic:
            db.add(Coupon(PromotionId=promotion.PromotionId, CreatedByUserId=owner.UserId, Code=code,
                          Name=code, UsageLimit=100, UsedCount=0))
        db.commit()
        return promotion.PromotionId


@pytest.mark.parametrize("question", [
    "Khuyến mãi sản phẩm như nào",
    "Khuyến mãi các sản phẩm trên như nào",
    "Khuyến mãi đối với sản phẩm trên như nào",
    "Khuyến mãi như nào?",
    "Ưu đãi như nào?",
    "Có mã giảm giá nào phù hợp không?",
])
def test_product_promotion_questions_resolve_the_shown_list(question):
    state = ConversationState((PastTurn({}, "compare", LIST[:2]),))
    result = analyze(question, VOCAB, state)
    assert result.intent == "promotion_inquiry"
    assert [ref["ProductId"] for ref in result.references] == ["p1", "p2"]


def test_product_above_promotions_resolve_the_latest_focus():
    state = ConversationState((PastTurn({}, "product", LIST[1:2]),))
    assert analyze("Khuyến mãi sản phẩm trên như nào", VOCAB, state).references == LIST[1:2]
    multiple = ConversationState((PastTurn({}, "compare", LIST[:2]),))
    result = analyze("Khuyến mãi sản phẩm trên như nào", VOCAB, multiple)
    assert result.references == LIST[:2] and not result.clarification
    assert analyze("Khuyến mãi sản phẩm trên như nào", VOCAB).clarification


def test_promotion_follow_ups_keep_the_shown_category_unless_customer_changes_scope():
    state = ConversationState((PastTurn({"CategoryId": "phone"}, "recommend", LIST[:2]),))
    assert analyze("Điện thoại có ưu đãi gì?", VOCAB, state).references == LIST[:2]
    assert not analyze("Laptop có ưu đãi gì?", VOCAB, state).references
    assert not analyze("Cửa hàng có khuyến mãi gì?", VOCAB, state).references


@pytest.mark.parametrize("question", [
    "Khuyến mãi sản phẩm như nào",
    "Khuyến mãi các sản phẩm trên như nào",
    "Khuyến mãi đối với sản phẩm trên như nào",
    "Khuyến mãi như nào?",
    "Ưu đãi như nào?",
    "Có mã giảm giá nào phù hợp không?",
])
@pytest.mark.parametrize("respond", [provider_down, lambda m: answer({"intent": "handoff"})])
def test_offers_are_per_product_and_do_not_include_other_product_coupons(store, question, respond):
    s = store
    svc = s.service(TurnModel(s.counters, respond))
    recommended = cards(s.ask(svc, "Tư vấn điện thoại dưới 8 triệu."))
    compared = cards(s.ask(svc, "So sánh máy thứ nhất và máy thứ hai về pin"))
    ids = [p["ProductId"] for p in compared]
    offer(s, "FIRST100", product_id=ids[0])
    offer(s, "SECOND100", product_id=ids[1])
    offer(s, "OTHER100", product_id=recommended[2]["ProductId"])
    offer(s, "AUTO300", product_id=ids[0], automatic=True, amount=300000)
    reply = s.ask(svc, question)
    text = reply.AiMessages[0].Content
    assert reply.Status == "Completed" and not cards(reply)
    assert all(p["ProductName"] in text for p in compared)
    assert "FIRST100" in text and "SECOND100" in text and "OTHER100" not in text
    assert "giảm 300.000 đ" in text and "giá gốc" in text
    assert recommended[2]["ProductName"] not in text
    assert cards(s.ask(svc, "Máy thứ hai pin bao nhiêu?"))[0]["ProductName"] == compared[1]["ProductName"]


@pytest.mark.parametrize("prepared", [False, True])
def test_unscoped_offer_tool_and_legacy_finish_keep_the_referenced_products(store, prepared):
    s = store
    recommended = cards(s.ask(s.service(TurnModel(s.counters, provider_down)), "Tư vấn điện thoại dưới 8 triệu."))
    refs = tuple(recommended[:2])
    offer(s, "FIRST100", product_id=refs[0]["ProductId"])
    offer(s, "SECOND100", product_id=refs[1]["ProductId"])
    offer(s, "OTHER100", product_id=recommended[2]["ProductId"])
    context = GroundingContext("Khuyến mãi đối với sản phẩm trên như nào",
                               state=ConversationState((PastTurn({}, "recommend", refs),)))
    with Session(s.engine) as db:
        tools = AiTools(db, clock=lambda: NOW)
        if prepared:
            tools.prepare(context)
        coupons = tools.list_offers(ListOffersArguments(), context)["Coupons"]
        assert {coupon["Code"] for coupon in coupons} == {"FIRST100", "SECOND100"}
        assert set(context.offer_scopes) == {ref["ProductId"] for ref in refs}
        context.policy = None  # The older finish path must not produce a store-wide promotion summary.
        text, products, _, _ = tools.finish(PresentAnswerArguments(intent="offers"), context, 5)
    assert not products and all(ref["ProductName"] in text for ref in refs)
    assert "FIRST100" in text and "SECOND100" in text and "OTHER100" not in text
    assert "Các mã ưu đãi công khai hiện có" not in text


def test_category_offers_exclude_coupons_for_other_categories(store):
    s = store
    phone = next(pid for name, pid in s.products.items() if "Samsung Galaxy" in name)
    laptop = next(pid for name, pid in s.products.items() if "Laptop Dell" in name)
    offer(s, "PHONE100", product_id=phone)
    offer(s, "LAPTOP100", product_id=laptop)
    svc = s.service(TurnModel(s.counters, provider_down))
    text = s.ask(svc, "Laptop có khuyến mãi gì?").AiMessages[0].Content
    assert "LAPTOP100" in text and "PHONE100" not in text


def offer_product(s, category):
    with Session(s.engine) as db:
        if category == "Tai nghe":
            parent = Category(Name=category, Slug="tai-nghe")
            brand = Brand(Name="Sony", Slug="sony")
            db.add_all([parent, brand]); db.flush()
            product = Product(Name="Tai nghe Sony WH-1000XM5", Slug="tai-nghe-kiem-thu", CategoryId=parent.CategoryId,
                              BrandId=brand.BrandId, Status="Active", WarrantyMonths=12)
            db.add(product); db.flush()
            variant = ProductVariant(ProductId=product.ProductId, Sku="headphone-offer", VariantName="Tiêu chuẩn",
                                     Price=900000, CostPrice=450000, StockQuantity=5)
            db.add(variant)
        else:
            name = "Samsung Galaxy A07 4GB 128GB" if category == "Điện thoại" else "Laptop Dell Inspiron 14 5440"
            product = db.get(Product, uuid.UUID(s.products[name]))
            variant = db.scalar(select(ProductVariant).where(ProductVariant.ProductId == product.ProductId))
        db.flush()
        ref = {"ProductId": str(product.ProductId), "ProductVariantId": str(variant.ProductVariantId),
               "ProductName": product.Name, "Rank": 1}
        category_id, price = product.CategoryId, int(variant.Price)
        db.commit()
        return ref, category_id, price


@pytest.mark.parametrize("category", ["Điện thoại", "Laptop", "Tai nghe"])
@pytest.mark.parametrize("mode", ["category", "shown", "named"])
def test_coupons_match_the_category_and_price_after_automatic_discount(store, category, mode):
    s = store
    ref, category_id, price = offer_product(s, category)
    offer(s, "AUTO100", product_id=ref["ProductId"], automatic=True)
    offer(s, "BEST200", product_id=ref["ProductId"], amount=200000, minimum=price - 100000)
    offer(s, "VALID100", category_id=category_id)
    offer(s, "PERCENT10", product_id=ref["ProductId"], amount=10, discount_type="Percentage", maximum=150000)
    offer(s, "TOOHIGH100", product_id=ref["ProductId"], minimum=price - 100000 + 1)
    offer(s, "BELOWCOST100", product_id=ref["ProductId"], amount=price)
    other_id = next(pid for name, pid in s.products.items()
                    if ("Laptop" in name) == (category == "Điện thoại"))
    offer(s, "UNRELATED100", product_id=other_id)
    specific = mode != "category"
    state = ConversationState((PastTurn({}, "product", (ref,)),)) if mode == "shown" else ConversationState()
    question = (f"Cho tôi hỏi ưu đãi giảm giá của sản phẩm {ref['ProductName']} như thế nào" if mode == "named" else
                "Sản phẩm trên có khuyến mãi gì?" if specific else f"{category} có ưu đãi gì?")
    context = GroundingContext(question, state=state)
    with Session(s.engine) as db:
        tools = AiTools(db, clock=lambda: NOW)
        tools.prepare(context)
        text, _, _, _ = tools.finish(PresentAnswerArguments(intent="offers"), context, 5)
        codes = [coupon["Code"] for coupon in context.offers]
        assert codes.index("BEST200") < codes.index("VALID100")
        assert "PERCENT10" in codes and "TOOHIGH100" not in codes and "BELOWCOST100" not in codes
        # Ordinary cart coupon listings can include codes requiring more than one item.
        assert "TOOHIGH100" in {c.Code for c in tools.pricing.public_coupons(product_id=uuid.UUID(ref["ProductId"]))}
    assert "BEST200" in text and "TOOHIGH100" not in text and "BELOWCOST100" not in text
    assert "UNRELATED100" not in text
    assert (ref["ProductName"] if specific else f"{category}:") in text
    if not specific:
        assert all(f"{other}:" not in text for other in {"Điện thoại", "Laptop", "Tai nghe"} - {category})


def test_a_coupon_uses_the_shown_variant_instead_of_a_more_expensive_variant(store):
    s = store
    ref, _, _ = offer_product(s, "Điện thoại")
    with Session(s.engine) as db:
        expensive = ProductVariant(ProductId=uuid.UUID(ref["ProductId"]), Sku="expensive-offer", VariantName="Cao cấp",
                                   Price=9000000, CostPrice=4500000, StockQuantity=5)
        db.add(expensive); db.flush()
        expensive_id = expensive.ProductVariantId
        db.commit()
    offer(s, "HIGHPRICE200", product_id=ref["ProductId"], amount=200000, minimum=8000000)
    with Session(s.engine) as db:
        pricing = PricingService(db, clock=lambda: NOW)
        args = {"product_id": uuid.UUID(ref["ProductId"]), "single_item": True}
        assert not pricing.public_coupons(**args, product_variant_id=uuid.UUID(ref["ProductVariantId"]))
        assert not pricing.public_coupons(**args)  # Default to the cheapest available variant.
        assert [c.Code for c in pricing.public_coupons(**args, product_variant_id=expensive_id)] == ["HIGHPRICE200"]


@pytest.mark.parametrize("previous_laptops", [False, True])
@pytest.mark.parametrize("respond", [provider_down, lambda m: answer({"intent": "offers", "message":
    "Mã LAPTOP5 giảm 5%, mã PHUKIEN10 giảm 10%, mã VIETECH300K giảm 300.000 đ."})])
def test_honor_8990000_gets_phone_category_offers_and_only_matching_coupons(store, previous_laptops, respond):
    s = store
    name = "HONOR 600S 5G 6GB 128GB"
    with Session(s.engine) as db:
        original = db.get(Product, uuid.UUID(s.products["HONOR X7d 8GB 256GB"]))
        honor = Product(Name=name, Slug="honor-600s", CategoryId=original.CategoryId, BrandId=original.BrandId,
                        Status="Active", WarrantyMonths=12)
        db.add(honor); db.flush()
        db.add(ProductVariant(ProductId=honor.ProductId, Sku="honor-600s", VariantName="6GB 128GB",
                              Price=8990000, CostPrice=4000000, StockQuantity=5))
        honor_id, phone_category = str(honor.ProductId), honor.CategoryId
        laptop = db.get(Product, uuid.UUID(s.products["Laptop Dell Inspiron 14 5440"]))
        laptop_category = laptop.CategoryId
        db.add(Category(Name="Chuột", Slug="chuot"))
        db.commit()
    _, headphone_category, _ = offer_product(s, "Tai nghe")
    other_phone = s.products["Samsung Galaxy A17 6GB 128GB"]
    offer(s, "PHONE_AUTO", product_id=other_phone, automatic=True, amount=2000000)
    offer(s, "LAPTOP_AUTO", product_id=s.products["Laptop Dell Inspiron 14 5440"], automatic=True, amount=3000000)
    offer(s, "DIENTHOAI200K", category_id=phone_category, minimum=5000000, amount=200000)
    offer(s, "VIETECH50K", minimum=1000000, amount=50000)
    offer(s, "VIETECH300K", minimum=10000000, amount=300000)
    offer(s, "LAPTOP5", category_id=laptop_category, minimum=15000000, amount=5, discount_type="Percentage")
    offer(s, "PHUKIEN10", minimum=300000, amount=10, discount_type="Percentage",
          description="Giảm 10% tối đa 100.000đ cho chuột, bàn phím, loa, pin sạc dự phòng, đơn từ 300.000đ.")
    offer(s, "OTHERPHONE100", product_id=other_phone)
    svc = s.service(TurnModel(s.counters, respond))
    if previous_laptops:
        s.ask(svc, "Tư vấn laptop dưới 20 triệu")
    question = f"Cho tôi hỏi ưu đãi giảm giá của sản phẩm {name} như thế nào"
    reply = s.ask(svc, question)
    text = reply.AiMessages[0].Content
    assert reply.Status == "Completed" and not cards(reply)
    assert name in text and "8.990.000 đ" in text
    assert "Điện thoại:" in text and "giảm tới 2.000.000 đ" in text
    assert "DIENTHOAI200K" in text and "VIETECH50K" in text
    assert all(code not in text for code in ("VIETECH300K", "LAPTOP5", "PHUKIEN10", "OTHERPHONE100", "Laptop:"))
    assert s.question(question)["AiIntent"]["References"] == [honor_id]
    again = s.ask(svc, "Ưu đãi như nào?").AiMessages[0].Content
    assert name in again and "DIENTHOAI200K" in again and "LAPTOP5" not in again


def test_unknown_named_product_does_not_fall_back_to_store_wide_promotions(store):
    s = store
    offer(s, "UNRELATED100")
    reply = s.ask(s.service(TurnModel(s.counters, provider_down)), "HONOR 9999 có khuyến mãi gì?")
    text = reply.AiMessages[0].Content
    assert reply.Status == "Completed" and "chưa tìm thấy sản phẩm" in text
    assert "UNRELATED100" not in text


def test_chat_respects_category_conditions_even_when_coupon_targets_are_missing(store):
    s = store
    headphones, _, _ = offer_product(s, "Tai nghe")
    phone, _, _ = offer_product(s, "Điện thoại")
    offer(s, "AUDIO10", minimum=300000, amount=10, discount_type="Percentage", description="Giảm 10% cho tai nghe.")
    offer(s, "GLOBAL50", minimum=300000, amount=50000, description="Áp dụng mọi sản phẩm.")
    with Session(s.engine) as db:
        pricing = PricingService(db, clock=lambda: NOW)
        assert {c.Code for c in pricing.public_coupons(product_id=uuid.UUID(headphones["ProductId"]), single_item=True)} == {"AUDIO10", "GLOBAL50"}
        assert {c.Code for c in pricing.public_coupons(product_id=uuid.UUID(phone["ProductId"]), single_item=True)} == {"GLOBAL50"}


def test_a_named_coupon_does_not_list_unrelated_codes_and_is_refreshed(store):
    s = store
    target = offer(s, "SAVE300", amount=300000)
    for index in range(6):
        offer(s, f"OTHER{index}100")

    def expire(messages):
        with Session(s.engine) as db:
            db.get(Promotion, target).EndDate = NOW - timedelta(seconds=1)
            db.commit()
        return answer({"intent": "offers", "message": "Mã SAVE300 vẫn còn áp dụng, giảm 300.000 đ."})

    svc = s.service(TurnModel(s.counters, provider_down))
    text = s.ask(svc, "Mã SAVE300 được giảm bao nhiêu?").AiMessages[0].Content
    assert "SAVE300" in text and "300.000 đ" in text and "OTHER" not in text
    text = s.ask(s.service(TurnModel(s.counters, expire)), "Mã SAVE300 còn áp dụng không?").AiMessages[0].Content
    assert "Chưa tìm thấy mã SAVE300 còn hiệu lực" in text and "300.000 đ" not in text


def test_how_to_use_a_coupon_answers_the_steps_without_listing_offers(store):
    s = store
    offer(s, "UNRELATED100")
    svc = s.service(TurnModel(s.counters, provider_down))
    text = s.ask(svc, "Cách áp dụng mã giảm giá?").AiMessages[0].Content
    assert "Mở giỏ hàng" in text and "Nhập mã" in text and "tổng thanh toán" in text
    assert "UNRELATED100" not in text


@pytest.mark.parametrize("question", [
    "Nếu máy lỗi có được đổi mới không?", "Tôi muốn đổi máy", "Tôi muốn trả lại sản phẩm",
    "Mua rồi không thích có được trả không?", "Chính sách đổi trả iPhone 17 thế nào?",
    "Máy thứ hai lỗi màn hình có được đổi trả không?",
])
def test_natural_exchange_and_return_questions_are_policy_questions(question):
    state = ConversationState((PastTurn({}, "compare", LIST[:2]),))
    result = analyze(question, VOCAB, state)
    assert result.intent == "policy_inquiry" and result.topics == ("returns",)


@pytest.mark.parametrize("question,expected,absent", [
    ("Đổi trả trong bao nhiêu ngày?", "trong 15 ngày", "chênh lệch"),
    ("Làm sao gửi yêu cầu đổi trả?", "Tài khoản → Bảo hành và đổi trả", "Mỗi yêu cầu đổi mới"),
    ("Trả hàng có được hoàn tiền không?", "chưa hỗ trợ yêu cầu trả hàng hoàn tiền mới", "trong 15 ngày"),
    ("Đổi trả phải bù chênh lệch thế nào?", "thanh toán thêm phần chênh lệch", "Serial/IMEI"),
    ("Tôi đã gửi yêu cầu đổi trả, xem tiến độ ở đâu?", "chọn yêu cầu đã gửi", "đủ điều kiện"),
])
def test_return_answers_address_the_requested_topic(store, monkeypatch, question, expected, absent):
    monkeypatch.setenv("RETURN_WINDOW_DAYS", "15")
    s = store
    svc = s.service(TurnModel(s.counters, provider_down))
    reply = s.ask(svc, question)
    assert reply.Status == "Completed" and not cards(reply)
    text = reply.AiMessages[0].Content
    assert expected in text and absent not in text


def test_a_model_cannot_promise_a_refund_that_the_active_workflow_does_not_support(store):
    s = store
    svc = s.service(TurnModel(s.counters, lambda m: answer({
        "intent": "policy", "message": "Bạn có thể trả hàng để được hoàn tiền."})))
    question = "Trả hàng có được hoàn tiền không?"
    reply = s.ask(svc, question)
    assert "chưa hỗ trợ yêu cầu trả hàng hoàn tiền mới" in reply.AiMessages[0].Content
    assert s.question(question)["AiAnswerSource"] == "backend"


def test_formatting_does_not_hide_ungrounded_product_claims():
    facts = Facts(products=[
        ProductFacts("a", "Galaxy A17", "Samsung", ["Galaxy A17", "Pin 5000 mAh"]),
        ProductFacts("b", "Galaxy A37", "Samsung", ["Galaxy A37", "Pin 7000 mAh"]),
    ])
    good = "### Thông số\n\n**Galaxy A17**: pin **5000 mAh**."
    assert check_message(good, facts) == (good, [])
    assert check_message("**Galaxy** A17: pin **7000 mAh**.", facts)[1]
