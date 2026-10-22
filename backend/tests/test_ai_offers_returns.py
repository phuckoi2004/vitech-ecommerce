"""Focused offers and after-sales replies, using the public catalog and current exchange rules."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Coupon, Promotion, PromotionProduct, User
from app.services.ai_grounding import Facts, ProductFacts, check_message
from app.services.ai_intent import ConversationState, PastTurn, analyze
from tests.test_ai_advisor import LIST, NOW, VOCAB, cards, store  # noqa: F401
from tests.test_ai_policy_explain import TurnModel, answer, provider_down


def offer(s, code, *, product_id=None, automatic=False, amount=100000):
    with Session(s.engine) as db:
        owner = db.scalar(select(User).where(User.Email == "advisor@example.test"))
        promotion = Promotion(CreatedByUserId=owner.UserId, Name=code, ApplyMode="Automatic" if automatic else "Coupon",
                              Status="Active", DiscountType="FixedAmount", DiscountValue=amount, MinOrderValue=0,
                              StartDate=NOW - timedelta(days=1), EndDate=NOW + timedelta(days=10))
        db.add(promotion); db.flush()
        if product_id:
            db.add(PromotionProduct(PromotionId=promotion.PromotionId, ProductId=uuid.UUID(product_id)))
        if not automatic:
            db.add(Coupon(PromotionId=promotion.PromotionId, CreatedByUserId=owner.UserId, Code=code,
                          Name=code, UsageLimit=100, UsedCount=0))
        db.commit()
        return promotion.PromotionId


@pytest.mark.parametrize("question", [
    "Khuyến mãi sản phẩm như nào",
    "Khuyến mãi các sản phẩm trên như nào",
])
def test_product_promotion_questions_resolve_the_shown_list(question):
    state = ConversationState((PastTurn({}, "compare", LIST[:2]),))
    result = analyze(question, VOCAB, state)
    assert result.intent == "promotion_inquiry"
    assert [ref["ProductId"] for ref in result.references] == ["p1", "p2"]


def test_singular_product_above_resolves_focus_or_asks_which_product():
    state = ConversationState((PastTurn({}, "product", LIST[1:2]),))
    assert analyze("Khuyến mãi sản phẩm trên như nào", VOCAB, state).references == LIST[1:2]
    multiple = ConversationState((PastTurn({}, "compare", LIST[:2]),))
    assert analyze("Khuyến mãi sản phẩm trên như nào", VOCAB, multiple).clarification


@pytest.mark.parametrize("question", [
    "Khuyến mãi sản phẩm như nào",
    "Khuyến mãi các sản phẩm trên như nào",
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


def test_category_offers_exclude_coupons_for_other_categories(store):
    s = store
    phone = next(pid for name, pid in s.products.items() if "Samsung Galaxy" in name)
    laptop = next(pid for name, pid in s.products.items() if "Laptop Dell" in name)
    offer(s, "PHONE100", product_id=phone)
    offer(s, "LAPTOP100", product_id=laptop)
    svc = s.service(TurnModel(s.counters, provider_down))
    text = s.ask(svc, "Laptop có khuyến mãi gì?").AiMessages[0].Content
    assert "LAPTOP100" in text and "PHONE100" not in text


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
