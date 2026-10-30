"""Smart Compare through real catalog/pricing/history on isolated SQLite; no shared DB/provider."""

import copy
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Brand, Category, Message, Product, ProductVariant, Promotion, PromotionProduct
from app.schemas.ai_chat import AiMessageCancel, AiMessageCreate, PresentAnswerArguments
from app.schemas.ai_comparison import ComparisonSnapshot
from app.schemas.chat import MessageResponse
from app.services.ai_comparison import normalized_specs
from app.services.chat import ChatService
from app.services.exceptions import AiUnavailableError, ConflictError
from tests.test_ai_grounded import ask, call, finish, grounded_shop  # noqa: F401

NAMES = ("asus-zen", "lenovo-idea", "asus-vivo")


def show(shop, names=NAMES[:2]):
    service, _ = shop.service([[call("get_product", product_ids=[shop.products[n] for n in names])],
                               finish("recommend", *(shop.products[n] for n in names))])
    result = ask(shop, service, "Gợi ý laptop mới nhất")
    assert len([m for m in result.AiMessages if m.MessageType == "Product"]) == len(names)
    shop.now.value += timedelta(seconds=1)
    return result


def compare(shop, names=NAMES[:2], message=None):
    decision = finish("compare", *(shop.products[n] for n in names))
    if message:
        decision["message"] = message
    service, model = shop.service([decision])
    return ask(shop, service, "So sánh " + " và ".join(names)), service, model


def model_compare(shop, steps, question="So sánh 2 mẫu laptop ASUS mới nhất"):
    """A comparison whose subjects only the model picks (the backend resolves none from the question)."""
    service, model = shop.service(steps)
    return ask(shop, service, question), model


def table(response):
    return response.AiMessages[0].Metadata["Comparison"]


def rename(shop, names):
    with Session(shop.engine) as db:
        for old, new in names.items():
            db.get(Product, uuid.UUID(shop.products[old])).Name = new
        db.commit()


@pytest.mark.parametrize("count", [2, 3])
def test_two_or_three_columns_are_current_public_data_and_persist_without_migration(grounded_shop, count):
    shop = grounded_shop
    names = NAMES[:count]
    response, service, model = compare(shop, names)
    snapshot = table(response)
    assert response.Status == "Completed"
    assert [p["ProductId"] for p in snapshot["Products"]] == [shop.products[n] for n in names]
    assert [p["ProductVariantId"] for p in snapshot["Products"]] == [shop.variants[n] for n in names]
    assert all(len(row["Values"]) == count for row in snapshot["Rows"])
    assert all(p["Brand"] and p["Category"] and p["Slug"] for p in snapshot["Products"])
    with Session(shop.engine) as db:
        saved = db.get(Message, response.AiMessages[0].MessageId)
        assert saved.Metadata["Comparison"] == snapshot
        history = ChatService(db).get_conversation(shop.actor, shop.cid)
        restored = next(m for m in history.Messages if m.MessageId == saved.MessageId)
        assert restored.Metadata["Comparison"] == snapshot
        assert "ProductReferences" not in restored.Metadata
        assert db.get(Message, response.CustomerMessage.MessageId).Metadata["AiModel"] == "vietech-rules"
    # Resolved SKUs need no model round: its wording is never shown for a verified table.
    assert model.calls == []


@pytest.mark.parametrize("question,count", [
    ("So sánh 2 laptop vừa giới thiệu.", 2),
    ("Máy thứ nhất và máy thứ hai khác nhau thế nào?", 2),
    ("So sánh 3 sản phẩm trên.", 3),
    ("Tôi học lập trình, trong 2 laptop đó nên mua máy nào?", 2),
    ("Máy nào pin tốt hơn?", 2),
    ("So sánh camera, hiệu năng và giá của hai điện thoại này.", 2),
])
def test_conversation_references_use_exact_shown_order(grounded_shop, question, count):
    shop = grounded_shop
    shown = show(shop, NAMES[:count])
    expected = [m.Metadata["ProductVariantId"] for m in shown.AiMessages if m.MessageType == "Product"]
    service, _ = shop.service([finish("chat")])  # Backend owns comparison scope even if Gemini misclassifies.
    result = ask(shop, service, question)
    assert [p["ProductVariantId"] for p in table(result)["Products"]] == expected


@pytest.mark.parametrize("question", ["So sánh 4 sản phẩm trên", "So sánh máy thứ nhất", "So sánh 3 sản phẩm trên"])
def test_invalid_number_of_references_asks_instead_of_guessing(grounded_shop, question):
    shop = grounded_shop
    show(shop)
    service, model = shop.service([])
    result = ask(shop, service, question)
    assert model.calls == []
    assert not (result.AiMessages[0].Metadata or {}).get("Comparison")
    assert len(result.AiMessages) == 1


@pytest.mark.parametrize("question", ["So sánh 2 laptop vừa giới thiệu", "Máy nào pin tốt hơn?"])
def test_unresolved_history_asks_which_products(grounded_shop, question):
    service, model = grounded_shop.service([])
    result = ask(grounded_shop, service, question)
    assert model.calls == [] and "?" in result.AiMessages[0].Content
    assert "Comparison" not in (result.AiMessages[0].Metadata or {})


@pytest.mark.parametrize("question", ["So sánh asus-missing và lenovo-idea", "So sánh asus-ghost và lenovo-idea",
                                     "So sánh asus-zen và lenovo-idea và asus-vivo và asus-ghost"])
def test_missing_ambiguous_variant_or_over_limit_is_clarified(grounded_shop, question):
    service, model = grounded_shop.service([])
    result = ask(grounded_shop, service, question)
    assert result.Status == "Completed" and model.calls == []
    assert "Comparison" not in (result.AiMessages[0].Metadata or {})


def test_duplicate_product_names_require_a_choice(grounded_shop):
    shop = grounded_shop
    with Session(shop.engine) as db:
        db.get(Product, uuid.UUID(shop.products["asus-vivo"])).Name = "asus-zen"
        db.commit()
    service, model = shop.service([])
    result = ask(shop, service, "So sánh asus-zen và lenovo-idea")
    assert "nhiều sản phẩm" in result.AiMessages[0].Content and model.calls == []


def test_variant_clarification_can_be_answered_on_the_next_turn_after_reload(grounded_shop):
    shop = grounded_shop
    first, model = shop.service([])
    clarification = ask(shop, first, "So sánh asus-ghost và lenovo-idea")
    assert "phiên bản nào" in clarification.AiMessages[0].Content and model.calls == []
    shop.now.value += timedelta(seconds=1)
    # A new service reads the pending subjects from saved internal slots, not process-local state.
    resumed, _ = shop.service([finish("chat")])
    snapshot = table(ask(shop, resumed, "Chọn bản 16GB / 512GB"))
    assert [p["ProductId"] for p in snapshot["Products"]] == [shop.products["asus-ghost"], shop.products["lenovo-idea"]]
    assert snapshot["Products"][0]["ProductVariantId"] == shop.variants["asus-ghost"]
    assert snapshot["Products"][0]["InStock"] is False


def test_variant_reply_does_not_match_a_substring_of_a_different_capacity(grounded_shop):
    shop = grounded_shop
    first, _ = shop.service([])
    ask(shop, first, "So sánh asus-ghost và lenovo-idea")
    shop.now.value += timedelta(seconds=1)
    resumed, model = shop.service([])
    result = ask(shop, resumed, "Chọn bản 116GB / 1512GB")
    assert "phiên bản nào" in result.AiMessages[0].Content and model.calls == []
    assert "Comparison" not in (result.AiMessages[0].Metadata or {})


@pytest.mark.parametrize("change", ["Draft", "Discontinued", "deleted", "variant_hidden"])
def test_hidden_or_discontinued_product_is_not_leaked_or_replaced(grounded_shop, change):
    shop = grounded_shop
    show(shop)
    with Session(shop.engine) as db:
        product = db.get(Product, uuid.UUID(shop.products[NAMES[0]]))
        if change == "deleted":
            product.IsDeleted = True
        elif change == "variant_hidden":
            db.get(ProductVariant, uuid.UUID(shop.variants[NAMES[0]])).IsActive = False
        else:
            product.Status = change
        db.commit()
    service, model = shop.service([])
    result = ask(shop, service, "So sánh hai sản phẩm trên")
    assert model.calls == [] and "Comparison" not in (result.AiMessages[0].Metadata or {})


def test_out_of_stock_reference_keeps_its_sku_and_does_not_use_a_more_expensive_one(grounded_shop):
    shop = grounded_shop
    show(shop)
    with Session(shop.engine) as db:
        old = db.get(ProductVariant, uuid.UUID(shop.variants[NAMES[0]]))
        old.StockQuantity = 0
        db.add(ProductVariant(ProductId=old.ProductId, Sku="other-memory", VariantName="32 GB / 1 TB", Storage="1 TB",
                              Price=29000000, CostPrice=10000000, StockQuantity=5))
        db.commit()
    service, _ = shop.service([finish("chat")])
    snapshot = table(ask(shop, service, "So sánh 2 laptop trên"))
    assert snapshot["Products"][0]["ProductVariantId"] == shop.variants[NAMES[0]]
    assert not snapshot["Products"][0]["InStock"]
    assert Decimal(snapshot["Products"][0]["Price"]) == 18000000
    assert next(row for row in snapshot["Rows"] if row["Key"] == "storage")["Values"][0] == "512 GB"


def test_actual_automatic_sale_price_is_used(grounded_shop):
    shop = grounded_shop
    with Session(shop.engine) as db:
        promotion = Promotion(CreatedByUserId=shop.actor.user_id, Name="Test automatic", ApplyMode="Automatic", Status="Active",
            DiscountType="FixedAmount", DiscountValue=2000000, MinOrderValue=0,
            StartDate=shop.now.value - timedelta(days=1), EndDate=shop.now.value + timedelta(days=1))
        db.add(promotion); db.flush()
        db.add(PromotionProduct(PromotionId=promotion.PromotionId, ProductId=uuid.UUID(shop.products[NAMES[0]])))
        db.commit()
    snapshot = table(compare(shop)[0])
    assert Decimal(snapshot["Products"][0]["Price"]) == 16000000


def test_named_phone_models_resolve_without_using_external_model_knowledge(grounded_shop):
    shop = grounded_shop
    names = ("iPhone 17 Pro", "Samsung Galaxy S26 Ultra")
    with Session(shop.engine) as db:
        for old, new in zip(NAMES, names):
            product = db.get(Product, uuid.UUID(shop.products[old]))
            product.Name = new
            db.get(Category, product.CategoryId).Name = "Điện thoại"
        db.commit()
    service, _ = shop.service([finish("chat")])
    snapshot = table(ask(shop, service, "So sánh iPhone 17 Pro và Samsung Galaxy S26 Ultra."))
    assert [p["ProductName"] for p in snapshot["Products"]] == list(names)
    assert any(row["Key"] == "camera" for row in snapshot["Rows"])
    assert not any(row["Key"] == "gpu" for row in snapshot["Rows"])


def test_price_and_stock_are_rechecked_after_model_io(grounded_shop):
    shop = grounded_shop
    def changed(_):
        with Session(shop.engine) as db:
            variant = db.get(ProductVariant, uuid.UUID(shop.variants[NAMES[0]]))
            variant.Price = 19000000
            variant.StockQuantity = 0
            db.commit()
        return finish("compare", shop.products[NAMES[0]], shop.products[NAMES[2]])
    ids = [shop.products[NAMES[0]], shop.products[NAMES[2]]]
    result, _ = model_compare(shop, [[call("get_product", product_ids=ids)], changed])
    snapshot = table(result)
    assert [p["ProductId"] for p in snapshot["Products"]] == ids
    assert Decimal(snapshot["Products"][0]["Price"]) == 19000000
    assert snapshot["Products"][0]["InStock"] is False


def test_http_comparison_replay_recovery_and_history_share_the_public_snapshot(grounded_shop):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.core.dependencies import get_current_actor
    from app.routers.chat import router
    from app.routers.dependencies import get_ai_chat_service, get_chat_service
    from app.routers.errors import service_error_handler
    from app.services.exceptions import ServiceError

    shop = grounded_shop
    service, model = shop.service([finish("chat")])
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ServiceError, service_error_handler)
    app.dependency_overrides[get_current_actor] = lambda: shop.actor
    app.dependency_overrides[get_ai_chat_service] = lambda: service
    with Session(shop.engine) as db:
        app.dependency_overrides[get_chat_service] = lambda: ChatService(db)
        with TestClient(app) as client:
            path = f"/conversations/{shop.cid}"
            body = {"ClientRequestId": str(uuid.uuid4()), "Content": "So sánh asus-zen và lenovo-idea"}
            response = client.post(path + "/ai-messages", json=body)
            assert response.status_code == 200, response.text
            original = response.json()["AiMessages"][0]
            replay = client.post(path + "/ai-messages", json=body).json()["AiMessages"][0]
            recovery = client.get(path + "/ai-messages/" + body["ClientRequestId"]).json()["AiMessages"][0]
            history = client.get(path).json()["Messages"]
            restored = next(m for m in history if m["MessageId"] == original["MessageId"])
            assert original["Metadata"] == replay["Metadata"] == recovery["Metadata"] == restored["Metadata"]
            assert "Comparison" in restored["Metadata"] and "ProductReferences" not in restored["Metadata"]
            assert model.calls == []


def test_needs_use_existing_recommendation_criteria_without_favoring_price(grounded_shop):
    shop = grounded_shop
    with Session(shop.engine) as db:
        for name, ram in [(NAMES[0], "8 GB"), (NAMES[1], "16 GB")]:
            db.get(Product, uuid.UUID(shop.products[name])).Specifications = {"Processor": "Intel Core i5-13420H",
                "Memory RAM": ram, "SSD": "512 GB SSD", "Khe RAM": "2 khe, nâng cấp", "Battery": "54 Wh", "Weight": "1.4 kg"}
            db.get(ProductVariant, uuid.UUID(shop.variants[name])).VariantName = f"RAM {ram}, SSD 512 GB"
        db.commit()
    show(shop)
    service, _ = shop.service([finish("chat")])
    snapshot = table(ask(shop, service, "Tôi học lập trình và mang đi học, so sánh hai laptop trên để chạy Android Studio"))
    assert snapshot["RecommendedProductVariantId"] == shop.variants[NAMES[1]]  # Cheaper but better stated RAM.
    assert snapshot["Caveats"] == ["Chưa có kết quả chạy thử Android Studio trên các mẫu này để xác nhận mức đáp ứng bạn hỏi."]
    assert "RAM 16 GB" in snapshot["Recommendation"]


def test_missing_specs_are_explicit_and_never_produce_a_winner(grounded_shop):
    shop = grounded_shop
    with Session(shop.engine) as db:
        for name in NAMES[:2]:
            db.get(Product, uuid.UUID(shop.products[name])).Specifications = None
            variant = db.get(ProductVariant, uuid.UUID(shop.variants[name]))
            variant.VariantName = "Tiêu chuẩn"
        db.commit()
    show(shop)
    service, _ = shop.service([finish("chat")])
    snapshot = table(ask(shop, service, "Tôi học lập trình, so sánh 2 laptop trên"))
    assert all(value == "Chưa rõ" for row in snapshot["Rows"] for value in row["Values"])
    assert snapshot["RecommendedProductVariantId"] is None
    assert all(p["Completeness"] < .7 for p in snapshot["Products"])


@pytest.mark.parametrize("code", ["ai_unavailable", "ai_quota_exceeded", "ai_invalid_output"])
def test_verified_comparison_does_not_depend_on_the_provider_and_replays(grounded_shop, code):
    shop = grounded_shop
    def fail(_):
        raise AiUnavailableError("Test provider failure", code=code, retry_after_seconds=30 if code == "ai_quota_exceeded" else None)
    service, model = shop.service([fail, fail])
    data = AiMessageCreate(ClientRequestId=uuid.uuid4(), Content="So sánh asus-zen và lenovo-idea")
    result = service.ask(shop.actor, shop.cid, data)
    assert result.Status == "Completed" and table(result)["AnalysisStatus"] == "verified"
    replay = service.ask(shop.actor, shop.cid, data)
    restored = service.get_status(shop.actor, shop.cid, data.ClientRequestId)
    assert table(replay) == table(restored) == table(result)
    assert [m.MessageId for m in replay.AiMessages] == [m.MessageId for m in result.AiMessages]
    assert model.calls == []


@pytest.mark.parametrize("code", ["ai_unavailable", "ai_quota_exceeded", "ai_invalid_output"])
def test_provider_failure_while_the_model_picks_products_fails_without_a_guessed_table(grounded_shop, code):
    shop = grounded_shop
    def fail(_):
        raise AiUnavailableError("Test provider failure", code=code, retry_after_seconds=30 if code == "ai_quota_exceeded" else None)
    service, _ = shop.service([fail, fail])
    data = AiMessageCreate(ClientRequestId=uuid.uuid4(), Content="So sánh 2 mẫu laptop ASUS mới nhất")
    with pytest.raises(AiUnavailableError) as error:
        service.ask(shop.actor, shop.cid, data)
    assert error.value.code == code
    assert service.get_status(shop.actor, shop.cid, data.ClientRequestId).Status == "Failed"
    with Session(shop.engine) as db:
        assert not list(db.scalars(select(Message).where(Message.SenderType == "AI")))
    if code == "ai_quota_exceeded":  # The provider cooldown still applies to the next question.
        with pytest.raises(AiUnavailableError) as cooldown:
            ask(shop, service, "Xin chào")
        assert cooldown.value.code == "ai_quota_exceeded"


def test_cancel_during_comparison_still_fences_off_late_completion(grounded_shop):
    shop = grounded_shop
    data = AiMessageCreate(ClientRequestId=uuid.uuid4(), Content="So sánh 2 mẫu laptop ASUS mới nhất")
    ids = [shop.products[NAMES[0]], shop.products[NAMES[2]]]
    other, _ = shop.service([])
    def cancel(_):  # The customer stops the answer while the model is still choosing; its late result is discarded.
        other.cancel(shop.actor, shop.cid, data.ClientRequestId, AiMessageCancel(Content=data.Content))
        return finish("compare", *ids)
    service, _ = shop.service([[call("get_product", product_ids=ids)], cancel])
    with pytest.raises(ConflictError):
        service.ask(shop.actor, shop.cid, data)
    assert service.get_status(shop.actor, shop.cid, data.ClientRequestId).Status == "Cancelled"
    with Session(shop.engine) as db:
        assert not list(db.scalars(select(Message).where(Message.SenderType == "AI")))


@pytest.mark.parametrize("claim", ["asus-zen có 64 GB RAM và pin 90 Wh.",
                                  "asus-zen chạy Android Studio mượt và nhanh hơn 3 lần.",
                                  "asus-zen chạy Android Studio mượt hơn và có camera đẹp hơn."])
def test_unverified_numeric_and_qualitative_model_claims_are_never_rendered(grounded_shop, claim):
    shop = grounded_shop
    ids = [shop.products[NAMES[0]], shop.products[NAMES[2]]]
    decision = {**finish("compare", *ids), "message": claim}
    result, model = model_compare(shop, [[call("get_product", product_ids=ids)], decision])
    assert len(model.calls) == 2 and table(result)["Products"][0]["ProductId"] == ids[0]
    assert claim not in result.model_dump_json()


@pytest.mark.parametrize("variant_text,storage,ram,disk", [
    ("8 GB / 256 GB", None, "8 GB", "256 GB"),
    ("RAM 32GB, SSD 1TB", None, "32GB", "1TB"),
    ("8GB / 256GB", "256GB", "8GB", "256GB"),
    ("8GB 256GB", "256GB", "8GB", "256GB"),
    ("Tiêu chuẩn", "512 GB", "16 GB", "512 GB"),
])
def test_normalization_overlays_sku_memory_on_shared_specs(variant_text, storage, ram, disk):
    from types import SimpleNamespace
    variant = SimpleNamespace(VariantName=variant_text, Storage=storage, Color=None)
    specs = normalized_specs({"Hardware": {"RAM": "16 GB", "SSD": "128 GB"}, "Processor": "Intel Core i5"}, variant, "laptop")
    assert specs["ram"] == ram and specs["storage"] == disk and specs["cpu"] == "Intel Core i5"


def test_same_product_can_compare_two_explicit_variants_but_not_duplicates(grounded_shop):
    shop = grounded_shop
    pid = shop.products[NAMES[0]]
    with Session(shop.engine) as db:
        second = ProductVariant(ProductId=uuid.UUID(pid), Sku="second-version", VariantName="8GB / 256GB", Storage="8GB / 256GB",
                                Price=15000000, CostPrice=10000000, StockQuantity=3)
        db.add(second); db.commit()
        vid = str(second.ProductVariantId)
    # Explicit tool selections are checked against the catalog read in this turn.
    selected = [{"product_id": pid, "product_variant_id": shop.variants[NAMES[0]]}, {"product_id": pid, "product_variant_id": vid}]
    service, _ = shop.service([[call("get_product", product_id=pid)], {"intent": "compare", "products": selected}])
    snapshot = table(ask(shop, service, "So sánh các phiên bản asus-zen"))
    assert [p["ProductVariantId"] for p in snapshot["Products"]] == [s["product_variant_id"] for s in selected]
    assert next(row for row in snapshot["Rows"] if row["Key"] == "ram")["Values"] == ["16 GB", "8GB"]
    with pytest.raises(ValidationError):
        PresentAnswerArguments(intent="compare", products=[selected[0], selected[0]])


def test_schema_rejects_over_limit_or_misaligned_data_and_history_ignores_invalid_snapshot(grounded_shop):
    result, _, _ = compare(grounded_shop)
    valid = table(result)
    invalid = copy.deepcopy(valid)
    invalid["Rows"][0]["Values"] = ["one"]
    with pytest.raises(ValidationError):
        ComparisonSnapshot.model_validate(invalid)
    message = result.AiMessages[0].model_dump()
    message["Metadata"] = {"Comparison": invalid, "AiLeaseToken": "internal"}
    assert MessageResponse.model_validate(message).Metadata is None
    with pytest.raises(ValidationError):
        PresentAnswerArguments(intent="compare", products=[{"product_id": uuid.uuid4()} for _ in range(4)])


def test_two_products_needing_a_version_are_resolved_one_reply_at_a_time(grounded_shop):
    shop = grounded_shop
    with Session(shop.engine) as db:
        db.add(ProductVariant(ProductId=uuid.UUID(shop.products["lenovo-idea"]), Sku="lenovo-8", VariantName="8 GB / 256 GB",
                              Price=14000000, CostPrice=7000000, StockQuantity=2))
        db.commit()
    first, _ = shop.service([])
    assert "phiên bản nào của asus-ghost" in ask(shop, first, "So sánh asus-ghost và lenovo-idea").AiMessages[0].Content
    # Each reply answers the product the previous question named; a new service reads the saved slots only.
    for reply, asked in [("Chọn bản Available", "phiên bản nào của lenovo-idea"), ("Bản 8 GB / 256 GB", None)]:
        shop.now.value += timedelta(seconds=1)
        service, model = shop.service([])
        result = ask(shop, service, reply)
        assert model.calls == []
        if asked:
            assert asked in result.AiMessages[0].Content
    assert [p["VariantName"] for p in table(result)["Products"]] == ["Available", "8 GB / 256 GB"]


def test_new_request_after_a_version_question_is_not_taken_as_the_version(grounded_shop):
    shop = grounded_shop
    first, _ = shop.service([])
    ask(shop, first, "So sánh asus-ghost và lenovo-idea")
    shop.now.value += timedelta(seconds=1)
    service, model = shop.service([finish("chat")])
    result = ask(shop, service, "Thôi, tư vấn laptop RAM 16GB dưới 25 triệu")
    assert len(model.calls) == 1 and "phiên bản nào" not in result.AiMessages[0].Content
    assert "Comparison" not in (result.AiMessages[0].Metadata or {})


@pytest.mark.parametrize("question", [
    "So sánh giữa Zenbook 14 và IdeaPad Slim 5",
    "So sánh giúp mình Zenbook 14 với IdeaPad Slim 5",
    "Zenbook 14 và IdeaPad Slim 5 khác nhau thế nào?",
    "Zenbook 14 với IdeaPad Slim 5 thì nên chọn máy nào?",
    "Giữa Zenbook 14 và IdeaPad Slim 5, máy nào tốt hơn?",
])
def test_common_phrasings_resolve_the_named_products_instead_of_claiming_they_are_not_sold(grounded_shop, question):
    shop = grounded_shop
    rename(shop, {"asus-zen": "Zenbook 14", "lenovo-idea": "IdeaPad Slim 5"})
    service, model = shop.service([])
    result = ask(shop, service, question)
    assert "chưa tìm thấy" not in result.AiMessages[0].Content
    assert [p["ProductName"] for p in table(result)["Products"]] == ["Zenbook 14", "IdeaPad Slim 5"]
    assert model.calls == []


@pytest.mark.parametrize("question", [
    "So sánh iPhone 17 Pro và Samsung Galaxy S26 Ultra về camera, pin và hiệu năng.",
    "So sánh iPhone 17 Pro và Samsung Galaxy S26 Ultra về: camera, pin và hiệu năng.",
    "So sánh iPhone 17 Pro, Samsung Galaxy S26 Ultra theo camera, pin, hiệu năng và giá.",
    "So sánh camera, pin và hiệu năng của iPhone 17 Pro và Samsung Galaxy S26 Ultra.",
    "So sánh giúp mình iPhone 17 Pro với Samsung Galaxy S26 Ultra về camera, pin, hiệu năng, màn hình và giá.",
])
def test_comparison_criteria_are_not_counted_as_additional_products(grounded_shop, question):
    shop = grounded_shop
    rename(shop, {"asus-zen": "iPhone 17 Pro 256GB", "lenovo-idea": "Samsung Galaxy S26 Ultra 5G 12GB 256GB",
                  "asus-vivo": "iPhone 17 Pro Max 512GB"})
    with Session(shop.engine) as db:
        category = db.scalars(select(Category).where(Category.Name == "Laptop")).one()
        category.Name, category.Slug = "Điện thoại", "dien-thoai"
        for name in NAMES:
            db.get(Product, uuid.UUID(shop.products[name])).Specifications = {
                "Camera sau": "48 MP", "Pin": "5000 mAh", "CPU": "Test CPU", "RAM": "16 GB"}
        db.commit()
    service, model = shop.service([])
    result = ask(shop, service, question)
    snapshot = table(result)
    assert [p["ProductId"] for p in snapshot["Products"]] == [shop.products["asus-zen"], shop.products["lenovo-idea"]]
    assert {"camera", "battery", "cpu"} <= {row["Key"] for row in snapshot["Rows"]}
    assert "tối đa 3 sản phẩm" not in result.AiMessages[0].Content
    assert model.calls == []


def test_three_named_products_still_compare_with_a_long_list_of_criteria(grounded_shop):
    service, model = grounded_shop.service([])
    result = ask(grounded_shop, service,
                 "So sánh asus-zen, lenovo-idea và asus-vivo về CPU, RAM, pin, màn hình và giá.")
    assert [p["ProductId"] for p in table(result)["Products"]] == [grounded_shop.products[name] for name in NAMES]
    assert model.calls == []


def test_four_actual_products_are_still_rejected_even_with_comparison_criteria(grounded_shop):
    service, model = grounded_shop.service([])
    result = ask(grounded_shop, service,
                 "So sánh asus-zen, lenovo-idea, asus-vivo và asus-ghost về CPU, pin và hiệu năng.")
    assert "tối đa 3 sản phẩm" in result.AiMessages[0].Content
    assert "Comparison" not in (result.AiMessages[0].Metadata or {})
    assert model.calls == []


def test_model_comparison_is_kept_when_the_backend_read_the_question_as_another_intent(grounded_shop):
    shop = grounded_shop
    show(shop)
    ids = [shop.products[NAMES[1]], shop.products["asus-vivo"]]
    service, _ = shop.service([[call("get_product", product_id=ids[1])], finish("compare", *ids)])
    result = ask(shop, service, "Máy thứ hai có gì hơn asus-vivo không?")  # Read as a recommendation with one reference.
    assert [p["ProductId"] for p in table(result)["Products"]] == ids


def test_same_value_written_differently_is_not_a_difference(grounded_shop):
    shop = grounded_shop
    with Session(shop.engine) as db:
        db.get(ProductVariant, uuid.UUID(shop.variants[NAMES[0]])).VariantName = "16GB / 512GB"
        db.commit()
    snapshot = table(compare(shop)[0])
    assert next(row for row in snapshot["Rows"] if row["Key"] == "ram")["Values"] == ["16GB", "16 GB"]
    assert not any(line.startswith(("RAM", "Bộ nhớ")) for line in snapshot["Differences"])


@pytest.mark.parametrize("features,refresh", [
    ("Dynamic Island; Màn hình luôn bật; HDR; 460 ppi; True Tone", None),
    ("Tần số quét 120Hz; Độ sáng tối đa 3000 nits", "120 Hz"),
])
def test_screen_features_only_fill_the_refresh_row_with_a_stated_hz(features, refresh):
    from types import SimpleNamespace
    variant = SimpleNamespace(VariantName="256GB", Storage="256GB", Color=None)
    specs = normalized_specs({"Tính năng màn hình": features, "Kích thước màn hình": "6.1 inch"}, variant, "phone")
    assert specs.get("refresh") == refresh


@pytest.mark.parametrize("question", ["So sánh 2 mẫu laptop Dell rẻ nhất", "So sánh 2 laptop rẻ nhất",
                                      "Máy nào dưới 25 triệu pin tốt hơn?"])
def test_a_question_asking_for_a_new_set_does_not_reuse_the_list_just_shown(grounded_shop, question):
    shop = grounded_shop
    with Session(shop.engine) as db:
        db.add(Brand(Name="Dell", Slug="dell")); db.commit()
    show(shop)
    ids = [shop.products["asus-vivo"], shop.products["lenovo-idea"]]
    service, model = shop.service([[call("get_product", product_ids=ids)], finish("compare", *ids)])
    result = ask(shop, service, question)
    assert len(model.calls) == 2  # The model reads the catalog for the new set; the old list is not reused.
    assert [p["ProductId"] for p in table(result)["Products"]] == ids


PROGRAMMING_SPECS = {"Memory RAM": "16 GB", "SSD": "512 GB SSD", "Khe RAM": "2 khe, nâng cấp", "Battery": "54 Wh",
                     "Weight": "1.4 kg"}


def test_recommendation_states_what_decided_it_and_what_the_other_does_better(grounded_shop):
    """Live case: a mid-tier CPU in the curated 'Laptop lập trình' group beat a high-tier CPU with the same RAM/SSD,
    while the advice quoted RAM, SSD and the weaker CPU as the reasons."""
    shop = grounded_shop
    with Session(shop.engine) as db:
        laptop = db.scalars(select(Category).where(Category.Name == "Laptop")).one()
        curated = Category(Name="Laptop lập trình", Slug="laptop-lap-trinh", ParentCategoryId=laptop.CategoryId)
        db.add(curated); db.flush()
        for name, cpu in [(NAMES[0], "Intel Core i5-13420H"), (NAMES[1], "Intel Core i7-13620H")]:
            product = db.get(Product, uuid.UUID(shop.products[name]))
            product.Specifications = {**PROGRAMMING_SPECS, "Processor": cpu}
            if name == NAMES[0]:
                product.CategoryId = curated.CategoryId
        db.commit()
    service, _ = shop.service([])
    snapshot = table(ask(shop, service, "Tôi học lập trình, so sánh asus-zen và lenovo-idea"))
    reason, _, other = snapshot["Recommendation"].partition(" lenovo-idea mạnh hơn về: ")
    assert snapshot["RecommendedProductVariantId"] == shop.variants[NAMES[0]]
    assert reason.endswith("nhờ: thuộc nhóm Laptop lập trình.")  # Not the shared RAM/SSD or its weaker CPU.
    assert "Core i7-13620H" in other


def test_identical_specs_are_never_told_apart_by_specs_only_by_the_stated_price(grounded_shop):
    shop = grounded_shop
    with Session(shop.engine) as db:
        for name, price in [(NAMES[0], 19500000), (NAMES[1], 15000000)]:
            db.get(Product, uuid.UUID(shop.products[name])).Specifications = {**PROGRAMMING_SPECS,
                                                                             "Processor": "Intel Core i5-13420H"}
            db.get(ProductVariant, uuid.UUID(shop.variants[name])).Price = price
        db.commit()
    service, _ = shop.service([])
    plain = table(ask(shop, service, "Tôi học lập trình, so sánh asus-zen và lenovo-idea"))
    assert plain["RecommendedProductVariantId"] is None
    shop.now.value += timedelta(seconds=1)
    service, _ = shop.service([])
    budget = table(ask(shop, service, "Tôi học lập trình, ngân sách dưới 20 triệu, so sánh asus-zen và lenovo-idea"))
    assert budget["RecommendedProductVariantId"] == shop.variants[NAMES[1]]
    assert budget["Recommendation"] == ("lenovo-idea (16 GB / 512 GB) phù hợp hơn với nhu cầu của bạn nhờ: "
                                        "giá thấp hơn, trong ngân sách 20.000.000 đ.")
