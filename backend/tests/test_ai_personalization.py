"""Catalog-based advice is detached from personalization: wishlist and delivered orders never shape an AI turn.

The stage 10.5 repository (repositories/ai_personalization.py) is kept for other uses and still tested here, but the AI
turn neither reads it nor sends it to the model, and the same request ranks the same way for every customer.
Isolated SQLite, scripted model; no Gemini calls.
"""

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.ai_config import AiSettings
from app.core.auth_state import MemoryStateStore
from app.models import (Brand, Category, Conversation, Order, OrderItem, Product, ProductVariant, User, Wishlist,
                        WishlistItem)
from app.repositories.ai_personalization import AiPersonalizationRepository
from app.schemas.ai_chat import AiMessageCreate
from app.services.actor import Actor
from app.services.ai_chat import SYSTEM_PROMPT, AiChatService
from tests.sqlite_schema import AI_SIGNAL_TABLES, create_tables
from tests.test_ai_grounded import ScriptedModel, call, finish

TABLES = ("Users", "Conversations", "Messages", "ProductImages", "Promotions", "PromotionCategories",
          "PromotionProducts", "Coupons", *AI_SIGNAL_TABLES)


def sqlite_functions(connection, _):
    connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat(" "))
    connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)
    connection.create_function("lower", 1, lambda value: value.lower() if value else value, deterministic=True)
    connection.create_function("translate", 3, lambda value, source, target:
                               value.translate(str.maketrans(source, target)) if value else value, deterministic=True)


def add_order(db, customer_id, variant, status):
    order = Order(OrderCode=f"ORDER-SECRET-{uuid.uuid4().hex[:6]}", CustomerId=customer_id,
                  ShippingMethodId=uuid.uuid4(), PaymentMethodId=uuid.uuid4(), Subtotal=variant.Price,
                  DiscountAmount=0, TotalAmount=variant.Price, OrderStatus=status, PaymentStatus="Paid",
                  ReceiverName="Receiver Secret", ReceiverPhone="0987654321", ShippingAddress="12 Secret Street")
    db.add(order); db.flush()
    db.add(OrderItem(OrderId=order.OrderId, ProductVariantId=variant.ProductVariantId, ProductName="Order line",
                     Sku=variant.Sku, VariantInfo=variant.VariantName, WarrantyMonths=24, Quantity=1,
                     UnitPrice=variant.Price, DiscountAmount=0, LineTotal=variant.Price))


def add_wishlist(db, user_id, product_id):
    wishlist = db.query(Wishlist).filter_by(UserId=user_id).one_or_none()
    if wishlist is None:
        wishlist = Wishlist(UserId=user_id)
        db.add(wishlist); db.flush()
    db.add(WishlistItem(WishlistId=wishlist.WishlistId, ProductId=uuid.UUID(product_id)))


@pytest.fixture
def shop():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", sqlite_functions)
    counters = {"connections": 0}
    event.listen(engine, "checkout", lambda *_: counters.update(connections=counters["connections"] + 1))
    event.listen(engine, "checkin", lambda *_: counters.update(connections=counters["connections"] - 1))
    create_tables(engine, TABLES)
    now = datetime(2026, 10, 22, 8, tzinfo=timezone.utc)
    with Session(engine) as db:
        owner = User(Email="private-profile@example.test", PhoneNumber="0912345678", PasswordHash="private-password",
                     FullName="Private Customer Name", Role="Customer", AccountStatus="Active")
        newcomer = User(Email="new@example.test", PhoneNumber="0911111111", PasswordHash="new-password",
                        FullName="New Customer", Role="Customer", AccountStatus="Active")
        laptop = Category(Name="Laptop", Slug="laptop")
        brands = {name: Brand(Name=name, Slug=name.lower()) for name in ("ASUS", "Lenovo", "Dell", "HP")}
        db.add_all([owner, newcomer, laptop, *brands.values()]); db.flush()
        conversations = {}
        for user in (owner, newcomer):
            conversations[user.UserId] = uuid.uuid4()
            db.add(Conversation(ConversationId=conversations[user.UserId], CustomerId=user.UserId, Mode="AI",
                                Status="Open"))
        products, variants = {}, {}
        for name, brand, price, ram in [("asus-zen", "ASUS", 18000000, "16 GB"), ("asus-vivo", "ASUS", 21000000, "8 GB"),
                                        ("lenovo-idea", "Lenovo", 17000000, "16 GB"),
                                        ("dell-inspiron", "Dell", 16000000, "8 GB"), ("hp-pavilion", "HP", 15000000, "8 GB")]:
            product = Product(Name=name, Slug=name, BrandId=brands[brand].BrandId, CategoryId=laptop.CategoryId,
                              Status="Active", WarrantyMonths=24, Specifications={"Dung lượng RAM": ram})
            db.add(product); db.flush()
            variants[name] = ProductVariant(ProductId=product.ProductId, Sku=name, VariantName="Bản tiêu chuẩn",
                                            Price=price, CostPrice=price // 2, StockQuantity=5)
            db.add(variants[name]); db.flush()
            products[name] = str(product.ProductId)
        add_wishlist(db, owner.UserId, products["asus-vivo"])
        add_order(db, owner.UserId, variants["dell-inspiron"], "Delivered")
        add_order(db, owner.UserId, variants["hp-pavilion"], "Pending")  # Not a purchase until delivered.
        owner_actor, newcomer_actor = Actor(owner.UserId, "Customer"), Actor(newcomer.UserId, "Customer")
        db.commit()
    state = MemoryStateStore()
    sessions = []

    def service(steps):
        session = Session(engine, autoflush=False)
        sessions.append(session)
        model = ScriptedModel(steps, counters)
        return AiChatService(session, settings=AiSettings(api_key="test"), model=model, state=state,
                             clock=lambda: now), model

    yield SimpleNamespace(engine=engine, owner=owner_actor, newcomer=newcomer_actor, conversations=conversations,
                          products=products, service=service)
    for session in sessions:
        session.close()
    engine.dispose()


def ask(shop, svc, actor, content):
    return svc.ask(actor, shop.conversations[actor.user_id],
                   AiMessageCreate(ClientRequestId=uuid.uuid4(), Content=content))


def search_ids(messages):
    return [p["ProductId"] for p in json.loads(messages[-1]["content"])["Products"]]


def test_the_same_request_ranks_the_same_for_a_returning_and_a_new_customer(shop):
    orders = {}

    def record(actor):
        def choose(messages):
            orders[actor.user_id] = search_ids(messages)
            return finish("recommend", orders[actor.user_id][0])
        return choose

    for actor in (shop.owner, shop.newcomer):
        svc, model = shop.service([[call("search_products", category="laptop")], record(actor)])
        response = ask(shop, svc, actor, "Tư vấn laptop dưới 30 triệu")
        assert response.Status == "Completed" and response.AiMessages[1].MessageType == "Product"
        # Everything sent except the fixed instructions (which only say not to use such reasons).
        sent = json.dumps([m["content"].replace(SYSTEM_PROMPT, "") if m["role"] == "system" else m
                           for messages, _ in model.calls for m in messages], ensure_ascii=False)
        # Neither the wishlist, the orders nor any profile detail reaches the model.
        for private in ("Wishlist", "Purchases", "yêu thích", "đã mua", "private-profile", "0912345678",
                        "Private Customer Name", "Receiver Secret", "0987654321", "Secret Street", "ORDER-SECRET"):
            assert private not in sent
        assert "yêu thích" not in response.AiMessages[0].Content and "đã mua" not in response.AiMessages[0].Content
    assert orders[shop.owner.user_id] == orders[shop.newcomer.user_id]
    # 16 GB first (balanced laptop profile), then budget: the wishlisted 8 GB ASUS gets no boost.
    assert orders[shop.owner.user_id][:2] == [shop.products["lenovo-idea"], shop.products["asus-zen"]]


def test_a_new_customer_without_wishlist_cart_or_orders_gets_full_advice(shop):
    def choose(messages):
        ids = search_ids(messages)
        assert len(ids) == 5 and json.loads(messages[-1]["content"])["Ranked"] is True
        return finish("recommend", *ids[:3])

    svc, _ = shop.service([[call("search_products", category="laptop")], choose])
    response = ask(shop, svc, shop.newcomer, "Laptop dưới 30 triệu")
    assert [m.MessageType for m in response.AiMessages] == ["Text", "Product", "Product", "Product"]
    assert "Phù hợp:" in response.AiMessages[0].Content


def test_the_detached_repository_still_reads_signals_for_other_uses(shop):
    with Session(shop.engine) as db:
        signals = AiPersonalizationRepository(db)
        assert [hint["Brand"] for hint in signals.interests(shop.owner.user_id, "wishlist")] == ["ASUS"]
        assert [hint["Brand"] for hint in signals.interests(shop.owner.user_id, "purchases")] == ["Dell"]
        assert signals.purchased_product_ids(shop.owner.user_id) == [shop.products["dell-inspiron"]]
        assert signals.interests(shop.newcomer.user_id, "wishlist") == []
        db.get(Product, uuid.UUID(shop.products["asus-vivo"])).IsDeleted = True
        db.query(Brand).filter_by(Name="Dell").one().IsActive = False
        db.flush()
        assert signals.interests(shop.owner.user_id, "wishlist") == []  # Hidden products/brands are never signals.
        assert signals.interests(shop.owner.user_id, "purchases") == []
