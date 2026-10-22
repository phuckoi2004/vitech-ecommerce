"""Read current schema, or apply ONLY the exchange-order migration from its exact parent.

Run with the backend Python environment. Never prints connection strings or customer records.
"""
import argparse
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, inspect, select, text
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
import importlib.util
from app.core.env import database_url
from app.models import PaymentMethod, ShippingMethod

parser = argparse.ArgumentParser()
parser.add_argument("--apply", action="store_true")
parser.add_argument("--locks", action="store_true")
args = parser.parse_args()
engine = create_engine(database_url(), connect_args={"connect_timeout": 10})
try:
    with engine.connect() as connection:
        revisions = connection.execute(text("select version_num from alembic_version")).scalars().all()
        print("Database revision:", revisions)
        print("Shipping methods:", connection.execute(select(ShippingMethod.Code, ShippingMethod.Name, ShippingMethod.IsActive)).all())
        print("Payment methods:", connection.execute(select(PaymentMethod.Code, PaymentMethod.IsActive)).all())
        columns = {column["name"] for column in inspect(connection).get_columns("Orders")}
        print("Exchange columns:", sorted(columns & {"SourceReturnRequestId", "ExchangeCreditAmount"}))
        print("Return completion checks:", [c for c in inspect(connection).get_check_constraints("ReturnRequests")
                                            if "Complet" in c["name"] or "Quantity" in c["name"]])
        if args.locks:
            print("Table locks (no query texts or credentials):", connection.execute(text('''
                SELECT l.pid, l.mode, l.granted, a.state,
                       EXTRACT(epoch FROM now() - a.xact_start)::integer AS transaction_seconds,
                       c.relname
                FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid
                JOIN pg_class c ON c.oid = l.relation
                WHERE c.relname IN ('Orders', 'ReturnRequests') AND l.pid <> pg_backend_pid()
                ORDER BY a.xact_start
            ''')).all())
    if args.apply:
        if revisions == ["e6a2c9d4b810"]:
            print("Exchange migration already applied; nothing written.")
        elif revisions == ["c3a9f5e7d206"]:
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            command.upgrade(config, "e6a2c9d4b810")
            print("Applied exchange migration e6a2c9d4b810.")
        elif revisions == ["d7a1e5c9b304"]:
            # This shared database has an external migration absent from this checkout.
            # Apply only the inspected exchange DDL, in one transaction; never fabricate/stamp its history.
            path = Path(__file__).resolve().parents[1] / "alembic/versions/e6a2c9d4b810_exchange_orders.py"
            spec = importlib.util.spec_from_file_location("exchange_migration", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with engine.begin() as connection:
                ctx = MigrationContext.configure(connection)
                with Operations.context(ctx):
                    module.upgrade()
                assert module.installed(connection)
                assert connection.execute(text("select version_num from alembic_version")).scalars().all() == revisions
            print("Exchange schema verified/applied; external revision d7a1e5c9b304 preserved (no stamp).")
        else:
            raise RuntimeError("Unexpected parent revision; refusing to apply unrelated migrations")
except Exception as error:
    print("Database inspection/application failed:", type(error).__name__)
    original = getattr(error, "orig", None)
    diagnostic = getattr(original, "diag", None)
    if diagnostic and getattr(original, "sqlstate", None):
        print("SQLSTATE:", original.sqlstate, "Database message:", diagnostic.message_primary)
    sys.exit(1)
finally:
    engine.dispose()
