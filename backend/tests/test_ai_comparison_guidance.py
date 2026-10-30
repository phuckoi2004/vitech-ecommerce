"""Questions about comparison accuracy must not select or count products."""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import Message
from app.schemas.ai_chat import AiMessageCreate
from app.services.ai_intent import CategoryInfo, ConversationState, PastTurn, Vocabulary, analyze
from tests.test_ai_comparison import table
from tests.test_ai_grounded import ask, grounded_shop  # noqa: F401


QUESTION = "Nếu hai sản phẩm thiếu thông số pin hoặc GPU, bạn có thể so sánh chính xác được không?"
VOCAB = Vocabulary((CategoryInfo("laptop", "Laptop", "laptop"),))


def state_with_products(count):
    refs = tuple({"Rank": index, "ProductId": str(uuid.UUID(int=index)), "ProductName": f"Laptop {index}"}
                 for index in range(1, count + 1))
    slots = {"CategoryId": "laptop", "MaxBudget": 25000000, "MinRamGb": 16,
             "BrandIds": ["asus", "lenovo"], "Needs": ["programming"], "RequestedCount": 3}
    return ConversationState((PastTurn(slots, "compare", refs),))


@pytest.mark.parametrize("count", [0, 2, 3, 5])
def test_a_hypothetical_product_count_does_not_select_from_the_previous_list(count):
    state = state_with_products(count)
    intent = analyze(QUESTION, VOCAB, state)
    assert intent.intent == "comparison_guidance"
    assert not intent.references and not intent.clarification
    assert intent.requested_count is None
    assert intent.to_metadata()["Slots"] == state.latest().slots


@pytest.mark.parametrize("question", [
    QUESTION,
    "Nếu thiếu pin, bạn so sánh thế nào?",
    "Thiếu GPU thì có so sánh được không?",
    "Khi chưa rõ CPU hoặc RAM thì bạn có thể so sánh chính xác không?",
    "Nếu 4 laptop chưa có thông số màn hình thì có thể so sánh chính xác không?",
])
def test_guidance_questions_are_answered_without_requiring_a_product_list(question):
    intent = analyze(question, VOCAB)
    assert intent.intent == "comparison_guidance"
    assert not intent.references and not intent.clarification


@pytest.mark.parametrize("question", [
    "So sánh hai sản phẩm trên về pin và GPU.",
    "Hãy chọn 3 laptop dưới 25 triệu rồi so sánh CPU, RAM, SSD, màn hình và giá.",
    "So sánh hai mẫu trên, bỏ qua GPU nếu thiếu thông số.",
    "Hãy so sánh chính xác hai mẫu trên, bỏ qua pin nếu thiếu thông số.",
])
def test_requests_to_build_a_table_still_use_the_product_comparison_flow(question):
    assert analyze(question, VOCAB, state_with_products(3)).intent == "product_comparison"


@pytest.mark.parametrize("with_previous_products", [False, True])
def test_the_exact_question_gets_a_direct_answer_without_cards_or_a_table(grounded_shop, with_previous_products):
    shop = grounded_shop
    service, model = shop.service([])
    if with_previous_products:
        selected = ask(shop, service, "Hãy chọn 3 laptop dưới 25 triệu rồi so sánh CPU, RAM, SSD, màn hình và giá.")
        ids = [p["ProductId"] for p in table(selected)["Products"]]
    response = ask(shop, service, QUESTION)
    assert response.Status == "Completed" and len(response.AiMessages) == 1
    reply = response.AiMessages[0]
    assert not (reply.Metadata or {}).get("Comparison")
    assert "Chưa rõ" in reply.Content and "không tự đoán" in reply.Content
    assert "2 hoặc 3 mẫu" not in reply.Content and "Mình xác định được" not in reply.Content
    assert model.calls == []
    if with_previous_products:
        resumed, _ = shop.service([])
        again = ask(shop, resumed, "So sánh 3 mẫu trên")
        assert [p["ProductId"] for p in table(again)["Products"]] == ids


def test_a_guidance_reply_replays_and_keeps_the_saved_shopping_constraints(grounded_shop):
    shop = grounded_shop
    service, model = shop.service([])
    original = ask(shop, service, "Chọn 3 laptop dưới 25 triệu RAM từ 16GB rồi so sánh CPU, RAM và giá.")
    data = AiMessageCreate(ClientRequestId=uuid.uuid4(), Content=QUESTION)
    answer = service.ask(shop.actor, shop.cid, data)
    replay = service.ask(shop.actor, shop.cid, data)
    recovery = service.get_status(shop.actor, shop.cid, data.ClientRequestId)
    assert answer.AiMessages[0].MessageId == replay.AiMessages[0].MessageId == recovery.AiMessages[0].MessageId
    with Session(shop.engine) as db:
        old = db.get(Message, original.CustomerMessage.MessageId).Metadata["AiIntent"]["Slots"]
        current = db.get(Message, answer.CustomerMessage.MessageId).Metadata["AiIntent"]["Slots"]
        assert current == old
    assert model.calls == []
