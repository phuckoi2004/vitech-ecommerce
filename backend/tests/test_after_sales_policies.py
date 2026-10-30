"""Public policies and AI replies use the active exchange/warranty workflows; no shared database/provider."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.content import router
from app.services.after_sales_policy import store_policies
from app.services.ai_policy import return_lines, warranty_message_issue
from app.services.returns import ReturnPolicy
from tests.test_ai_advisor import cards, store  # noqa: F401
from tests.test_ai_policy_explain import TurnModel, answer, provider_down


@pytest.mark.parametrize("days", [None, "15"])
def test_public_policies_use_the_same_configured_window_as_chat_without_login(monkeypatch, days):
    if days is None:
        monkeypatch.delenv("RETURN_WINDOW_DAYS", raising=False)
    else:
        monkeypatch.setenv("RETURN_WINDOW_DAYS", days)
    api = FastAPI()
    api.include_router(router)
    with TestClient(api) as client:
        response = client.get("/store-policies")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    payload = response.json()
    expected_days = int(days or 7)
    assert payload["ReturnWindowDays"] == expected_days
    assert any(f"trong {expected_days} ngày" in line for line in payload["Returns"])
    assert any(f"trong {expected_days} ngày" in line for line in return_lines("Đổi trả bao nhiêu ngày?"))
    assert any("chưa hỗ trợ yêu cầu trả hàng hoàn tiền mới" in line for line in payload["Returns"])
    assert any("chưa hỗ trợ đổi máy trong phiếu bảo hành" in line for line in payload["Warranty"])
    assert not any("chuyển trung tâm" in line or "ảnh/video" in line for line in payload["Warranty"])
    assert any("phí gửi/nhận" in line and "nhân viên xác nhận" in line for line in payload["Warranty"])


def test_unconfigured_policy_does_not_publish_a_guessed_window():
    payload = store_policies(ReturnPolicy())
    assert payload["ReturnWindowDays"] is None
    assert any("thời hạn ghi ở trang tạo yêu cầu" in line for line in payload["Returns"])
    assert not any("7 ngày" in line for line in payload["Returns"])


@pytest.mark.parametrize("claim", [
    "VieTech bảo hành 1 đổi 1.",
    "Bạn sẽ được đổi máy mới khi bảo hành.",
    "VieTech sẽ thay máy mới trong thời gian bảo hành.",
    "Bảo hành miễn phí cho mọi trường hợp.",
    "Bảo hành xong trong 7 ngày.",
    "Máy được bảo hành mọi lỗi.",
])
def test_provider_warranty_promises_are_replaced_for_the_actual_shown_product(store, claim):
    shop = store
    service = shop.service(TurnModel(shop.counters, lambda _: answer({"intent": "policy", "message": claim})))
    shown = cards(shop.ask(service, "Tư vấn điện thoại dưới 8 triệu."))
    question = "Thủ tục bảo hành máy thứ hai như thế nào?"
    response = shop.ask(service, question)
    text = response.AiMessages[0].Content
    assert text != claim
    assert shown[1]["ProductName"] in text
    assert "chưa hỗ trợ đổi máy trong phiếu bảo hành" in text
    assert "phí gửi/nhận bảo hành cần được nhân viên xác nhận" in text
    assert shop.question(question)["AiAnswerSource"] == "backend"
    assert shop.question(question)["AiGroundingIssues"]


def test_denial_of_a_paused_replacement_is_allowed():
    assert warranty_message_issue("Hiện chưa hỗ trợ đổi máy trong phiếu bảo hành.") is None


@pytest.mark.parametrize("respond", [provider_down, lambda _: answer({
    "intent": "policy", "message": "Laptop VieTech được bảo hành 12 tháng miễn phí."})])
def test_a_generic_laptop_duration_question_asks_for_the_model_instead_of_guessing(store, respond):
    shop = store
    question = "Tôi mua laptop tại VIETECH thì được bảo hành bao lâu?"
    response = shop.ask(shop.service(TurnModel(shop.counters, respond)), question)
    text = response.AiMessages[0].Content
    assert response.Status == "Completed" and not cards(response)
    assert "tên hoặc mã mẫu sản phẩm" in text
    assert "tính từ ngày giao hàng thành công" in text
    assert "12 tháng" not in text and "24 tháng" not in text
    assert shop.question(question)["AiIntent"]["Intent"] == "policy_inquiry"


def test_laptop_warranty_does_not_quote_the_previous_phone_list(store):
    shop = store
    service = shop.service(TurnModel(shop.counters, provider_down))
    phones = cards(shop.ask(service, "Tư vấn điện thoại dưới 8 triệu."))
    response = shop.ask(service, "Tôi mua laptop tại VIETECH thì được bảo hành bao lâu?")
    text = response.AiMessages[0].Content
    assert "tên hoặc mã mẫu sản phẩm" in text
    assert all(phone["ProductName"] not in text for phone in phones)


@pytest.mark.parametrize("question,expected", [
    ("Bảo hành có mất phí gửi máy không?", "phí gửi/nhận bảo hành"),
    ("Bảo hành mất bao nhiêu ngày?", "Thời gian xử lý"),
    ("Laptop rơi vỡ có được bảo hành không?", "nhân viên kiểm tra theo điều kiện"),
])
def test_unconfirmed_terms_are_explained_without_inventing_fees_or_exclusions(store, question, expected):
    shop = store
    text = shop.ask(shop.service(TurnModel(shop.counters, provider_down)), question).AiMessages[0].Content
    assert expected in text
    assert "miễn phí" not in text and "trong 7 ngày" not in text
