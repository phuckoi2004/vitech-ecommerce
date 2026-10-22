"""Create part of the real schema in an isolated SQLite engine for tests.

Every table is copied so foreign keys resolve; only the named tables are created (existing ones are kept).
"""
from sqlalchemy import JSON, MetaData
from sqlalchemy.dialects.postgresql import JSONB

from app.models import Base

# Tables an AI turn reads for automatic personalization (stage 10.5).
AI_SIGNAL_TABLES = ("Brands", "Categories", "Products", "ProductVariants", "Wishlists", "WishlistItems", "Orders",
                    "OrderItems")


def create_tables(engine, names):
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        for column in table.to_metadata(metadata).c:
            if isinstance(column.type, JSONB):
                column.type = JSON()
    metadata.create_all(engine, tables=[metadata.tables[name] for name in names])
