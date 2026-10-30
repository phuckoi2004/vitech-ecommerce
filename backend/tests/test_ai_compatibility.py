"""Existing chat/catalog/pricing/history on isolated SQLite; fake Gemini cannot change rule results."""

import copy
import uuid
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import Brand, Category, Message, Product, ProductVariant
from app.schemas.ai_chat import AiMessageCancel, AiMessageCreate
from app.schemas.chat import MessageResponse
from app.services.chat import ChatService
from app.services.exceptions import AiUnavailableError, ConflictError
from tests.test_ai_grounded import ask, call, finish, grounded_shop  # noqa: F401
from tests.test_compatibility import mode, port
from app.services.ai_intent import ConversationState
from app.services.compatibility_intent import compatibility_question, video_request


@pytest.fixture
def compatibility_shop(grounded_shop):
    shop = grounded_shop
    with Session(shop.engine) as db:
        for name, title in [("asus-zen", "ASUS Zenbook UX3405"), ("lenovo-idea", "Lenovo IdeaPad Slim 3")]:
            product = db.get(Product, uuid.UUID(shop.products[name]))
            product.Name = title
            product.Specifications = {**product.Specifications, "VideoOutputs": [port()], "VideoOutputsComplete": True}
        monitors = Category(Name="Màn hình máy tính", Slug="man-hinh")
        lg = Brand(Name="LG", Slug="lg")
        db.add_all([monitors, lg]); db.flush()
        for slug, title in [("lg-27", "LG 27GR93U"), ("lg-32", "LG 32GR93U")]:
            product = Product(Name=title, Slug=slug, BrandId=lg.BrandId, CategoryId=monitors.CategoryId, Status="Active",
                WarrantyMonths=24, Specifications={"VideoInputs": [port(Version="2.1")], "VideoInputsComplete": True,
                                                   "Độ phân giải màn hình": "3840x2160", "Tần số quét": "144Hz"})
            db.add(product); db.flush()
            variant = ProductVariant(ProductId=product.ProductId, Sku=slug, VariantName="Tiêu chuẩn", Price=8000000,
                                      CostPrice=4000000, StockQuantity=3)
            db.add(variant); db.flush()
            shop.products[slug], shop.variants[slug] = str(product.ProductId), str(variant.ProductVariantId)
        db.commit()
    return shop


def response(*ids, message=None):
    return {"intent": "compatibility", "compatibility_explanation_ids": list(ids), **({"message": message} if message else {})}


def check(shop, question="Laptop ASUS Zenbook UX3405 có kết nối được với màn hình LG 27GR93U không?", steps=None):
    service, model = shop.service(steps if steps is not None else [response("connection", "cable")])
    return ask(shop, service, question), service, model


def snapshot(result):
    return result.AiMessages[0].Metadata["Compatibility"]


def show(shop, names, question):
    service, _ = shop.service([[call("get_product", product_ids=[shop.products[name] for name in names])],
                               finish("recommend", *(shop.products[name] for name in names))])
    result = ask(shop, service, question)
    assert len(result.AiMessages) == len(names) + 1
    shop.now.value += timedelta(seconds=1)
    return result


def test_named_products_run_verified_rules_and_only_one_final_gemini_round(compatibility_shop):
    shop = compatibility_shop
    result, _, model = check(shop)
    data = snapshot(result)
    assert data["Status"] == "compatible"
    assert [p["ProductId"] for p in data["Products"]] == [shop.products["asus-zen"], shop.products["lg-27"]]
    assert [p["ProductVariantId"] for p in data["Products"]] == [shop.variants["asus-zen"], shop.variants["lg-27"]]
    assert data["ExplanationSource"] == "gemini"
    assert len(model.calls) == 1
    assert [t["function"]["name"] for t in model.calls[0][1]["tools"]] == ["present_answer"]
    assert "KẾT QUẢ KIỂM TRA TƯƠNG THÍCH ĐÃ XÁC MINH" in model.calls[0][0][0]["content"]


def test_laptop_macbook_category_prefix_preserves_the_explicit_model(compatibility_shop):
    shop = compatibility_shop
    with Session(shop.engine) as db:
        db.get(Product, uuid.UUID(shop.products["asus-zen"])).Name = "Apple MacBook Air M3"
        db.commit()
    result, _, _ = check(shop, "Laptop MacBook Air M3 có kết nối được với màn hình LG 27GR93U không?")
    assert snapshot(result)["Products"][0]["ProductId"] == shop.products["asus-zen"]


@pytest.mark.parametrize("question", [
    "Điện thoại iPhone có tương thích với bộ sạc này không?",
    "Laptop này có kết nối được màn hình này qua hub USB-C không?",
    "Laptop ASUS và laptop Lenovo có kết nối được màn hình LG không?",
    "Laptop này có kết nối được hai màn hình không?",
])
def test_unsupported_new_devices_do_not_reuse_a_previous_pair(compatibility_shop, question):
    shop = compatibility_shop
    initial, _, _ = check(shop)
    assert snapshot(initial)["Status"] == "compatible"
    shop.now.value += timedelta(seconds=1)
    result, _, model = check(shop, question, steps=[])
    assert model.calls == []
    assert "Compatibility" not in (result.AiMessages[0].Metadata or {})
    assert "một laptop" in result.AiMessages[0].Content


@pytest.mark.parametrize("question", [
    "Laptop ASUS này có kết nối được màn hình LG này không?",
    "Hai thiết bị này có tương thích với nhau không?",
    "Muốn kết nối laptop này với màn hình kia thì cần cáp gì?",
    "Laptop vừa giới thiệu có xuất hình ra màn hình 4K không?",
    "Laptop này có kết nối được với màn hình 144Hz này không?",
    "Cắm màn hình 4K 144Hz vào laptop này có chạy đúng 144Hz không?",
])
def test_contextual_questions_use_the_shown_pair(compatibility_shop, question):
    shop = compatibility_shop
    show(shop, ["asus-zen"], "Giới thiệu 1 laptop ASUS mới nhất")
    show(shop, ["lg-27"], "Giới thiệu 1 màn hình LG mới nhất")
    result, _, _ = check(shop, question)
    assert [p["ProductVariantId"] for p in snapshot(result)["Products"]] == [shop.variants["asus-zen"], shop.variants["lg-27"]]


def test_smart_compare_then_typed_ordinal_and_followup_keep_devices_without_rewriting_comparison(compatibility_shop):
    shop = compatibility_shop
    compare_service, compare_model = shop.service([])
    compared = ask(shop, compare_service, "So sánh ASUS Zenbook UX3405 và Lenovo IdeaPad Slim 3")
    old_table = copy.deepcopy(compared.AiMessages[0].Metadata["Comparison"])
    assert compare_model.calls == []
    shop.now.value += timedelta(seconds=1)
    show(shop, ["lg-27"], "Giới thiệu 1 màn hình LG mới nhất")
    checked, service, _ = check(shop, "Laptop thứ hai vừa so sánh có kết nối được màn hình LG này không?",
                                steps=[response("connection"), response("connection", "signal_mode", "missing")])
    assert snapshot(checked)["Products"][0]["ProductId"] == shop.products["lenovo-idea"]
    shop.now.value += timedelta(seconds=1)
    followup = ask(shop, service, "Nếu muốn xuất 4K 144Hz thì sao?")
    data = snapshot(followup)
    assert [p["ProductId"] for p in data["Products"]] == [shop.products["lenovo-idea"], shop.products["lg-27"]]
    assert data["Request"]["Width"] == 3840 and data["Request"]["RefreshHz"] == 144
    assert data["Status"] == "unknown"
    assert next(c for c in data["Criteria"] if c["Id"] == "connection")["Status"] == "compatible"
    with Session(shop.engine) as db:
        assert db.get(Message, compared.AiMessages[0].MessageId).Metadata["Comparison"] == old_table


def test_monitor_and_laptop_ordinals_resolve_from_separate_lists(compatibility_shop):
    shop = compatibility_shop
    show(shop, ["asus-zen", "lenovo-idea"], "Giới thiệu 2 laptop mới nhất")
    show(shop, ["lg-27", "lg-32"], "Giới thiệu 2 màn hình mới nhất")
    result, _, _ = check(shop, "Màn hình thứ hai có dùng được với laptop đầu tiên không?")
    assert [p["ProductId"] for p in snapshot(result)["Products"]] == [shop.products["asus-zen"], shop.products["lg-32"]]


@pytest.mark.parametrize("question", ["Laptop này có kết nối được màn hình LG này không?",
                                     "Hai thiết bị này có tương thích không?",
                                     "Laptop của tôi có kết nối được màn hình 144Hz này không?"])
def test_missing_or_ambiguous_devices_are_asked_without_a_gemini_call(compatibility_shop, question):
    shop = compatibility_shop
    service, model = shop.service([])
    result = ask(shop, service, question)
    assert "Compatibility" not in (result.AiMessages[0].Metadata or {}) and model.calls == []
    assert "?" in result.AiMessages[0].Content or "nhé" in result.AiMessages[0].Content


def test_missing_device_reply_completes_the_pair_after_service_reload(compatibility_shop):
    shop = compatibility_shop
    first, model = shop.service([])
    result = ask(shop, first, "Laptop ASUS Zenbook UX3405 có kết nối được với màn hình LG không?")
    assert "nhiều màn hình" in result.AiMessages[0].Content and model.calls == []
    shop.now.value += timedelta(seconds=1)
    completed, _, _ = check(shop, "LG 27GR93U")
    assert snapshot(completed)["Products"][1]["ProductId"] == shop.products["lg-27"]


def test_empty_pending_subjects_can_be_filled_across_two_reloaded_turns(compatibility_shop):
    shop = compatibility_shop
    first, _ = shop.service([])
    ask(shop, first, "Hai thiết bị này có tương thích không?")
    shop.now.value += timedelta(seconds=1)
    second, _ = shop.service([])
    clarified = ask(shop, second, "ASUS Zenbook UX3405")
    assert "màn hình" in clarified.AiMessages[0].Content
    shop.now.value += timedelta(seconds=1)
    result, _, _ = check(shop, "LG 27GR93U")
    assert snapshot(result)["Status"] == "compatible"


@pytest.mark.parametrize("change", ["missing", "Draft", "Discontinued", "deleted", "hidden_variant"])
def test_not_found_hidden_or_deleted_device_never_yields_a_stale_result(compatibility_shop, change):
    shop = compatibility_shop
    if change == "missing":
        question = "Laptop ASUS Zenbook UX3405 có kết nối được màn hình LG XYZ999 không?"
    else:
        show(shop, ["asus-zen"], "Giới thiệu 1 laptop ASUS mới nhất")
        show(shop, ["lg-27"], "Giới thiệu 1 màn hình LG mới nhất")
        with Session(shop.engine) as db:
            product = db.get(Product, uuid.UUID(shop.products["lg-27"]))
            if change == "deleted":
                product.IsDeleted = True
            elif change == "hidden_variant":
                db.get(ProductVariant, uuid.UUID(shop.variants["lg-27"])).IsActive = False
            else:
                product.Status = change
            db.commit()
        question = "Laptop này có kết nối được màn hình này không?"
    result, _, model = check(shop, question, steps=[])
    assert model.calls == [] and "Compatibility" not in (result.AiMessages[0].Metadata or {})


def test_single_usb_c_capability_does_not_mistake_hdmi_for_usb_c_video(compatibility_shop):
    shop = compatibility_shop
    show(shop, ["asus-zen"], "Giới thiệu 1 laptop ASUS mới nhất")
    with Session(shop.engine) as db:
        product = db.get(Product, uuid.UUID(shop.products["asus-zen"]))
        product.Specifications = {"VideoOutputs": [port(), port("USB-C", Video=None)], "VideoOutputsComplete": True}
        db.commit()
    result, _, _ = check(shop, "Cổng USB-C của laptop này có hỗ trợ xuất hình không?")
    assert snapshot(result)["CheckType"] == "laptop_video_output"
    assert snapshot(result)["Status"] == "unknown"
    assert snapshot(result)["Request"]["SourceConnector"] == "usb_c"


def test_source_only_advanced_mode_question_keeps_output_and_mode_results_separate(compatibility_shop):
    result, _, _ = check(compatibility_shop, "Laptop ASUS Zenbook UX3405 có xuất hình qua HDMI 4K 144Hz không?")
    data = snapshot(result)
    assert data["CheckType"] == "laptop_video_output" and data["Status"] == "unknown"
    assert next(c for c in data["Criteria"] if c["Id"] == "connection")["Status"] == "compatible"
    assert next(c for c in data["Criteria"] if c["Id"] == "signal_mode")["Status"] == "unknown"


def test_missing_port_specs_yield_unknown_instead_of_invented_ports(compatibility_shop):
    shop = compatibility_shop
    with Session(shop.engine) as db:
        for name in ["asus-zen", "lg-27"]:
            db.get(Product, uuid.UUID(shop.products[name])).Specifications = None
        db.commit()
    result, _, _ = check(shop)
    data = snapshot(result)
    assert data["Status"] == "unknown" and data["Missing"]
    assert all(product["Facts"] == [] for product in data["Products"])


@pytest.mark.parametrize("malicious", [
    {"intent": "compare", "products": [{"product_id": str(uuid.uuid4())}, {"product_id": str(uuid.uuid4())}]},
    response("made-up-result", message="Chắc chắn hỗ trợ 4K 144Hz và tặng bộ chuyển HDMI 3.0."),
    response("connection", message="Hai máy đều có HDMI 9.9, đã thử nghiệm 4K 144Hz mượt."),
])
def test_gemini_cannot_change_status_facts_or_introduce_unsupported_explanations(compatibility_shop, malicious):
    result, _, _ = check(compatibility_shop, steps=[malicious])
    data = snapshot(result)
    assert data["Status"] == "compatible"
    assert "9.9" not in result.model_dump_json() and "tặng bộ" not in result.model_dump_json()
    assert "đã thử nghiệm" not in result.model_dump_json()


@pytest.mark.parametrize("code", ["ai_unavailable", "ai_quota_exceeded", "ai_invalid_output"])
def test_provider_failure_preserves_rules_history_replay_and_cooldown(compatibility_shop, code):
    shop = compatibility_shop
    def fail(_):
        raise AiUnavailableError("Provider failure", code=code, retry_after_seconds=30 if code == "ai_quota_exceeded" else None)
    service, model = shop.service([fail, fail])
    data = AiMessageCreate(ClientRequestId=uuid.uuid4(), Content="Laptop ASUS Zenbook UX3405 có kết nối được màn hình LG 27GR93U không?")
    first = service.ask(shop.actor, shop.cid, data)
    result = snapshot(first)
    assert result["Status"] == "compatible" and result["AnalysisStatus"] == "fallback"
    calls = len(model.calls)
    assert snapshot(service.ask(shop.actor, shop.cid, data)) == result
    assert snapshot(service.get_status(shop.actor, shop.cid, data.ClientRequestId)) == result
    assert len(model.calls) == calls
    with Session(shop.engine) as db:
        history = ChatService(db).get_conversation(shop.actor, shop.cid)
        saved = next(m for m in history.Messages if m.MessageId == first.AiMessages[0].MessageId)
        assert saved.Metadata["Compatibility"] == result
    if code == "ai_quota_exceeded":
        with pytest.raises(AiUnavailableError) as error:
            ask(shop, service, "Xin chào")
        assert error.value.code == "ai_quota_exceeded"


def test_cancel_during_gemini_fences_off_compatibility_snapshot(compatibility_shop):
    shop = compatibility_shop
    data = AiMessageCreate(ClientRequestId=uuid.uuid4(), Content="Laptop ASUS Zenbook UX3405 có kết nối được màn hình LG 27GR93U không?")
    other, _ = shop.service([])
    def cancel(_):
        other.cancel(shop.actor, shop.cid, data.ClientRequestId, AiMessageCancel(Content=data.Content))
        raise AiUnavailableError("Timeout")
    service, _ = shop.service([cancel])
    with pytest.raises(ConflictError):
        service.ask(shop.actor, shop.cid, data)
    assert service.get_status(shop.actor, shop.cid, data.ClientRequestId).Status == "Cancelled"


def test_specs_are_rechecked_after_model_io(compatibility_shop):
    shop = compatibility_shop
    def changed(_):
        with Session(shop.engine) as db:
            db.get(Product, uuid.UUID(shop.products["asus-zen"])).Specifications = None
            db.commit()
        return response("connection")
    result, _, _ = check(shop, steps=[changed])
    assert snapshot(result)["Status"] == "unknown" and "Chưa thể xác nhận" in snapshot(result)["Explanation"]


def test_normal_chat_and_smart_compare_are_still_separate(compatibility_shop):
    shop = compatibility_shop
    service, model = shop.service([finish("chat")])
    result = ask(shop, service, "Xin chào")
    assert "Compatibility" not in (result.AiMessages[0].Metadata or {})
    shop.now.value += timedelta(seconds=1)
    result = ask(shop, service, "So sánh ASUS Zenbook UX3405 và Lenovo IdeaPad Slim 3 máy nào tốt hơn?")
    assert result.AiMessages[0].Metadata.get("Comparison") and not result.AiMessages[0].Metadata.get("Compatibility")
    assert len(model.calls) == 1


def test_corrupt_compatibility_metadata_cannot_break_history_or_leak_private_slots(compatibility_shop):
    result, _, _ = check(compatibility_shop)
    message = result.AiMessages[0].model_dump()
    message["Metadata"] = {"Compatibility": {"Version": 1}, "AiLeaseToken": "private", "Comparison": None}
    assert MessageResponse.model_validate(message).Metadata is None


def test_gemini_cannot_omit_uncertainty_by_selecting_only_the_positive_connection_sentence(compatibility_shop):
    result, _, _ = check(compatibility_shop,
        "Laptop ASUS Zenbook UX3405 có kết nối được màn hình LG 27GR93U ở 4K 144Hz không?", steps=[response("connection")])
    data = snapshot(result)
    assert data["Status"] == "unknown"
    assert "Chưa thể xác nhận" in data["Explanation"] and "Cần kiểm tra thêm" in data["Explanation"]


def test_selected_out_of_stock_sku_is_kept_and_uses_only_its_video_specs(compatibility_shop):
    shop = compatibility_shop
    show(shop, ["asus-zen"], "Giới thiệu 1 laptop ASUS mới nhất")
    show(shop, ["lg-27"], "Giới thiệu 1 màn hình LG mới nhất")
    with Session(shop.engine) as db:
        old = db.get(ProductVariant, uuid.UUID(shop.variants["asus-zen"]))
        old.StockQuantity = 0
        second = ProductVariant(ProductId=old.ProductId, Sku="different-ports", VariantName="8GB / 256GB", Price=14000000,
                                CostPrice=7000000, StockQuantity=5)
        db.add(second); db.flush()
        product = db.get(Product, old.ProductId)
        product.Specifications = {"VideoByVariant": {
            str(old.ProductVariantId): {"VideoOutputs": [], "VideoOutputsComplete": True},
            str(second.ProductVariantId): {"VideoOutputs": [port()], "VideoOutputsComplete": True}}}
        db.commit()
    result, _, _ = check(shop, "Laptop này có kết nối được màn hình này không?")
    data = snapshot(result)
    assert data["Products"][0]["ProductVariantId"] == shop.variants["asus-zen"]
    assert data["Products"][0]["InStock"] is False and data["Status"] == "incompatible"


def test_variant_reply_after_reload_keeps_pending_pair(compatibility_shop):
    shop = compatibility_shop
    with Session(shop.engine) as db:
        db.add(ProductVariant(ProductId=uuid.UUID(shop.products["asus-zen"]), Sku="another-version", VariantName="8GB / 256GB",
                              Price=14000000, CostPrice=7000000, StockQuantity=5))
        db.commit()
    result, _, model = check(shop, steps=[])
    assert "phiên bản nào" in result.AiMessages[0].Content and model.calls == []
    shop.now.value += timedelta(seconds=1)
    completed, _, _ = check(shop, "Chọn bản 16GB / 512GB")
    assert snapshot(completed)["Products"][0]["ProductVariantId"] == shop.variants["asus-zen"]


def test_real_http_snapshot_replay_status_and_history_keep_comparison_metadata_separate(compatibility_shop):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.core.dependencies import get_current_actor
    from app.routers.chat import router
    from app.routers.dependencies import get_ai_chat_service, get_chat_service
    from app.routers.errors import service_error_handler
    from app.services.exceptions import ServiceError

    shop = compatibility_shop
    compare, _ = shop.service([])
    compared = ask(shop, compare, "So sánh ASUS Zenbook UX3405 và Lenovo IdeaPad Slim 3")
    shop.now.value += timedelta(seconds=1)
    service, model = shop.service([response("connection", "cable")])
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ServiceError, service_error_handler)
    app.dependency_overrides[get_current_actor] = lambda: shop.actor
    app.dependency_overrides[get_ai_chat_service] = lambda: service
    with Session(shop.engine) as db:
        app.dependency_overrides[get_chat_service] = lambda: ChatService(db)
        with TestClient(app) as client:
            path = f"/conversations/{shop.cid}"
            body = {"ClientRequestId": str(uuid.uuid4()), "Content": "Laptop Lenovo vừa so sánh có kết nối được với màn hình LG 27GR93U không?"}
            result = client.post(path + "/ai-messages", json=body)
            assert result.status_code == 200, result.text
            original = result.json()["AiMessages"][0]
            replay = client.post(path + "/ai-messages", json=body).json()["AiMessages"][0]
            recovered = client.get(path + "/ai-messages/" + body["ClientRequestId"]).json()["AiMessages"][0]
            history = client.get(path).json()["Messages"]
            restored = next(m for m in history if m["MessageId"] == original["MessageId"])
            old = next(m for m in history if m["MessageId"] == str(compared.AiMessages[0].MessageId))
            assert original["Metadata"] == replay["Metadata"] == recovered["Metadata"] == restored["Metadata"]
            assert old["Metadata"]["Comparison"] == compared.AiMessages[0].Metadata["Comparison"]
            assert "Compatibility" not in old["Metadata"] and "Comparison" not in original["Metadata"]
            assert len(model.calls) == 1 and "CompatibilitySubjects" not in result.text and "AiLeaseToken" not in result.text


@pytest.mark.parametrize("question", ["Laptop ASUS và laptop Lenovo máy nào tốt hơn?",
    "So sánh hai laptop trên về khả năng xuất hình qua USB-C", "Tư vấn laptop mới có xuất hình 4K"])
def test_recommendations_and_comparisons_of_ports_are_not_compatibility_checks(question):
    assert compatibility_question(question, ConversationState()) is False


def test_compact_4k144hz_keeps_the_resolution_and_ambiguous_2k_is_not_silently_dropped():
    request = video_request("Xuất hình 4K144Hz")
    assert (request.Width, request.Height, request.RefreshHz) == (3840, 2160, 144)
    with pytest.raises(ValueError):
        video_request("Xuất hình 2K 144Hz")


# --- Review regressions -----------------------------------------------------------------------------------------

def saved_intent(shop, result):
    with Session(shop.engine) as db:
        return db.get(Message, result.CustomerMessage.MessageId).Metadata["AiIntent"]


@pytest.mark.parametrize("question", [
    "Laptop này có kết nối Wi-Fi 7 không?", "Laptop này có những cổng kết nối gì?",
    "Laptop này có kết nối Bluetooth với tai nghe được không?", "Laptop này có tương thích Windows 11 không?",
    "RAM 32GB có tương thích với laptop này không?", "Màn hình này có đạt 144Hz không?",
    "Màn hình này có những cổng kết nối gì?", "Laptop này có cổng kết nối HDMI không?",
])
def test_non_display_or_single_product_spec_questions_keep_the_existing_flow(question):
    assert compatibility_question(question, ConversationState()) is False


@pytest.mark.parametrize("question", [
    "Laptop này kết nối với màn hình qua HDMI được không?", "Màn hình LG kết nối với MacBook được không?",
    "Laptop này kết nối qua USB-C được không?", "Điện thoại có kết nối được màn hình không?",
    "Laptop này có tương thích với màn hình 4K không?",
])
def test_display_connection_questions_are_still_compatibility_checks(question):
    assert compatibility_question(question, ConversationState()) is True


@pytest.mark.parametrize("question,expected", [
    ("Laptop A có kết nối được màn hình B qua USB-C không?", "usb_c"),
    ("Kết nối laptop với màn hình bằng cáp HDMI được không?", "hdmi"),
    ("Laptop có kết nối màn hình qua cổng DP được không?", "displayport"),
    ("Laptop có kết nối màn hình qua Type-C không?", "usb_c"),
])
def test_a_named_laptop_connector_is_part_of_the_request_without_saying_xuat_hinh(question, expected):
    assert video_request(question).SourceConnector == expected


def test_new_question_does_not_inherit_a_hidden_connector_or_mode(compatibility_shop):
    shop = compatibility_shop
    first, _, _ = check(shop, "Laptop ASUS Zenbook UX3405 có kết nối được màn hình LG 27GR93U qua USB-C ở 4K 144Hz không?")
    data = snapshot(first)
    assert data["Request"]["SourceConnector"] == "usb_c" and data["Request"]["RefreshHz"] == 144
    # The complete output list has HDMI only: USB-C video is explicitly absent, not merely unknown.
    assert data["Status"] == "incompatible"
    shop.now.value += timedelta(seconds=1)
    second, _, _ = check(shop)
    again = snapshot(second)
    assert again["Request"] == {"Width": None, "Height": None, "RefreshHz": None, "SourceConnector": None,
                                "DirectOnly": False}
    assert again["Status"] == "compatible"


def test_follow_up_swapping_one_device_keeps_the_other_device_and_the_request(compatibility_shop):
    shop = compatibility_shop
    compare, _ = shop.service([])
    ask(shop, compare, "So sánh ASUS Zenbook UX3405 và Lenovo IdeaPad Slim 3")
    shop.now.value += timedelta(seconds=1)
    first, service, _ = check(shop, "Laptop thứ hai vừa so sánh có kết nối được màn hình LG 27GR93U ở 4K 144Hz không?",
                              steps=[response("connection"), response("connection")])
    assert snapshot(first)["Products"][0]["ProductId"] == shop.products["lenovo-idea"]
    shop.now.value += timedelta(seconds=1)
    swapped = snapshot(ask(shop, service, "Còn laptop thứ nhất thì sao?"))
    assert [p["ProductId"] for p in swapped["Products"]] == [shop.products["asus-zen"], shop.products["lg-27"]]
    assert swapped["Request"]["Width"] == 3840 and swapped["Request"]["RefreshHz"] == 144


def test_generic_ordinal_beside_a_named_monitor_uses_the_compared_list(compatibility_shop):
    shop = compatibility_shop
    compare, _ = shop.service([])
    ask(shop, compare, "So sánh ASUS Zenbook UX3405 và Lenovo IdeaPad Slim 3")
    for question in ["Máy thứ hai có kết nối được màn hình LG 27GR93U không?",
                     "Màn hình LG 27GR93U có dùng được với máy thứ hai không?"]:
        shop.now.value += timedelta(seconds=1)
        result, _, _ = check(shop, question)
        assert [p["ProductId"] for p in snapshot(result)["Products"]] == [shop.products["lenovo-idea"], shop.products["lg-27"]]


def test_new_shopping_requests_are_not_captured_by_a_previous_or_pending_check(compatibility_shop):
    shop = compatibility_shop
    check(shop)
    for question in ["Còn màn hình nào rẻ hơn không?", "Laptop nào dưới 20 triệu pin trâu?"]:
        shop.now.value += timedelta(seconds=1)
        service, _ = shop.service([finish("no_results")])
        result = ask(shop, service, question)
        assert saved_intent(shop, result)["Intent"] != "product_compatibility"
        assert "Compatibility" not in (result.AiMessages[0].Metadata or {})
    shop.now.value += timedelta(seconds=1)
    pending, _ = shop.service([])
    ask(shop, pending, "Laptop ASUS Zenbook UX3405 có kết nối được với màn hình LG không?")  # Asks which LG monitor.
    shop.now.value += timedelta(seconds=1)
    service, _ = shop.service([finish("no_results")])
    result = ask(shop, service, "Laptop nào dưới 20 triệu pin trâu?")
    assert saved_intent(shop, result)["Intent"] != "product_compatibility"


def test_answer_text_separates_basic_connection_from_the_requested_mode(compatibility_shop):
    result, _, _ = check(compatibility_shop, "Laptop ASUS Zenbook UX3405 có kết nối được màn hình LG 27GR93U ở 4K 144Hz không?",
                         steps=[response("connection")])
    content = result.AiMessages[0].Content
    assert "Kết nối cơ bản: Đáp ứng trong điều kiện đã nêu" in content and "chưa thể xác nhận" in content.lower()


def test_provider_fallback_with_many_spec_warnings_keeps_a_valid_snapshot(compatibility_shop):
    shop = compatibility_shop
    with Session(shop.engine) as db:
        product = db.get(Product, uuid.UUID(shop.products["asus-zen"]))
        # Eleven distinct conflicting entries (an input listed as an output): the advisor must stay renderable.
        product.Specifications = {f"Nhóm {i}": {"VideoOutputs": [port(Direction="input")]} for i in range(11)}
        db.commit()
    def fail(_):
        raise AiUnavailableError("Provider timeout")
    result, _, _ = check(shop, steps=[fail])
    data = snapshot(result)
    assert data["AnalysisStatus"] == "fallback" and data["Status"] == "unknown"
    assert len(data["Limitations"]) <= 12 and "tạm thời chưa hoàn tất" in data["Limitations"][-1]
    with Session(shop.engine) as db:
        history = ChatService(db).get_conversation(shop.actor, shop.cid)
        assert next(m for m in history.Messages if m.MessageId == result.AiMessages[0].MessageId).Metadata["Compatibility"]


def _after_check(pending=False):
    from app.services.ai_intent import PastTurn
    laptop = {"ProductId": str(uuid.uuid4()), "ProductName": "Laptop", "Kind": "laptop"}
    monitor = {"ProductId": str(uuid.uuid4()), "ProductName": "Màn hình", "Kind": "monitor"}
    slots = {"CompatibilitySubjects": [laptop] if pending else [laptop, monitor], "CompatibilityRequest": {},
             "PendingCompatibility": pending}
    return ConversationState((PastTurn(slots, "clarify" if pending else "compatibility", () if pending else (laptop, monitor)),))


@pytest.mark.parametrize("question,expected", [
    ("Còn laptop thứ nhất thì sao?", True), ("Vậy màn hình thứ hai thì sao?", True), ("Còn qua USB-C thì sao?", True),
    ("Nếu muốn xuất 4K 144Hz thì sao?", True), ("Vậy laptop này giá bao nhiêu?", False),
    ("Vậy laptop này pin bao lâu?", False), ("Còn màn hình này bảo hành mấy tháng?", False),
])
def test_follow_ups_after_a_check_continue_it_but_product_questions_do_not(question, expected):
    assert compatibility_question(question, _after_check()) is expected


def test_pending_version_reply_still_continues_and_a_which_question_with_criteria_does_not():
    assert compatibility_question("Bản RAM 16GB / 512GB", _after_check(pending=True)) is True
    assert compatibility_question("Laptop nào dưới 20 triệu xuất hình 4K được?", ConversationState(), new_request=True) is False


def test_which_laptop_question_explains_the_pairwise_scope_without_a_catalog_guess(compatibility_shop):
    shop = compatibility_shop
    service, model = shop.service([])
    result = ask(shop, service, "Laptop nào kết nối được màn hình LG 27GR93U?")
    assert model.calls == [] and "Compatibility" not in (result.AiMessages[0].Metadata or {})
    assert "từng cặp" in result.AiMessages[0].Content and "“nao”" not in result.AiMessages[0].Content


def test_clarification_quotes_the_name_as_the_customer_typed_it(compatibility_shop):
    shop = compatibility_shop
    service, model = shop.service([])
    result = ask(shop, service, "Laptop ASUS Zenbook UX3405 có kết nối được màn hình Samsung Odyssey Đen không?")
    assert model.calls == [] and "“Samsung Odyssey Đen”" in result.AiMessages[0].Content


def test_quota_cooldown_still_answers_compatibility_from_rules_but_refuses_other_questions(compatibility_shop):
    shop = compatibility_shop
    def quota(_):
        raise AiUnavailableError("Quota", code="ai_quota_exceeded", retry_after_seconds=60)
    service, model = shop.service([quota])
    first = snapshot(ask(shop, service, "Laptop ASUS Zenbook UX3405 có kết nối được màn hình LG 27GR93U không?"))
    assert first["AnalysisStatus"] == "fallback" and len(model.calls) == 1  # Starts the provider cooldown.
    shop.now.value += timedelta(seconds=1)
    during = snapshot(ask(shop, service, "Laptop Lenovo IdeaPad Slim 3 có kết nối được màn hình LG 32GR93U không?"))
    assert during["Status"] == "compatible" and during["AnalysisStatus"] == "fallback"
    assert during["ExplanationSource"] == "backend" and len(model.calls) == 1  # No model call during the cooldown.
    shop.now.value += timedelta(seconds=1)
    asked = ask(shop, service, "Laptop ASUS Zenbook UX3405 có kết nối được với màn hình LG không?")
    assert "nhiều màn hình" in asked.AiMessages[0].Content and len(model.calls) == 1
    with Session(shop.engine) as db:
        before = db.query(Message).count()
    for question in ["Xin chào", "Còn màn hình nào rẻ hơn không?"]:
        with pytest.raises(AiUnavailableError) as error:
            ask(shop, service, question)
        assert error.value.code == "ai_quota_exceeded" and error.value.retry_after_seconds
    with Session(shop.engine) as db:
        assert db.query(Message).count() == before  # Refused before being saved, as before this change.
    assert len(model.calls) == 1


@pytest.mark.parametrize("question", ["Xin chào", "Cảm ơn bạn", "Bạn là ai?"])
def test_small_talk_is_not_taken_as_the_pending_device_name(question):
    assert compatibility_question(question, _after_check(pending=True)) is False
