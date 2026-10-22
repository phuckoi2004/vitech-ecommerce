"""Five-card advice keeps quantity, ranking, follow-up references and conversational clarification aligned."""
import json
import uuid
from dataclasses import replace
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.ai_config import AiSettings
from app.schemas.ai_chat import GetProductArguments, PresentAnswerArguments
from app.services.ai_intent import ConversationState, PastTurn, analyze
from app.services.ai_tools import AiTools, GroundingContext
from app.services.exceptions import AiUnavailableError
from tests.test_ai_advisor import LIST, NOW, PHONES, VOCAB, AdvisorModel, cards, store, turn_data  # noqa: F401


class FiveProductsModel(AdvisorModel):
    def __init__(self, counters, count=5):
        super().__init__(counters)
        self.count = count

    def complete(self, messages, **kwargs):
        data = turn_data(messages)
        if data["analysis"]["intent"] not in ("product_recommendation", "recommend_more"):
            return super().complete(messages, **kwargs)
        assert self.counters["connections"] == 0
        self.calls.append(messages)
        products = data["search"]["Products"][:self.count]
        if not products:
            return self._answer({"intent": "no_results"})
        return self._answer({"intent": "recommend", "products": [{"product_id": p["ProductId"]} for p in products],
                             "message": "Mình tư vấn các mẫu này:\n\n" + "\n".join(p["Name"] for p in products)})


def test_default_and_schema_allow_five_but_reject_six():
    assert AiSettings().max_products == 5
    ids = [uuid.uuid4() for _ in range(6)]
    assert len(PresentAnswerArguments(intent="recommend", products=[{"product_id": pid} for pid in ids[:5]]).products) == 5
    assert GetProductArguments(rank=5).rank == 5
    assert len(GetProductArguments(product_ids=ids[:5]).product_ids) == 5
    with pytest.raises(AiUnavailableError):
        AiSettings(max_products=6)
    with pytest.raises(ValidationError):
        PresentAnswerArguments(intent="recommend", products=[{"product_id": pid} for pid in ids])
    with pytest.raises(ValidationError):
        GetProductArguments(rank=6)
    with pytest.raises(ValidationError):
        GetProductArguments(product_ids=ids)


@pytest.mark.parametrize("question", [
    "Hãy đề xuất tối đa 5 sản phẩm cho tôi", "Tư vấn 5 laptop dưới 20 triệu",
    "Tư vấn năm điện thoại dưới 8 triệu", "Tư vấn 8 sản phẩm",
])
def test_quantity_is_recognized_and_capped_at_five(question):
    assert analyze(question, VOCAB).requested_count == 5


def test_five_ranked_cards_and_the_fifth_product_are_available_on_the_next_turn(store):
    s = store
    svc = s.service(FiveProductsModel(s.counters))
    response = s.ask(svc, "Tư vấn 5 điện thoại dưới 8 triệu")
    selected = cards(response)
    assert len(selected) == 5 and [p["Rank"] for p in selected] == [1, 2, 3, 4, 5]
    assert all(Decimal(p["Price"]) <= 8_000_000 for p in selected)
    fifth = s.ask(svc, "Máy thứ năm pin bao nhiêu?")
    assert cards(fifth)[0]["ProductId"] == selected[4]["ProductId"] and "mAh" in fifth.AiMessages[0].Content


def test_an_explicit_request_for_five_is_filled_when_the_model_only_selects_three(store):
    s = store
    svc = s.service(FiveProductsModel(s.counters, count=3))
    question = "Tư vấn 5 laptop dưới 20 triệu"
    response = s.ask(svc, question)
    assert len(cards(response)) == 5
    assert len({p["ProductId"] for p in cards(response)}) == 5
    assert all(Decimal(p["Price"]) <= 20_000_000 for p in cards(response))
    assert s.question(question)["AiAnswerSource"] == "backend"


@pytest.mark.parametrize("question,cap", [("Tư vấn 2 điện thoại dưới 8 triệu", 2),
                                         ("Tư vấn 5 điện thoại dưới 8 triệu", 3)])
def test_lower_requested_or_configured_caps_apply_to_text_cards_and_references(store, question, cap):
    s = store
    svc = s.service(FiveProductsModel(s.counters))
    if cap == 3:
        svc.settings = replace(svc.settings, max_products=3)
    reply = s.ask(svc, question)
    assert len(cards(reply)) == cap
    shown = [p["ProductName"] for p in cards(reply)]
    assert all(name in reply.AiMessages[0].Content for name in shown)
    assert reply.AiMessages[0].Content.count("**") == cap * 2
    unresolved = analyze(f"Máy thứ {cap + 1} pin bao nhiêu?", VOCAB,
                         ConversationState((PastTurn({}, "recommend", tuple(
                             {"Rank": p["Rank"], "ProductId": p["ProductId"]} for p in cards(reply))),)))
    assert unresolved.clarification


def test_clarification_is_conversational_and_remembers_the_requested_five(store):
    s = store
    model = FiveProductsModel(s.counters)
    svc = s.service(model)
    first = s.ask(svc, "Hãy đề xuất tối đa 5 sản phẩm cho tôi")
    text = first.AiMessages[0].Content
    assert "tư vấn" in text and "ngân sách" in text and "gợi ý" not in text
    assert not cards(first) and not model.calls
    second = s.ask(svc, "Laptop dưới 20 triệu")
    assert len(cards(second)) == 5
    assert s.question("Laptop dưới 20 triệu")["AiIntent"]["Slots"]["RequestedCount"] == 5


def test_more_five_products_keeps_the_criteria_without_repeating_the_previous_five(store):
    s = store
    svc = s.service(FiveProductsModel(s.counters))
    first = cards(s.ask(svc, "Tư vấn 5 điện thoại dưới 8 triệu"))
    second = cards(s.ask(svc, "Tư vấn thêm 5 mẫu khác"))
    expected_remaining = sum(price <= 8_000_000 for _, _, price, _ in PHONES) - len(first)
    assert len(second) == min(5, expected_remaining)
    assert not {p["ProductId"] for p in first} & {p["ProductId"] for p in second}
    assert all(Decimal(p["Price"]) <= 8_000_000 for p in second)


def test_fewer_than_five_matching_products_are_stated_without_relaxing_the_criteria(store):
    s = store
    svc = s.service(FiveProductsModel(s.counters))
    reply = s.ask(svc, "Tư vấn 5 laptop ASUS dưới 20 triệu")
    assert len(cards(reply)) == 2
    assert all("ASUS" in p["ProductName"] and Decimal(p["Price"]) <= 20_000_000 for p in cards(reply))
    assert "chỉ tìm được 2 mẫu" in reply.AiMessages[0].Content


def test_warranty_answer_includes_the_fourth_and_fifth_products(store):
    from tests.test_ai_policy_explain import TurnModel, provider_down

    s = store
    svc = s.service(FiveProductsModel(s.counters))
    selected = cards(s.ask(svc, "Tư vấn 5 điện thoại dưới 8 triệu"))
    svc.model = TurnModel(s.counters, provider_down)
    reply = s.ask(svc, "Bảo hành năm sản phẩm trên như thế nào?")
    assert all(p["ProductName"] in reply.AiMessages[0].Content for p in selected)
    assert "5. " + selected[4]["ProductName"] in reply.AiMessages[0].Content


@pytest.mark.parametrize("phrase,indices", [("Máy thứ tư", [3]), ("Máy thứ 5", [4]),
                                            ("Máy thứ tư và thứ năm", [3, 4]), ("Bốn máy đầu", [0, 1, 2, 3]),
                                            ("Năm sản phẩm trên", [0, 1, 2, 3, 4])])
def test_fourth_and_fifth_references_resolve_in_order(phrase, indices):
    refs = (*LIST, {"Rank": 4, "ProductId": "p4", "ProductName": "Phone 4"},
            {"Rank": 5, "ProductId": "p5", "ProductName": "Phone 5"})
    state = ConversationState((PastTurn({}, "recommend", refs),))
    result = analyze(phrase + " pin bao nhiêu?", VOCAB, state)
    assert not result.clarification
    assert [ref["ProductId"] for ref in result.references] == [refs[i]["ProductId"] for i in indices]


def test_five_product_detail_batch_is_available_within_the_tool_payload_budget(store):
    s = store
    with Session(s.engine) as db:
        tools = AiTools(db, clock=lambda: NOW)
        context = GroundingContext("So sánh các sản phẩm")
        ids = [uuid.UUID(pid) for pid in list(s.products.values())[:5]]
        result = tools.get_product(GetProductArguments(product_ids=ids), context)
        assert len(result["Products"]) == 5
        assert len(json.dumps(result, ensure_ascii=False)) <= 14000
