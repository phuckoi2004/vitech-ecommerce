"""Real SQL repositories on isolated SQLite; never connects to the configured database."""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification, User
from app.repositories.order import OrderRepository
from app.repositories.user import NotificationRepository
from tests.test_content_atomic import content  # isolated engine fixture, including UUID/time functions


def seed_orders(context, *, lines_by_customer=None):
    factory = context['factory']
    first = context['customer']
    first.FullName, first.PhoneNumber = 'An Nguyen', '0981234567'
    second = factory.user()
    second.FullName, second.PhoneNumber = 'Long Tran', '0909812345'
    third = factory.user()
    third.FullName, third.PhoneNumber = 'Literal %_ name', '0712345678'
    method = factory.payment_method('COD')
    lines_by_customer = lines_by_customer or ((), (), ())
    orders = [factory.order(user, method, lines=lines)
              for user, lines in zip((first, second, third), lines_by_customer)]
    with context['engine'].begin() as connection:
        connection.execute(User.__table__.update().where(User.UserId == first.UserId).values(
            FullName=first.FullName, PhoneNumber=first.PhoneNumber))
        for model, objects in factory.db.tables.items():
            for obj in objects.values():
                if model is User and obj.UserId not in (second.UserId, third.UserId): continue
                connection.execute(model.__table__.insert().values(
                    **{column.key: getattr(obj, column.key) for column in model.__table__.columns}))
    return orders


def test_search_matches_literal_contiguous_substrings_of_account_name_and_phone(content):
    first, second, third = seed_orders(content)
    with Session(content['engine']) as session:
        repo = OrderRepository(session)
        expected = {'0': {first.OrderId, second.OrderId, third.OrderId},
                    '098': {first.OrderId, second.OrderId}, '0981': {first.OrderId, second.OrderId},
                    '0982': set(), 'AN NG': {first.OrderId}, '%_': {third.OrderId},
                    first.OrderCode: {first.OrderId}}
        for text, ids in expected.items():
            assert {o.OrderId for o in repo.list_orders(keyword=text)} == ids
            assert repo.count_orders(keyword=text) == len(ids)
        rows = repo.list_orders(keyword='0', offset=1, limit=1)
        assert len(rows) == 1 and repo.count_orders(keyword='0') == 3
        assert repo.count_orders(keyword='098', customer_id=third.CustomerId) == 0
        assert repo.count_orders(keyword='098', order_status='Shipping') == 0


def test_account_search_and_product_history_filters_combine_with_the_same_count(content):
    phone, case = content['factory'].variant(), content['factory'].variant()
    first, _, third = seed_orders(content, lines_by_customer=(
        ((phone, 1), (case, 1)), ((case, 1),), ((phone, 1),)))
    filters = dict(keyword='098', product_id=phone.ProductId, order_status=['Pending', 'Processing'])
    with Session(content['engine']) as session:
        repo = OrderRepository(session)
        rows = repo.list_orders(**filters, offset=0, limit=1, with_items=True)
        assert [order.OrderId for order in rows] == [first.OrderId]
        assert repo.count_orders(**filters) == 1
        assert repo.list_orders(**filters, offset=1, limit=1) == []
        assert repo.count_orders(**filters, customer_id=third.CustomerId) == 0
    # The customer's history has its products and review references loaded after the session closes.
    assert {item.product_variant.product.ProductId for item in rows[0].items} == {phone.ProductId, case.ProductId}
    assert all(item.review is None for item in rows[0].items)


def test_shared_resolution_updates_only_new_order_alerts_without_deleting_history(content):
    first, second, _ = seed_orders(content)
    now = datetime(2026, 10, 21, tzinfo=timezone.utc)
    ids = []
    with Session(content['engine']) as session:
        for order, kind, user in ((first, 'NewOrder', content['staff']),
                                  (first, 'NewOrder', content['customer']),
                                  (first, 'Order', content['staff']),
                                  (second, 'NewOrder', content['staff'])):
            row = Notification(UserId=user.UserId, Title='Test', Content='Test', NotificationType=kind,
                               ReferenceType='Order', ReferenceId=order.OrderId)
            session.add(row); session.flush(); ids.append(row.NotificationId)
        session.commit()
        NotificationRepository(session).resolve_new_order(first.OrderId, now)
        session.commit()
    with Session(content['engine']) as session:
        rows = {n.NotificationId: n for n in session.scalars(select(Notification))}
        assert len(rows) == 4
        assert [rows[id].IsRead for id in ids] == [True, True, False, False]
