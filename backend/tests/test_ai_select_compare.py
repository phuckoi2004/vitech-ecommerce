"""Select products within the customer's constraints, then compare without a provider round."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import Category, ProductVariant
from app.schemas.ai_chat import AiMessageCreate, PresentAnswerArguments
from app.services.ai_tools import AiTools, GroundingContext
from tests.test_ai_comparison import table, show
from tests.test_ai_grounded import ask, grounded_shop  # noqa: F401


@pytest.mark.parametrize("question,count", [
    ("Hãy chọn 2 laptop dưới 25 triệu rồi so sánh CPU, RAM, SSD, màn hình và giá.", 2),
    ("Chọn giúp tôi 2 laptop dưới 25 triệu và so sánh về CPU, RAM, SSD, màn hình và giá.", 2),
    ("Tìm 2 laptop dưới 20 triệu rồi so sánh CPU, RAM và giá.", 2),
    ("So sánh 2 laptop dưới 25 triệu về CPU, RAM, SSD, màn hình và giá.", 2),
    ("Hãy chọn 2 mẫu laptop dưới 25 triệu rồi so sánh CPU, RAM, SSD, màn hình và giá.", 2),
    ("Chọn hai chiếc laptop dưới 25 triệu rồi so sánh CPU, RAM, SSD, màn hình và giá.", 2),
    ("So sánh CPU, RAM, SSD, màn hình và giá của 2 laptop dưới 25 triệu.", 2),
    ("Hãy chọn laptop dưới 25 triệu rồi so sánh CPU, RAM, SSD, màn hình và giá.", 2),
])
def test_select_then_compare_filters_products_and_builds_the_requested_number_of_columns(grounded_shop, question, count):
    shop = grounded_shop
    with Session(shop.engine) as db:
        db.add(Category(Name="Màn hình", Slug="man-hinh"))
        db.commit()
    service, model = shop.service([])
    response = ask(shop, service, question)
    snapshot = table(response)
    assert len(snapshot["Products"]) == count
    assert all(p["Category"] == "Laptop" for p in snapshot["Products"])
    assert all(p["InStock"] and Decimal(p["Price"]) <= 25000000 for p in snapshot["Products"])
    assert len({p["ProductId"] for p in snapshot["Products"]}) == count
    assert {"cpu", "ram", "storage", "screen"} <= {row["Key"] for row in snapshot["Rows"]}
    if "20 triệu" in question:
        assert all(Decimal(p["Price"]) <= 20000000 for p in snapshot["Products"])
    assert model.calls == []


def test_the_selected_comparison_replays_and_restores_without_selecting_again(grounded_shop):
    shop = grounded_shop
    service, model = shop.service([])
    data = AiMessageCreate(ClientRequestId=uuid.uuid4(),
                           Content="Hãy chọn 2 laptop dưới 25 triệu rồi so sánh CPU, RAM, SSD, màn hình và giá.")
    response = service.ask(shop.actor, shop.cid, data)
    assert len(table(response)["Products"]) == 2
    assert table(service.ask(shop.actor, shop.cid, data)) == table(response)
    assert table(service.get_status(shop.actor, shop.cid, data.ClientRequestId)) == table(response)
    assert model.calls == []


def test_a_new_selection_request_uses_current_constraints_instead_of_the_previous_pair(grounded_shop):
    shop = grounded_shop
    show(shop)
    service, model = shop.service([])
    response = ask(shop, service, "Hãy chọn 2 laptop dưới 20 triệu rồi so sánh CPU, RAM, SSD, màn hình và giá.")
    assert len(table(response)["Products"]) == 2
    assert all(Decimal(product["Price"]) <= 20000000 for product in table(response)["Products"])
    assert model.calls == []


def test_brand_and_ram_constraints_apply_to_the_selected_versions(grounded_shop):
    service, model = grounded_shop.service([])
    response = ask(grounded_shop, service, "Chọn 2 laptop chỉ ASUS RAM từ 16GB dưới 25 triệu rồi so sánh CPU, RAM và giá.")
    products = table(response)["Products"]
    assert len(products) == 2
    assert all(p["Brand"] == "ASUS" for p in products)
    assert all("16" in row for row in next(r["Values"] for r in table(response)["Rows"] if r["Key"] == "ram"))
    assert model.calls == []


@pytest.mark.parametrize("budget,remaining", [(1, 0), (17, 1), (20, 2)])
def test_not_enough_products_is_reported_without_looser_filters_or_an_incorrect_limit_question(grounded_shop, budget, remaining):
    service, model = grounded_shop.service([])
    response = ask(grounded_shop, service, f"Chọn 2 laptop dưới {budget} triệu rồi so sánh CPU, RAM, SSD và giá.")
    message = response.AiMessages[0]
    assert "Mỗi bảng so sánh" not in message.Content
    if remaining == 2:
        assert len(table(response)["Products"]) == 2
        assert not any("mẫu yêu cầu" in note for note in table(response)["Caveats"])
    else:
        assert not (message.Metadata or {}).get("Comparison")
        assert "chưa" in message.Content.lower() or "1 mẫu" in message.Content
    assert model.calls == []


@pytest.mark.parametrize("count", [3, 4])
def test_a_request_for_more_than_two_products_asks_for_a_pair(grounded_shop, count):
    service, model = grounded_shop.service([])
    response = ask(grounded_shop, service, f"Hãy chọn {count} laptop dưới 25 triệu rồi so sánh CPU, RAM, SSD, màn hình và giá.")
    assert "đúng 2 sản phẩm" in response.AiMessages[0].Content
    assert not (response.AiMessages[0].Metadata or {}).get("Comparison")
    assert model.calls == []


def test_a_list_of_criteria_without_products_is_not_reported_as_too_many_products(grounded_shop):
    service, _ = grounded_shop.service([{"intent": "clarify", "clarification": "products"}])
    response = ask(grounded_shop, service, "So sánh CPU, RAM, SSD, màn hình và giá.")
    assert "Mỗi bảng so sánh" not in response.AiMessages[0].Content
    assert not (response.AiMessages[0].Metadata or {}).get("Comparison")


@pytest.mark.parametrize("changed", ["price", "stock"])
def test_a_selected_version_is_rechecked_against_the_search_constraints_before_showing_it(grounded_shop, changed):
    shop = grounded_shop
    context = GroundingContext("Chọn 2 laptop dưới 25 triệu rồi so sánh CPU, RAM, SSD và giá.")
    with Session(shop.engine) as db:
        tools = AiTools(db, clock=lambda: shop.now.value)
        tools.prepare(context)
        assert context.comparison is not None
        vid = uuid.UUID(context.comparison["Products"][0]["ProductVariantId"])
        variant = db.get(ProductVariant, vid)
        if changed == "price":
            variant.Price = 30000000
        else:
            variant.StockQuantity = 0
        db.commit()
        db.expire_all()
        decision = PresentAnswerArguments(intent="compare", products=[
            {"product_id": ref["ProductId"], "product_variant_id": ref["ProductVariantId"]}
            for ref in context.intent.references])
        _, _, _, notes = tools.finish(decision, context, 5)
        assert not notes.get("Comparison")
        assert context.intent.clarification
