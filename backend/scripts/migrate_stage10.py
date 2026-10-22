"""Preflight, isolated PostgreSQL validation and transactional Stage 10 migration.

Uses the same configured database as the backend. Never prints its URL or user content.
An apply requires a matching preflight report and the unchanged revision/fingerprint.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import uuid

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.env import database_url
from app.models import Base

INDEXES = ("UX_Messages_AiRequest", "UX_Messages_AiReply", "UX_Messages_AiPending")
ALLOWED = {"a6d2e8f4b190", "b2f8c6d4e901", "c3a9f5e7d206", "d7a1e5c9b304"}
TABLES = ("Users", "Conversations", "Messages", "Categories", "Brands", "PurchaseOrders", "PurchaseOrderItems", "PurchaseReceipts", "PurchaseReceiptItems")


def configuration():
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return config


def fingerprint(engine):
    url = engine.url
    return hashlib.sha256(json.dumps([url.host, url.port, url.database, url.username]).encode()).hexdigest()


def snapshot(connection, engine):
    revisions = list(connection.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num")).scalars())
    indexes = connection.execute(text("""SELECT indexname, indexdef FROM pg_indexes
        WHERE schemaname = current_schema() AND tablename = 'Messages'
        AND indexname IN ('UX_Messages_AiRequest','UX_Messages_AiReply','UX_Messages_AiPending')""")).all()
    duplicates = {}
    for name, key, sender, pending in (
        (INDEXES[0], "ClientRequestId", "Customer", False),
        (INDEXES[1], "ReplyToMessageId", "AI", False),
        (INDEXES[2], "AiProcessingStatus", "Customer", True),
    ):
        condition = '"Metadata" ->> :key = \'Pending\'' if pending else '"Metadata" ->> :key IS NOT NULL'
        group = '"ConversationId"' if pending else '"ConversationId", "Metadata" ->> :key'
        query = f'SELECT count(*) FROM (SELECT 1 FROM "Messages" WHERE "SenderType" = :sender AND {condition} GROUP BY {group} HAVING count(*) > 1) duplicates'
        duplicates[name] = connection.scalar(text(query), {"key": key, "sender": sender})
    quote = connection.dialect.identifier_preparer.quote
    counts = {table: connection.scalar(text(f"SELECT count(*) FROM {quote(table)}")) for table in TABLES}
    schema = inspect(connection)
    return {"fingerprint": fingerprint(engine), "revisions": revisions, "ai_indexes": dict(indexes),
            "duplicates": duplicates, "row_counts": counts,
            "catalog_soft_delete": {table: any(c["name"] == "IsDeleted" for c in schema.get_columns(table)) for table in ("Categories", "Brands")},
            "receipt_foreign_keys": {table: [{"name": key["name"], "ondelete": key.get("options", {}).get("ondelete")} for key in schema.get_foreign_keys(table)] for table in ("PurchaseReceipts", "PurchaseReceiptItems")}}


def isolated_validation(engine):
    """All scratch DDL/data is rolled back; no published catalog/receipt migration is executed here."""
    schema = "codex_ai_stage10_" + uuid.uuid4().hex
    config = configuration()
    script = ScriptDirectory.from_config(config)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text('SET LOCAL statement_timeout = \'30s\''))
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            connection.execute(text('CREATE TABLE "Messages" ("MessageId" uuid PRIMARY KEY, "ConversationId" uuid NOT NULL, "SenderType" varchar(20), "Metadata" jsonb)'))
            context = MigrationContext.configure(connection, opts={"target_metadata": Base.metadata})
            with Operations.context(context):
                for revision in ("d7a1e5c9b304",):
                    spec = importlib.util.spec_from_file_location("stage10_" + revision, script.get_revision(revision).path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    module.upgrade()
            def insert(conversation, sender, metadata):
                connection.execute(text('INSERT INTO "Messages" VALUES (CAST(:id AS uuid), CAST(:cid AS uuid), :sender, CAST(:metadata AS jsonb))'),
                                   {"id": str(uuid.uuid4()), "cid": conversation, "sender": sender, "metadata": json.dumps(metadata)})
            def rejected(action, expected):
                try:
                    with connection.begin_nested():
                        action()
                except IntegrityError as failure:
                    if failure.orig.diag.constraint_name != expected:
                        raise
                else:
                    raise RuntimeError("Constraint did not reject duplicate: " + expected)
            cid, request_id = str(uuid.uuid4()), str(uuid.uuid4())
            insert(cid, "Customer", {"ClientRequestId": request_id, "AiProcessingStatus": "Completed"})
            rejected(lambda: insert(cid, "Customer", {"ClientRequestId": request_id}), INDEXES[0])
            insert(cid, "AI", {"ReplyToMessageId": request_id})
            rejected(lambda: insert(cid, "AI", {"ReplyToMessageId": request_id}), INDEXES[1])
            insert(cid, "Customer", {"ClientRequestId": str(uuid.uuid4()), "AiProcessingStatus": "Pending"})
            rejected(lambda: insert(cid, "Customer", {"ClientRequestId": str(uuid.uuid4()), "AiProcessingStatus": "Pending"}), INDEXES[2])
            print("Isolated PostgreSQL migration and 3 idempotency constraints: PASS")
        finally:
            transaction.rollback()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--validate-isolated", action="store_true")
    args = parser.parse_args()
    report = Path(args.report).resolve()
    if not report.is_relative_to(ROOT / "output"):
        raise RuntimeError("The report must be inside this workspace's output directory")
    engine = create_engine(database_url(), connect_args={"connect_timeout": 5}, echo=False)
    try:
        if args.validate_isolated:
            isolated_validation(engine)
        if not args.apply:
            with engine.connect() as connection:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                before = snapshot(connection, engine)
                script = ScriptDirectory.from_config(configuration())
                before["planned_revisions"] = [step.revision.revision for step in script._upgrade_revs("heads", before["revisions"])]
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(before, indent=2), encoding="utf-8")
            print(json.dumps({key: before[key] for key in ("revisions", "planned_revisions", "duplicates")}, indent=2))
            return
        reviewed = json.loads(report.read_text(encoding="utf-8"))
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '60s'"))
            if not connection.scalar(text("SELECT pg_try_advisory_xact_lock(170105)")):
                raise RuntimeError("Another Stage 10 migration is running")
            before = snapshot(connection, engine)
            if before["fingerprint"] != reviewed["fingerprint"] or before["revisions"] != reviewed["revisions"]:
                raise RuntimeError("Database or revision changed since preflight")
            if any(before["duplicates"].values()):
                raise RuntimeError("Existing duplicate AI metadata must be investigated first")
            config = configuration()
            script = ScriptDirectory.from_config(config)
            plan = [step.revision.revision for step in script._upgrade_revs("heads", before["revisions"])]
            if not set(plan).issubset(ALLOWED) or plan != reviewed["planned_revisions"]:
                raise RuntimeError("Migration plan changed or includes an unreviewed revision")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            after = snapshot(connection, engine)
            if set(after["ai_indexes"]) != set(INDEXES):
                raise RuntimeError("Missing Stage 10 schema after upgrade")
            if before["row_counts"] != after["row_counts"]:
                raise RuntimeError("Data counts changed during schema migration; transaction rolled back")
        report.with_name(report.stem + "-applied.json").write_text(json.dumps({"before": before, "after": after}, indent=2), encoding="utf-8")
        print(json.dumps({"applied_revisions": plan, "current_revisions": after["revisions"], "ai_indexes": list(after["ai_indexes"]), "existing_data_counts_unchanged": True}, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as failure:
        original = getattr(failure, "orig", None)
        print(json.dumps({"error": type(failure).__name__, "sqlstate": getattr(original, "sqlstate", None),
                          "constraint": getattr(getattr(original, "diag", None), "constraint_name", None),
                          "reason": str(failure) if isinstance(failure, RuntimeError) else "No schema changes committed on failure."}))
        sys.exit(1)
