"""Customer wording through the existing answer boundary; no live database or provider."""

import uuid
import json

import pytest
from sqlalchemy.orm import Session

from app.models import Message, Product
from app.services.ai_comparison import _chip_generation_answer
from app.services.ai_customer_wording import customer_notes, customer_text
from app.core.search_text import fold
from app.services.ai_grounding import Facts, check_message
from tests.test_ai_comparison import show, table
from tests.test_ai_grounded import ask, call, finish, grounded_shop  # noqa: F401


@pytest.mark.parametrize("identifier", [
    "catalog", "CATALOG", "Specifications", "ProductVariants", "product_variants", "Products",
    "Categories", "Brands", "Messages", "Conversations", "CostPrice", "StockQuantity", "WarrantyMonths",
    "ProductVariantId", "ProductId", "VideoByVariant", "public.ProductVariants", "PaymentTransactions",
    "OrderStatusHistories", "ProductSerials", "ReturnRequests", "WishlistItems", "PurchaseReceipts",
])
def test_internal_identifiers_are_rejected_even_when_present_in_the_question_or_tool_facts(identifier):
    message = f"Thông tin được đọc từ `{identifier}`."
    _, issues = check_message(message, Facts(shared_texts=[message]))
    assert "lộ chi tiết nội bộ" in issues


def test_development_technologies_in_the_customers_needs_are_not_treated_as_table_names():
    message = "Máy dành cho nhu cầu lập trình backend với PostgreSQL."
    assert check_message(message, Facts(shared_texts=[message])) == (message, [])


@pytest.mark.parametrize("identifier", ["catalog", "Specifications", "ProductVariants"])
def test_an_internal_name_from_the_model_is_replaced_by_customer_facing_product_facts(grounded_shop, identifier):
    shop = grounded_shop
    decision = {**finish("product", shop.products["asus-zen"]),
                "message": f"Theo {identifier}, asus-zen có RAM 16 GB."}
    service, _ = shop.service([[call("get_product", product_id=shop.products["asus-zen"])], decision])
    response = ask(shop, service, "asus-zen có RAM bao nhiêu?")
    assert identifier not in response.AiMessages[0].Content
    assert "RAM: 16 GB" in response.AiMessages[0].Content
    with Session(shop.engine) as db:
        metadata = db.get(Message, response.CustomerMessage.MessageId).Metadata
        assert "lộ chi tiết nội bộ" in metadata["AiGroundingIssues"]


@pytest.mark.parametrize("question", [
    "So sánh hai laptop trên", "So sánh hai laptop trên để học lập trình",
    "So sánh hai laptop trên để chơi game", "So sánh pin hai laptop trên",
])
def test_ordinary_comparisons_do_not_append_generic_disclaimers(grounded_shop, question):
    shop = grounded_shop
    show(shop)
    service, _ = shop.service([])
    response = ask(shop, service, question)
    snapshot = table(response)
    assert snapshot["Caveats"] == []
    assert any("Chưa rõ" in row["Values"] for row in snapshot["Rows"])
    assert "Giá và tồn kho" not in response.AiMessages[0].Content


def test_a_specific_software_question_keeps_only_the_relevant_uncertainty(grounded_shop):
    shop = grounded_shop
    show(shop)
    service, _ = shop.service([])
    snapshot = table(ask(shop, service, "So sánh hai laptop trên để chạy Android Studio"))
    assert snapshot["Caveats"] == [
        "Chưa có kết quả chạy thử Android Studio trên các mẫu này để xác nhận mức đáp ứng bạn hỏi."]
    assert not any("pin" in line or "giá" in line.lower() for line in snapshot["Caveats"])


def test_missing_chip_generation_is_explained_without_an_internal_source_name():
    answer = _chip_generation_answer("Chip mẫu nào mới hơn?", [], [{}, {}])
    assert answer == "Chưa có đủ thông tin về thế hệ chip để xác định mẫu nào dùng chip mới hơn."


def test_a_description_without_specs_explains_the_specific_missing_information(grounded_shop):
    shop = grounded_shop
    with Session(shop.engine) as db:
        db.get(Product, uuid.UUID(shop.products["asus-zen"])).Specifications = None
        db.commit()
    show(shop)
    service, _ = shop.service([finish("product", shop.products["asus-zen"])])
    response = ask(shop, service, "Giới thiệu chi tiết máy thứ nhất")
    assert "Chưa có thông số chi tiết cho mẫu này" in response.AiMessages[0].Content
    assert "catalog" not in response.AiMessages[0].Content.lower()


def test_a_comparison_answer_and_its_saved_table_do_not_narrate_information_processing(grounded_shop):
    service, _ = grounded_shop.service([])
    response = ask(grounded_shop, service, "So sánh asus-zen và lenovo-idea")
    message = response.AiMessages[0]
    assert message.Content.startswith("So sánh các mẫu sau:")
    public = fold(json.dumps({"Content": message.Content, "Comparison": table(response)}, ensure_ascii=False))
    assert all(term not in public for term in ("du lieu", "doi chieu", "xac minh", "can cu"))
    assert any("Chưa rõ" in row["Values"] for row in table(response)["Rows"])


@pytest.mark.parametrize("message", [
    "Theo dữ liệu hiện có, asus-zen có RAM 16 GB.",
    "Mình đã đối chiếu và xác minh thông tin của asus-zen.",
    "Dựa trên thông số, asus-zen có RAM 16 GB.",
])
def test_process_narration_from_the_model_is_replaced_by_direct_product_advice(grounded_shop, message):
    shop = grounded_shop
    decision = {**finish("product", shop.products["asus-zen"]), "message": message}
    service, _ = shop.service([[call("get_product", product_id=shop.products["asus-zen"])], decision])
    response = ask(shop, service, "asus-zen có RAM bao nhiêu?")
    answer = response.AiMessages[0].Content
    assert "RAM: 16 GB" in answer
    assert all(term not in fold(answer) for term in ("du lieu", "doi chieu", "xac minh", "dua tren"))


@pytest.mark.parametrize("before,after", [
    ("Chưa đủ dữ liệu để xác nhận 3840×2160 ở 144 Hz.", "Chưa thể xác nhận 3840×2160 ở 144 Hz."),
    ("USB-C chỉ truyền dữ liệu, không xuất hình.", "USB-C chỉ truyền tệp, không xuất hình."),
    ("USB-C data only; không có DisplayPort Alt Mode.", "USB-C chỉ truyền tệp, không có DisplayPort Alt Mode."),
    ("Cáp HDMI truyền video phù hợp giữa hai cổng đã xác minh.", "Cáp HDMI truyền video phù hợp giữa hai cổng."),
])
def test_wording_keeps_negation_connector_requirements_and_numeric_limits(before, after):
    assert customer_text(before) == after


def test_wording_does_not_change_machine_verdicts_ids_prices_or_the_original_snapshot():
    original = {"Comparison": {"Products": [{"ProductId": "keep-id", "Price": "22041000.00", "Score": .8}],
                               "Rows": [{"Key": "ram", "Values": ["Chưa có dữ liệu", "16 GB"]}]},
                "Compatibility": {"Status": "unknown", "Basis": "device_type", "ModeBasis": "published_max",
                    "Request": {"Width": 3840, "Height": 2160, "RefreshHz": 144},
                    "Explanation": "Chưa đủ dữ liệu để xác nhận.", "Conditions": ["Cáp phải hỗ trợ 3840×2160 @ 144 Hz."]}}
    shown = customer_notes(original)
    assert shown["Comparison"]["Products"] == original["Comparison"]["Products"]
    assert shown["Comparison"]["Rows"][0]["Values"] == ["Chưa rõ", "16 GB"]
    assert original["Comparison"]["Rows"][0]["Values"][0] == "Chưa có dữ liệu"
    for key in ("Status", "Basis", "ModeBasis", "Request", "Conditions"):
        assert shown["Compatibility"][key] == original["Compatibility"][key]
    assert shown["Compatibility"]["Explanation"] == "Chưa thể xác nhận."


def test_saved_and_new_wording_do_not_repeat_connection_conditions_when_rendered_again():
    before = "Kết nối cơ bản: Có căn cứ xác nhận trong điều kiện đã nêu."
    after = "Kết nối cơ bản: Đáp ứng trong điều kiện đã nêu."
    assert customer_text(before) == customer_text(after) == after


@pytest.mark.parametrize("sentence", [
    "Chưa thể chọn một mẫu phù hợp hơn với nhu cầu của bạn.",
    "Chưa đủ căn cứ để chọn một mẫu phù hợp hơn. Bạn cho mình biết nhu cầu ưu tiên nhé.",
    "Chưa thể kết luận để chọn một mẫu phù hợp hơn.",
])
def test_unwanted_default_recommendations_are_removed_without_replacement(sentence):
    assert customer_text(sentence) == ""
    assert customer_text("RAM: 16 GB.\n\n" + sentence) == "RAM: 16 GB."


def test_no_default_recommendation_is_added_when_the_comparison_has_no_winner(grounded_shop):
    service, _ = grounded_shop.service([])
    response = ask(grounded_shop, service, "So sánh asus-zen và lenovo-idea")
    snapshot = table(response)
    assert snapshot["Recommendation"] == ""
    assert snapshot["RecommendedProductVariantId"] is None
    assert not response.AiMessages[0].Content.rstrip().endswith("nhu cầu của bạn.")
    assert len(snapshot["Products"]) == 2 and snapshot["Rows"]


def test_a_model_reply_containing_only_the_removed_sentence_still_returns_product_details(grounded_shop):
    shop = grounded_shop
    decision = {**finish("product", shop.products["asus-zen"]),
                "message": "Chưa thể chọn một mẫu phù hợp hơn với nhu cầu của bạn."}
    service, _ = shop.service([[call("get_product", product_id=shop.products["asus-zen"])], decision])
    response = ask(shop, service, "asus-zen có RAM bao nhiêu?")
    assert response.Status == "Completed"
    assert "RAM: 16 GB" in response.AiMessages[0].Content
    assert "Chưa thể chọn" not in response.AiMessages[0].Content
