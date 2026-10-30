"""Phase A only: SELECT a live catalog snapshot, then audit values offline. No apply/write mode."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def capture():
    from sqlalchemy import create_engine, func, select, text
    from sqlalchemy.orm import Session
    from app.core.env import database_url
    from app.models import Brand, Category, Product, ProductImage, ProductVariant
    # Reuse the existing catalog inventory serializer, without its apply/import workflow.
    from enrich_sample_catalog import fingerprint

    models = (Product, ProductVariant, Category, Brand, ProductImage)
    engine = create_engine(database_url(), connect_args={"connect_timeout": 12})
    try:
        with Session(engine, autoflush=False) as db:
            db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            db.execute(text("SET LOCAL statement_timeout = '20s'"))
            readonly = db.scalar(text("SELECT current_setting('transaction_read_only')"))
            if readonly != "on":
                raise RuntimeError("Read-only transaction was not established")
            counts = {model.__tablename__: db.scalar(select(func.count()).select_from(model)) for model in models}
            columns = [dict(row) for row in db.execute(text("""
                SELECT table_name, column_name, ordinal_position, data_type, udt_name, is_nullable
                FROM information_schema.columns WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
            """)).mappings()]
            constraints = [dict(row) for row in db.execute(text("""
                SELECT c.relname AS table_name, con.conname, pg_get_constraintdef(con.oid) AS definition
                FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
                ORDER BY c.relname, con.conname
            """)).mappings()]
            tables = {model.__tablename__: [fingerprint(row) for row in db.scalars(
                select(model).order_by(model.__mapper__.primary_key[0]))] for model in models}
            # Cost is invariant-checked in memory; business-sensitive values are never exported.
            cost_hash = digest([(row['ProductVariantId'], row.pop('CostPrice')) for row in tables['ProductVariants']])
            result = {
                "CapturedAt": datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(),
                "Source": "configured_postgresql_live_select", "ReadOnly": True,
                "Counts": counts, "SchemaFingerprint": digest([columns, constraints]),
                "ProtectedCostFingerprint": cost_hash, "Tables": tables,
            }
            result["CatalogFingerprint"] = digest(tables)
            db.rollback()
            return result
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='store_true', help='SELECT current configured PostgreSQL in READ ONLY mode')
    parser.add_argument('--input', type=Path, help='Offline original snapshot, never an import manifest')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/catalog-standardization')
    parser.add_argument('--evidence', type=Path, help='Reviewed evidence for existing exact JSON paths')
    parser.add_argument('--verify-live', action='store_true', help='SELECT again and compare fingerprints, never update')
    parser.add_argument('--validate-consumers', action='store_true', help='Check public schemas and all current AI readers offline')
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if args.capture == bool(args.input):
        parser.error('Choose exactly one of --capture or --input')
    if args.capture:
        if (folder / 'catalog-original.json').exists():
            parser.error('Original snapshot already exists; use --input or a new output directory')
        try:
            original = capture()
        except Exception as error:
            # Connection errors may contain credentials; never print exception text/traceback.
            print('Catalog SELECT failed:', type(error).__name__)
            code = getattr(getattr(error, 'orig', None), 'sqlstate', None)
            if code:
                print('SQLSTATE:', code)
            return 1
        (folder / 'catalog-original.json').write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'Counts': original['Counts'], 'ReadOnly': original['ReadOnly']}, ensure_ascii=False))
    else:
        original = json.loads(args.input.read_text(encoding='utf-8'))
    from catalog_standardization import audit, csv_write, source_candidates, write_reports
    evidence = json.loads(args.evidence.read_text(encoding='utf-8')) if args.evidence else {'Values': []}
    result = audit(original, evidence)
    write_reports(folder, original, result)
    candidates = source_candidates(original, evidence, BACKEND / 'data/sample-catalog-2026-10-17.json')
    csv_write(folder / 'catalog-source-candidates.csv', candidates, list(candidates[0]) if candidates else [])
    if evidence.get('Sources'):
        csv_write(folder / 'catalog-source-register.csv', evidence['Sources'], list(evidence['Sources'][0]))
    if args.validate_consumers:
        from catalog_standardization import validate_consumers
        consumer_checks = validate_consumers(original, result)
        (folder / 'catalog-ai-validation.json').write_text(json.dumps(consumer_checks, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result['summary'], ensure_ascii=False))
    if args.verify_live:
        try:
            current = capture()
        except Exception as error:
            print('Live verification SELECT failed:', type(error).__name__)
            return 1
        verification = {'CheckedAt': current['CapturedAt'], 'ReadOnly': current['ReadOnly'],
                        'Counts': current['Counts'], 'SameCounts': current['Counts'] == original['Counts'],
                        'SameSchema': current['SchemaFingerprint'] == original['SchemaFingerprint'],
                        'SameCatalog': current['CatalogFingerprint'] == original['CatalogFingerprint'],
                        'SameProtectedCost': current['ProtectedCostFingerprint'] == original['ProtectedCostFingerprint']}
        (folder / 'catalog-live-verification.json').write_text(json.dumps(verification, indent=2), encoding='utf-8')
        print(json.dumps(verification))
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
