"""Read-only audit of pending same-SKU exchange orders; prints no customer or connection data."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from app.core.env import database_url
from app.models import Order, OrderItem, ReturnRequest, PaymentTransaction


engine = create_engine(database_url(), connect_args={"connect_timeout": 10})
try:
    with Session(engine) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        session.execute(text("SET LOCAL statement_timeout = '10s'"))
        orders = session.scalars(select(Order).where(
            Order.SourceReturnRequestId.is_not(None), Order.OrderStatus == "Pending",
            Order.PaymentStatus.in_(("Pending", "Failed"))))
        count = 0
        for order in orders:
            request = session.get(ReturnRequest, order.SourceReturnRequestId)
            original = session.get(OrderItem, request.OrderItemId) if request else None
            items = list(session.scalars(select(OrderItem).where(OrderItem.OrderId == order.OrderId)))
            if not original or len(items) != 1 or items[0].Quantity != 1 or items[0].ProductVariantId != original.ProductVariantId:
                continue
            transactions = list(session.scalars(select(PaymentTransaction).where(PaymentTransaction.OrderId == order.OrderId)))
            print({"OrderId": str(order.OrderId), "OrderCode": order.OrderCode,
                   "RequestCode": request.RequestCode, "RequestStatus": request.Status,
                   "TotalAmount": str(order.TotalAmount), "PaymentStatus": order.PaymentStatus,
                   "PaymentTransactions": [{"Type": t.TransactionType, "Status": t.Status, "Amount": str(t.Amount)} for t in transactions]})
            count += 1
        print("Same-SKU unpaid orders:", count, "(read-only; no data changed)")
except Exception as error:
    print("Inspection failed:", type(error).__name__)
    original = getattr(error, "orig", None)
    if getattr(original, "sqlstate", None):
        print("SQLSTATE:", original.sqlstate)
    sys.exit(1)
finally:
    engine.dispose()
