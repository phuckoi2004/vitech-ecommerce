"""Store-policy questions (warranty, exchange, promotions), "why these products?" and "describe them in detail".

All are answered from backend data: policy lines from the services' rules and the catalog, the reasons from the
ranking formula re-applied to the products already shown, the descriptions from those products' catalog details.
Gemini only words the answer; when it fails or picks something ungrounded, the backend's own answer is shown instead
of an error. A shopping request without any criteria is answered with the backend's question first.
"""

import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.ai import ChatCompletion, ToolCall
from app.models import Coupon, Product, Promotion, User
from app.services.ai_intent import ConversationState, PastTurn, analyze
from app.services.exceptions import AiUnavailableError
from tests.test_ai_advisor import (LIST, NOW, PHONE_SPECS, PHONES, STATE, VOCAB, AdvisorModel, cards,  # noqa: F401
                                   store, turn_data)


def answer(arguments):
    return ChatCompletion("", "policy-fake", 10, 5,
                          (ToolCall("call_" + uuid.uuid4().hex, "present_answer", json.dumps(arguments)),))


class TurnModel:
    """AdvisorModel for ordinary turns; `respond(messages)` for the turn under test (may raise)."""

    def __init__(self, counters, respond):
        self.advisor, self.respond, self.notes = AdvisorModel(counters), respond, []

    def complete(self, messages, **kwargs):
        intent = turn_data(messages)["analysis"]["intent"]
        if intent in ("explain_recommendation", "policy_inquiry", "promotion_inquiry", "product_description"):
            self.notes.append(messages[0]["content"])
            return self.respond(messages)
        return self.advisor.complete(messages, **kwargs)


def provider_down(_messages):
    raise AiUnavailableError("AI tạm thời không khả dụng.")


@pytest.mark.parametrize("question,intent,topics", [
    ("Thông tin khuyến mãi bảo hành như nào", "policy_inquiry", ("promotion", "warranty")),
    ("Chính sách đổi trả thế nào?", "policy_inquiry", ("returns",)),
    ("Bảo hành bao lâu vậy?", "policy_inquiry", ("warranty",)),
    ("Xin chào, chính sách bảo hành như thế nào?", "policy_inquiry", ("warranty",)),
    ("Chính sách của shop ra sao?", "policy_inquiry", ("warranty", "returns")),
    ("Máy thứ hai bảo hành bao lâu?", "product_information", ()),  # A product's own warranty months.
    ("Máy thứ hai pin bao nhiêu và bảo hành mấy tháng?", "product_information", ()),
    ("Tư vấn laptop bảo hành 24 tháng dưới 20 triệu", "product_recommendation", ()),
    ("Có mã giảm giá nào không?", "promotion_inquiry", ()),
    ("Điện thoại đời mới nào pin trâu?", "product_recommendation", ()),  # "đời mới" folds like "đổi mới".
])
def test_policy_questions_are_recognized(question, intent, topics):
    result = analyze(question, VOCAB, STATE)
    assert (result.intent, result.topics) == (intent, topics)


@pytest.mark.parametrize("question,refs", [
    ("Bảo hành của 2 sản phẩm trên như thế nào", ["p1", "p2"]),
    ("Tôi muốn biết bảo hành của 2 sản phẩm trên", ["p1", "p2"]),
    ("Thủ tục bảo hành máy thứ hai như thế nào?", ["p2"]),
    ("Máy thứ hai bảo hành bao lâu và thủ tục thế nào?", ["p2"]),
    ("Chính sách đổi trả của 2 sản phẩm trên", ["p1", "p2"]),
])
def test_policy_questions_keep_the_referenced_products(question, refs):
    state = ConversationState((PastTurn({}, "compare", LIST[:2]),))
    result = analyze(question, VOCAB, state)
    assert result.intent == "policy_inquiry" and not result.clarification
    assert [ref["ProductId"] for ref in result.references] == refs
    assert result.topics == (("returns",) if "đổi trả" in question else ("warranty",))


@pytest.mark.parametrize("question", [
    "Bảo hành của 2 sản phẩm trên như thế nào",
    "Tôi muốn biết bảo hành của 2 sản phẩm trên",
])
@pytest.mark.parametrize("respond", [
    provider_down,
    lambda m: ChatCompletion("not json", "policy-fake"),
    lambda m: answer({"intent": "handoff", "message": "Bạn vui lòng liên hệ nhân viên để được hỗ trợ."}),
])
def test_warranty_of_the_two_products_just_compared_is_answered(store, question, respond):
    s = store
    model = TurnModel(s.counters, respond)
    svc = s.service(model)
    recommended = cards(s.ask(svc, "Tư vấn điện thoại dưới 8 triệu."))
    compared = cards(s.ask(svc, "So sánh máy thứ nhất và máy thứ hai về pin"))
    assert len(compared) == 2
    names = [card["ProductName"] for card in compared]
    with Session(s.engine) as db:
        for name, months in zip(names, (24, 0)):
            db.scalar(select(Product).where(Product.Name == name)).WarrantyMonths = months
        db.commit()

    reply = s.ask(svc, question)
    text = reply.AiMessages[0].Content
    assert reply.Status == "Completed" and cards(reply) == []
    assert text.startswith("Bảo hành:") and "tính từ ngày giao hàng thành công" in text
    assert f"1. {names[0]}: 24 tháng" in text and f"2. {names[1]}: không có bảo hành" in text
    assert recommended[2]["ProductName"] not in text
    meta = s.question(question)
    assert meta["AiIntent"]["Intent"] == "policy_inquiry" and meta["AiAnswerSource"] == "backend"
    assert "CHÍNH SÁCH VÀ ƯU ĐÃI VIETECH" in model.notes[-1]
    assert cards(s.ask(svc, "Máy thứ hai pin bao nhiêu?"))[0]["ProductName"] == names[1]


def test_warranty_policy_of_one_referenced_product_does_not_include_the_others(store):
    s = store
    svc = s.service(TurnModel(s.counters, provider_down))
    recommended = cards(s.ask(svc, "Tư vấn điện thoại dưới 8 triệu."))
    reply = s.ask(svc, "Thủ tục bảo hành máy thứ hai như thế nào?")
    text = reply.AiMessages[0].Content
    assert recommended[1]["ProductName"] in text
    assert all(card["ProductName"] not in text for card in (recommended[0], recommended[2]))


def test_grounded_warranty_wording_for_the_referenced_products_is_kept(store):
    s = store

    def worded(messages):
        products = turn_data(messages)["referenced"]["Products"]
        return answer({"intent": "policy", "message": "Bảo hành các sản phẩm:\n" + "\n".join(
            f"- {p['Name']}: bảo hành {p['WarrantyMonths']} tháng." for p in products)})

    svc = s.service(TurnModel(s.counters, worded))
    s.ask(svc, "Tư vấn điện thoại dưới 8 triệu.")
    compared = cards(s.ask(svc, "So sánh máy thứ nhất và máy thứ hai về pin"))
    question = "Tôi muốn biết bảo hành của 2 sản phẩm trên"
    reply = s.ask(svc, question)
    assert reply.AiMessages[0].Content == "Bảo hành các sản phẩm:\n" + "\n".join(
        f"- {p['ProductName']}: bảo hành 12 tháng." for p in compared)
    assert s.question(question)["AiAnswerSource"] == "model"


def test_why_questions_explain_the_list_just_shown():
    for question in ("Tại sao bạn lại đề xuất cho tôi những máy này", "Tại sao bạn lại đề xuất cho tôi 3 máy này",
                     "Vì sao lại chọn máy này?", "Dựa vào đâu bạn gợi ý vậy?"):
        result = analyze(question, VOCAB, STATE)
        assert result.intent == "explain_recommendation" and not result.clarification, question
        assert [ref["ProductId"] for ref in result.references] == ["p1", "p2", "p3"]
        assert result.filters()["max_price"] == 8_000_000 and result.needs == ("battery",)  # The criteria in force.
    second = analyze("Vì sao bạn chọn máy thứ hai?", VOCAB, STATE)
    assert second.intent == "explain_recommendation" and [r["ProductId"] for r in second.references] == ["p2"]
    two = ConversationState((PastTurn({}, "recommend", LIST[:2]),))
    assert analyze("Tại sao đề xuất máy thứ ba?", VOCAB, two).clarification.startswith("Danh sách vừa rồi chỉ có 2")
    assert analyze("Tại sao bạn đề xuất vậy?", VOCAB).intent != "explain_recommendation"  # Nothing shown yet.
    assert analyze("Tại sao máy thứ nhất pin yếu hơn?", VOCAB, STATE).intent == "product_information"  # Not a "why chosen".
    single = ConversationState((PastTurn({}, "product", LIST[:1]),))
    assert analyze("Sao bạn lại gợi ý máy này?", VOCAB, single).references == LIST[:1]


@pytest.mark.parametrize("respond", [
    provider_down,  # Gemini 503: the backend answer is shown instead of "AI tạm thời không khả dụng".
    lambda m: answer({"intent": "compare", "products": [{"product_id": str(uuid.uuid4())},
                                                        {"product_id": str(uuid.uuid4())}]}),  # Unknown products.
    lambda m: answer({"intent": "product", "message": "x"}),  # Invalid arguments (product without products).
])
def test_why_answer_comes_from_the_ranking_even_when_the_model_fails(store, respond):
    s = store
    model = TurnModel(s.counters, respond)
    svc = s.service(model)
    first = s.ask(svc, "Tư vấn điện thoại dưới 8 triệu.")
    shown = [c["ProductName"] for c in cards(first)]

    why = s.ask(svc, "Tại sao bạn lại đề xuất cho tôi những máy này")
    text = why.AiMessages[0].Content
    assert why.Status == "Completed" and cards(why) == []  # Text only: the cards are already on screen.
    assert text.startswith("Mình chọn từ các sản phẩm đang bán và còn hàng tại VieTech") and "8.000.000 đ" in text
    assert [text.index(name) for name in shown] == sorted(text.index(name) for name in shown)
    assert text.count("Phù hợp:") == 3 and "chip" in text
    meta = s.question("Tại sao bạn lại đề xuất cho tôi những máy này")
    assert meta["AiIntent"]["Intent"] == "explain_recommendation" and meta["AiAnswerSource"] == "backend"
    note = model.notes[-1]
    assert "SẢN PHẨM KHÁCH ĐANG NHẮC TỚI (backend" in note and '"Matched"' in note
    assert "KẾT QUẢ search_products BACKEND ĐÃ CHẠY" not in note  # No new search: the shown products are explained.

    # The explanation keeps the list: "máy thứ hai" is still the second card of the first answer.
    second = s.ask(svc, "Máy thứ hai pin bao nhiêu?")
    assert [c["ProductName"] for c in cards(second)] == [shown[1]]


def test_a_grounded_why_message_from_the_model_is_shown(store):
    s = store

    def explain(messages):
        products = turn_data(messages)["referenced"]["Products"]
        lines = [f"- {p['Name']}: {p['Ranking']['Matched'][0]}." for p in products]
        return answer({"intent": "explain", "message": "Mình chọn theo cấu hình và ngân sách của bạn:\n" + "\n".join(lines)})

    svc = s.service(TurnModel(s.counters, explain))
    s.ask(svc, "Tư vấn điện thoại dưới 8 triệu.")
    why = s.ask(svc, "Vì sao lại chọn mấy máy này?")
    assert why.AiMessages[0].Content.startswith("Mình chọn theo cấu hình và ngân sách của bạn:")
    assert s.question("Vì sao lại chọn mấy máy này?")["AiAnswerSource"] == "model"


def add_coupon(s, code="VIETECH300K"):
    with Session(s.engine) as db:
        owner = db.scalar(select(User).where(User.Email == "advisor@example.test"))
        promotion = Promotion(CreatedByUserId=owner.UserId, Name="Giảm 300K", ApplyMode="Coupon", Status="Active",
                              DiscountType="FixedAmount", DiscountValue=300000, MinOrderValue=5000000,
                              StartDate=NOW - timedelta(days=1), EndDate=NOW + timedelta(days=10))
        db.add(promotion); db.flush()
        db.add(Coupon(PromotionId=promotion.PromotionId, CreatedByUserId=owner.UserId, Code=code, Name="Giảm 300K",
                      UsageLimit=100, UsedCount=0))
        db.commit()


@pytest.mark.parametrize("respond", [
    provider_down,
    lambda m: ChatCompletion("not json", "policy-fake", 10, 5),  # The 15:50 failure: no valid final answer.
    lambda m: answer({"intent": "handoff"}),  # The old contract sent warranty questions away.
])
def test_promotion_and_warranty_question_is_answered_from_policy_data(store, respond):
    s = store
    add_coupon(s)
    model = TurnModel(s.counters, respond)
    svc = s.service(model)
    s.ask(svc, "Tư vấn điện thoại dưới 8 triệu.")

    reply = s.ask(svc, "Thông tin khuyến mãi bảo hành như nào")
    text = reply.AiMessages[0].Content
    assert reply.Status == "Completed" and cards(reply) == []
    assert text.startswith("Khuyến mãi:") and "\n\nBảo hành:" in text
    assert "VIETECH300K: giảm 300.000 đ; đơn tối thiểu 5.000.000 đ; hạn 01/11/2026" in text
    assert "tính từ ngày giao hàng thành công" in text
    assert "Thời hạn bảo hành của các mẫu vừa giới thiệu:\n- 1." in text and "12 tháng" in text
    meta = s.question("Thông tin khuyến mãi bảo hành như nào")
    assert meta["AiIntent"]["Intent"] == "policy_inquiry" and meta["AiIntent"]["Topics"] == ["promotion", "warranty"]
    assert "CHÍNH SÁCH VÀ ƯU ĐÃI VIETECH" in model.notes[-1] and "VIETECH300K" in model.notes[-1]

    # The policy turn does not replace the list: "máy thứ nhất" still refers to the recommendation.
    assert cards(s.ask(svc, "Máy thứ nhất pin bao nhiêu?"))


def test_return_policy_states_the_configured_window_and_grounded_wording_is_kept(store, monkeypatch):
    s = store
    monkeypatch.setenv("RETURN_WINDOW_DAYS", "15")

    def worded(messages):
        return answer({"intent": "policy", "message": "Bạn gửi yêu cầu đổi trả trong 15 ngày kể từ ngày giao hàng, "
                                                      "đơn đổi được miễn phí giao hàng tiêu chuẩn."})

    svc = s.service(TurnModel(s.counters, worded))
    reply = s.ask(svc, "Chính sách đổi trả thế nào?")
    assert reply.AiMessages[0].Content.startswith("Bạn gửi yêu cầu đổi trả trong 15 ngày")
    assert s.question("Chính sách đổi trả thế nào?")["AiAnswerSource"] == "model"

    def invented(messages):
        return answer({"intent": "policy", "message": "Đổi trả trong 30 ngày, bảo hành 1 đổi 1."})

    svc = s.service(TurnModel(s.counters, invented))
    reply = s.ask(svc, "Đổi trả được không?")
    text = reply.AiMessages[0].Content
    assert text.startswith("Đổi trả:\n- Gửi yêu cầu đổi trả trong 15 ngày kể từ ngày giao hàng") and "30 ngày" not in text
    issues = s.question("Đổi trả được không?")["AiGroundingIssues"]
    assert any("30" in issue for issue in issues) and any("1 doi 1" in issue for issue in issues)


def test_quota_errors_still_fail_so_the_cool_down_applies(store):
    s = store

    def quota(_messages):
        raise AiUnavailableError("AI tạm hết hạn mức.", code="ai_quota_exceeded", retry_after_seconds=30)

    svc = s.service(TurnModel(s.counters, quota))
    with pytest.raises(AiUnavailableError) as error:
        s.ask(svc, "Chính sách bảo hành thế nào?")
    assert error.value.code == "ai_quota_exceeded"


@pytest.mark.parametrize("question,intent,refs", [
    ("Tôi muốn biết mô tả cụ thể của từng máy", "product_description", ["p1", "p2", "p3"]),
    ("Cho tôi biết thông tin cụ thể hơn 3 chiếc latop", "product_description", ["p1", "p2", "p3"]),
    ("Giới thiệu chi tiết các máy này", "product_description", ["p1", "p2", "p3"]),
    ("Cho tôi xem cấu hình từng máy", "product_description", ["p1", "p2", "p3"]),
    ("Giới thiệu thêm về máy thứ hai", "product_description", ["p2"]),  # Not "đề xuất thêm".
    ("Đánh giá máy thứ nhất", "product_description", ["p1"]),
    ("Giới thiệu 3 mẫu khác", "recommend_more", []),
    ("Máy thứ hai pin bao nhiêu?", "product_information", ["p2"]),
    ("Thông tin cụ thể laptop dưới 20 triệu", "product_recommendation", []),  # New criteria: a new search.
])
def test_detail_requests_about_shown_products_are_recognized(question, intent, refs):
    result = analyze(question, VOCAB, STATE)
    assert (result.intent, [ref["ProductId"] for ref in result.references]) == (intent, refs)


def test_more_detail_means_the_product_last_talked_about():
    focus = ConversationState((PastTurn({"CategoryId": "phone"}, "recommend", LIST),
                               PastTurn({"CategoryId": "phone"}, "product", LIST[1:2])))
    assert [r["ProductId"] for r in analyze("Mô tả chi tiết hơn", VOCAB, focus).references] == ["p2"]
    assert [r["ProductId"] for r in analyze("Mô tả cụ thể từng máy", VOCAB, focus).references] == ["p1", "p2", "p3"]
    assert analyze("Mô tả chi tiết hơn", VOCAB).intent != "product_description"  # Nothing shown yet.


@pytest.mark.parametrize("respond", [
    provider_down,
    lambda m: answer({"intent": "product", "products": [{"product_id": str(uuid.uuid4())}]}),  # Unknown product.
    lambda m: answer({"intent": "product", "products": [{"product_id": p["ProductId"]} for p in turn_data(m)[
        "referenced"]["Products"]], "message": "Máy đầu có pin 9000 mAh."}),  # Invented spec: wording replaced.
])
def test_description_of_shown_products_is_answered_from_the_catalog(store, respond):
    s = store
    model = TurnModel(s.counters, respond)
    svc = s.service(model)
    shown = [c["ProductName"] for c in cards(s.ask(svc, "Tư vấn điện thoại dưới 8 triệu."))]

    reply = s.ask(svc, "Tôi muốn biết mô tả cụ thể của từng máy")
    text = reply.AiMessages[0].Content
    assert reply.Status == "Completed" and cards(reply) == []
    assert [text.index(name) for name in shown] == sorted(text.index(name) for name in shown)
    for name in shown:
        specs = PHONE_SPECS[name]
        assert f"- Chipset: {specs['Chipset']}" in text and f"- Pin: {specs['Pin']}" in text
    assert text.count("Phiên bản Bản tiêu chuẩn:") == 3 and text.count("- Bảo hành: 12 tháng.") == 3
    assert "9000 mAh" not in text
    meta = s.question("Tôi muốn biết mô tả cụ thể của từng máy")
    assert meta["AiIntent"]["Intent"] == "product_description" and meta["AiAnswerSource"] == "backend"
    assert '"Specifications"' in model.notes[-1] and "KẾT QUẢ search_products BACKEND ĐÃ CHẠY" not in model.notes[-1]

    # The description keeps the list and the focus.
    assert [c["ProductName"] for c in cards(s.ask(svc, "Máy thứ hai pin bao nhiêu?"))] == [shown[1]]
    detail = s.ask(svc, "Mô tả chi tiết hơn")
    assert shown[1] in detail.AiMessages[0].Content and shown[0] not in detail.AiMessages[0].Content


def test_a_grounded_description_from_the_model_is_shown(store):
    s = store

    def describe(messages):
        products = turn_data(messages)["referenced"]["Products"]
        lines = [f"- {p['Name']}: chip {p['Specifications']['Chipset']}, pin {p['Specifications']['Pin']}, "
                 f"bảo hành {p['WarrantyMonths']} tháng." for p in products]
        return answer({"intent": "product", "products": [{"product_id": p["ProductId"]} for p in products],
                       "message": "Chi tiết từng mẫu:\n" + "\n".join(lines)})

    svc = s.service(TurnModel(s.counters, describe))
    s.ask(svc, "Tư vấn điện thoại dưới 8 triệu.")
    reply = s.ask(svc, "Giới thiệu chi tiết các máy này")
    assert reply.AiMessages[0].Content.startswith("Chi tiết từng mẫu:")
    assert s.question("Giới thiệu chi tiết các máy này")["AiAnswerSource"] == "model"


@pytest.mark.parametrize("question,asks", [
    ("Tôi muốn mua 1 chiếc điện thoại", True), ("Tư vấn laptop cho tôi", True), ("Tôi cần mua máy", True),
    ("Tư vấn điện thoại dưới 8 triệu", False), ("Điện thoại pin trâu", False), ("Có laptop ASUS nào không?", False),
    ("Điện thoại rẻ nhất", False), ("Tôi muốn mua iPhone", False),
])
def test_a_request_without_criteria_is_answered_with_a_question(question, asks):
    result = analyze(question, VOCAB)
    assert result.intent == "product_recommendation" and bool(result.clarification) == asks
    if asks:
        assert "Ngân sách" in result.clarification or "ngân sách" in result.clarification


def test_the_reply_to_the_question_fills_the_criteria_and_is_never_asked_twice():
    asked = ConversationState((PastTurn({"CategoryId": "phone"}, "clarify", ()),))
    reply = analyze("Tầm 8 triệu, chơi game", VOCAB, asked)
    assert (reply.category_id, reply.max_budget, reply.needs, reply.clarification) == ("phone", 8_000_000, ("gaming",), None)
    for answer_ in ("Tùy bạn", "Gì cũng được", "Tôi muốn mua 1 chiếc điện thoại"):
        result = analyze(answer_, VOCAB, asked)
        assert (result.intent, result.category_id, result.clarification) == ("product_recommendation", "phone", None)
    assert analyze("Giờ tôi muốn laptop", VOCAB, STATE).clarification  # A new need group is asked again.
    assert not analyze("Tôi muốn điện thoại", VOCAB, STATE).clarification  # The 8-triệu budget is still in force.


def test_a_vague_request_asks_first_then_recommends_from_the_answer(store):
    s = store
    model = AdvisorModel(s.counters)
    svc = s.service(model)
    first = s.ask(svc, "Tôi muốn mua 1 chiếc điện thoại")
    assert first.Status == "Completed" and cards(first) == [] and model.calls == []  # Asked without a model call.
    assert first.AiMessages[0].Content.startswith("Để tư vấn điện thoại phù hợp với bạn")
    reply = s.ask(svc, "Tầm 8 triệu, chơi game")
    phones = {name: price for name, _, price, _ in PHONES}
    assert len(cards(reply)) == 3 and all(phones[c["ProductName"]] <= 8_000_000 for c in cards(reply))


def test_a_literal_backslash_n_from_the_model_becomes_a_line_break():
    from app.services.ai_grounding import Facts, check_message
    message, issues = check_message(r"Mình gợi ý 2 mẫu:\n\n- Mẫu một.\r\n- Mẫu hai.", Facts())
    assert (message, issues) == ("Mình gợi ý 2 mẫu:\n\n- Mẫu một.\n- Mẫu hai.", [])
