"""Phase B: freeze the reviewed proposal, apply existing values atomically, or undo this run.

No DDL, imports, provider calls, or writes outside Products.Specifications. The existing
Products trigger owns UpdatedAt. Rollback refuses rows edited after this run.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
BACKEND = SCRIPTS.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(SCRIPTS))

from audit_catalog_specs import capture, digest
from catalog_standardization import validate_consumers, validate_evidence, validate_proposal, validate_snapshot


class GuardError(ValueError):
    """A safe, credential-free reason to stop before committing."""


def now():
    return datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path, value, *, replace=False):
    """Flush recovery files before mutation; never overwrite an earlier backup."""
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    target = path.with_name(path.name + '.pending') if replace else path
    with target.open('wb' if replace else 'xb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    if replace:
        os.replace(target, path)


def checked(condition, message):
    if not condition:
        raise GuardError(message)


def reviewed(inputs):
    original = json.loads(inputs['catalog-original.json'].decode('utf-8-sig'))
    proposed = json.loads(inputs['catalog-cleaned.json'].decode('utf-8-sig'))
    evidence = json.loads(inputs['evidence.json'].decode('utf-8-sig'))
    changes = list(csv.DictReader(io.StringIO(inputs['catalog-changes.csv'].decode('utf-8-sig'))))
    for row in changes:
        row['Before'], row['Proposed'] = json.loads(row['Before']), json.loads(row['Proposed'])
    validate_snapshot(original)
    validate_snapshot(proposed)
    validate_proposal(original, proposed, changes)
    checked(bool(changes), 'The reviewed list is empty')
    checked(evidence.get('SnapshotFingerprint') == original['CatalogFingerprint'], 'Evidence snapshot mismatch')
    by_product = {p['ProductId']: p for p in original['Tables']['Products']}
    evidence_rows = evidence.get('Values', [])
    sources = {(v['ProductId'], v['Path']): v for v in evidence_rows}
    checked(len(sources) == len(evidence_rows), 'Duplicate evidence path')
    corrections = [c for c in changes if c['Classification'] == 'verified_correction']
    checked({(c['ProductId'], c['Path']) for c in corrections}
            == {key for key, row in sources.items() if row['Decision'] == 'correction'},
            'The reviewed corrections and evidence disagree')
    for change in corrections:
        item = sources[(change['ProductId'], change['Path'])]
        # The Phase A walker generates canonical paths, including escaped / and ~.
        path = tuple(part.replace('~1', '/').replace('~0', '~') for part in change['Path'][1:].split('/'))
        validate_evidence(item, by_product[change['ProductId']], path, change['Before'])
        checked(item['Proposed'] == change['Proposed'] and item['SourceURL'] == change['SourceURL'],
                'A correction differs from its reviewed evidence')
    return original, proposed, changes


def target_identity():
    from sqlalchemy.engine import make_url
    from app.core.env import database_url

    url = make_url(database_url())
    checked(url.get_backend_name() == 'postgresql', 'Phase B requires PostgreSQL')
    identity = {'host': (url.host or '').lower(), 'port': url.port or 5432,
                'database': url.database, 'role': url.username}
    return {'Fingerprint': digest(identity),
            'Provider': 'supabase' if 'supabase' in identity['host'] else 'postgresql'}


def records_for(original, proposed, changes, current):
    """Conservative preflight: any newer edit to a targeted product aborts the whole run."""
    checked(current['SchemaFingerprint'] == original['SchemaFingerprint'], 'The live schema differs from the reviewed schema')
    old = {p['ProductId']: p for p in original['Tables']['Products']}
    new = {p['ProductId']: p for p in proposed['Tables']['Products']}
    live = {p['ProductId']: p for p in current['Tables']['Products']}
    ids = sorted({c['ProductId'] for c in changes})
    checked(set(ids) <= set(live), 'A targeted product no longer exists')
    if all(live[pid]['Specifications'] == new[pid]['Specifications'] for pid in ids):
        # An earlier run already applied the entire list: no UPDATE and no timestamp bump.
        for pid in ids:
            checked({k: v for k, v in live[pid].items() if k not in ('Specifications', 'UpdatedAt')}
                    == {k: v for k, v in old[pid].items() if k not in ('Specifications', 'UpdatedAt')},
                    'An already-applied product has changed identity or protected fields')
        return []
    for pid in ids:
        checked(live[pid] == old[pid], 'A targeted product was edited after the reviewed snapshot; nothing was written')
    before_variants = {(v['ProductVariantId'], v['ProductId'], v['Sku'])
                       for v in original['Tables']['ProductVariants'] if v['ProductId'] in ids}
    live_variants = {(v['ProductVariantId'], v['ProductId'], v['Sku'])
                    for v in current['Tables']['ProductVariants'] if v['ProductId'] in ids}
    checked(live_variants == before_variants, 'Targeted SKU identities have changed')
    return [{'ProductId': pid, 'BeforeRow': copy.deepcopy(live[pid]),
             'AfterSpecs': copy.deepcopy(new[pid]['Specifications'])} for pid in ids]


def load_run(folder):
    manifest = read_json(folder / 'manifest.json')
    checked(manifest.get('Version') == 1, 'Unknown Phase B manifest version')
    expected_names = {'catalog-original.json', 'catalog-cleaned.json', 'catalog-changes.csv', 'evidence.json'}
    checked(set(manifest['InputHashes']) == expected_names, 'Unexpected input files')
    inputs = {name: (folder / 'inputs' / name).read_bytes() for name in expected_names}
    checked(all(sha(data) == manifest['InputHashes'][name] for name, data in inputs.items()), 'A frozen input was modified')
    original, proposed, changes = reviewed(inputs)
    plan = read_json(folder / 'plan.json')
    checked(digest(plan) == manifest['PlanHash'], 'The prepared plan was modified')
    current = read_json(folder / 'preflight.json')
    checked(digest(current) == manifest['PreflightHash'], 'The preflight backup was modified')
    checked(plan['Records'] == records_for(original, proposed, changes, current), 'The plan differs from the frozen review')
    checked(len(changes) == manifest['ValueChanges'] and len(plan['Records']) == manifest['ProductUpdates'],
            'Manifest counts do not match the reviewed list')
    checked(target_identity() == manifest['Target'], 'The configured database target changed')
    return manifest, original, proposed, changes, plan


def prepare(source, evidence_path, output, expected_changes, expected_products):
    inputs = {name: (source / name).read_bytes()
              for name in ('catalog-original.json', 'catalog-cleaned.json', 'catalog-changes.csv')}
    inputs['evidence.json'] = evidence_path.read_bytes()
    original, proposed, changes = reviewed(inputs)
    checked(len(changes) == expected_changes, 'The reviewed change count differs from the authorized count')
    checked(len({c['ProductId'] for c in changes}) == expected_products, 'The reviewed product count differs from the authorized count')
    consumers = validate_consumers(original, {'proposed': proposed, 'changes': changes})
    target = target_identity()
    current = capture()  # READ ONLY, no locks or mutation.
    records = records_for(original, proposed, changes, current)
    folder = output / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8])
    (folder / 'inputs').mkdir(parents=True, exist_ok=False)
    for name, data in inputs.items():
        with (folder / 'inputs' / name).open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    plan = {'PreparedAt': now(), 'Records': records}
    manifest = {'Version': 1, 'Target': target, 'InputHashes': {name: sha(data) for name, data in inputs.items()},
                'PlanHash': digest(plan), 'PreflightHash': digest(current), 'ValueChanges': len(changes),
                'ProductUpdates': len(records), 'Classifications': dict(Counter(c['Classification'] for c in changes))}
    save_json(folder / 'preflight.json', current)
    save_json(folder / 'plan.json', plan)
    save_json(folder / 'consumer-validation.json', consumers)
    save_json(folder / 'manifest.json', manifest)
    save_json(folder / 'receipt.json', {'Status': 'prepared' if records else 'already_applied', 'PreparedAt': now()})
    print(json.dumps({'Status': 'prepared' if records else 'already_applied', 'RunDirectory': str(folder),
                      'ValueChanges': len(changes), 'ProductUpdates': len(records), 'Classifications': manifest['Classifications']}))
    return folder


def snapshot_in_transaction(db):
    """Same five-table inventory as Phase A, on the caller's current transaction."""
    from sqlalchemy import select, text
    from app.models import Brand, Category, Product, ProductImage, ProductVariant
    from enrich_sample_catalog import fingerprint

    columns = [dict(r) for r in db.execute(text('''
        SELECT table_name, column_name, ordinal_position, data_type, udt_name, is_nullable
        FROM information_schema.columns WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    ''')).mappings()]
    constraints = [dict(r) for r in db.execute(text('''
        SELECT c.relname AS table_name, con.conname, pg_get_constraintdef(con.oid) AS definition
        FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
        ORDER BY c.relname, con.conname
    ''')).mappings()]
    models = (Product, ProductVariant, Category, Brand, ProductImage)
    tables = {m.__tablename__: [fingerprint(row) for row in db.scalars(
        select(m).order_by(m.__mapper__.primary_key[0]).execution_options(populate_existing=True))] for m in models}
    cost_hash = digest([(r['ProductVariantId'], r.pop('CostPrice')) for r in tables['ProductVariants']])
    return {'CapturedAt': now(), 'Source': 'phase_b_transaction_select',
            'ReadOnly': db.scalar(text("SELECT current_setting('transaction_read_only')")) == 'on',
            'Counts': {name: len(rows) for name, rows in tables.items()},
            'SchemaFingerprint': digest([columns, constraints]), 'ProtectedCostFingerprint': cost_hash,
            'Tables': tables, 'CatalogFingerprint': digest(tables)}


def match_records(snapshot, records):
    live = {p['ProductId']: p for p in snapshot['Tables']['Products']}
    checked(all(live.get(r['ProductId']) == r['BeforeRow'] for r in records),
            'A targeted row changed since preparation; transaction refused')


BATCH_UPDATE = '''
    UPDATE "Products" AS p SET "Specifications" = change."After"
    FROM jsonb_to_recordset(CAST(:patches AS jsonb)) AS change(
        "ProductId" uuid, "Before" jsonb, "After" jsonb, "UpdatedAt" timestamptz)
    WHERE p."ProductId" = change."ProductId"
      AND p."Specifications" = change."Before"
      AND p."UpdatedAt" IS NOT DISTINCT FROM change."UpdatedAt"
    RETURNING p."ProductId"
'''


def patch_payload(records):
    return json.dumps([{'ProductId': r['ProductId'], 'Before': r['BeforeRow']['Specifications'],
                        'After': r['AfterSpecs'], 'UpdatedAt': r['BeforeRow']['UpdatedAt']} for r in records],
                      ensure_ascii=False)


def validate_transition(before, after, changes, records):
    """Compare every catalog field, permitting only the listed values and target timestamps."""
    for key in ('Counts', 'SchemaFingerprint', 'ProtectedCostFingerprint'):
        checked(before[key] == after[key], 'A protected catalog invariant changed: ' + key)
    expected = {r['ProductId']: r['AfterSpecs'] for r in records}
    checked(len(expected) == len(records), 'Duplicate target product')
    before_rows = {p['ProductId']: p for p in before['Tables']['Products']}
    normalized = copy.deepcopy(before)
    normalized['Tables'] = copy.deepcopy(after['Tables'])
    for row in normalized['Tables']['Products']:
        if row['ProductId'] in expected:
            checked(row['Specifications'] == expected[row['ProductId']], 'The database did not apply the exact approved values')
            previous = before_rows[row['ProductId']]['UpdatedAt']
            checked(row['UpdatedAt'] is not None and datetime.fromisoformat(row['UpdatedAt']) >= datetime.fromisoformat(previous),
                    'Unexpected timestamp behavior')
            row['UpdatedAt'] = previous
    normalized['CatalogFingerprint'] = digest(normalized['Tables'])
    validate_proposal(before, normalized, changes)
    return {'ExactApprovedValues': True, 'SchemaUnchanged': True, 'KeysTypesAndPrivateMediaUnchanged': True,
            'ProtectedColumnsAndOtherCatalogTablesUnchanged': True, 'CostFingerprintUnchanged': True,
            'AutomaticUpdatedAtProducts': sum(before_rows[r['ProductId']]['UpdatedAt'] != r['UpdatedAt']
                                             for r in after['Tables']['Products'] if r['ProductId'] in expected)}


def execute_transaction(folder, manifest, changes, records, *, rollback=False):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from app.core.env import database_url

    prefix = 'rollback-' if rollback else 'transaction-'
    receipt_path = folder / ('rollback-receipt.json' if rollback else 'receipt.json')
    engine = create_engine(database_url(), connect_args={'connect_timeout': 12}, hide_parameters=True)
    state = {'Status': 'starting', 'StartedAt': now(), 'Target': manifest['Target'],
             'ValueChanges': len(changes), 'ProductUpdates': len(records)}
    committing = False
    try:
        with Session(engine, autoflush=False) as db:
            db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            db.execute(text("SET LOCAL statement_timeout = '20s'"))
            db.execute(text("SET LOCAL idle_in_transaction_session_timeout = '60s'"))
            checked(db.scalar(text("SELECT current_setting('transaction_read_only')")) == 'off', 'Database is read-only')
            ids = sorted(r['ProductId'] for r in records)
            locked = db.scalars(text('''SELECT "ProductId" FROM "Products"
                WHERE "ProductId" = ANY(CAST(:ids AS uuid[])) ORDER BY "ProductId" FOR UPDATE'''), {'ids': ids}).all()
            checked({str(pid) for pid in locked} == set(ids), 'Could not lock the exact target products')
            before = snapshot_in_transaction(db)
            checked(before['SchemaFingerprint'] == read_json(folder / 'preflight.json')['SchemaFingerprint'], 'Schema changed after preparation')
            match_records(before, records)
            # All recovery material is durable before the only UPDATE statement.
            save_json(folder / (prefix + 'before.json'), before)
            state.update(Status='backup_ready', BeforeHash=digest(before))
            save_json(receipt_path, state, replace=not rollback)
            updated = db.scalars(text(BATCH_UPDATE), {'patches': patch_payload(records)}).all()
            checked({str(pid) for pid in updated} == set(ids) and len(updated) == len(ids),
                    'Original-value comparison rejected part of the update; rolling back everything')
            after = snapshot_in_transaction(db)
            checks = validate_transition(before, after, changes, records)
            save_json(folder / (prefix + 'after.json'), after)
            state.update(Status='ready_to_commit', AfterHash=digest(after), Checks=checks)
            save_json(receipt_path, state, replace=True)
            committing = True
            db.commit()
            state.update(Status='committed', CommittedAt=now())
            save_json(receipt_path, state, replace=True)
            committing = False
            return state
    except Exception:
        # A failed COMMIT response is ambiguous. Never retry a write; --verify resolves it by SELECT.
        state.update(Status='commit_unknown' if committing else 'rolled_back', StoppedAt=now())
        if receipt_path.exists():
            save_json(receipt_path, state, replace=True)
        raise
    finally:
        engine.dispose()


def apply_run(folder):
    manifest, _, _, changes, plan = load_run(folder)
    receipt = read_json(folder / 'receipt.json')
    checked(receipt['Status'] == 'prepared', 'This run is not prepared; use --verify before any further action')
    checked(bool(plan['Records']), 'The reviewed list was already applied; no writes are needed')
    return execute_transaction(folder, manifest, changes, plan['Records'])


def committed_snapshots(folder, receipt, prefix):
    before, after = read_json(folder / (prefix + 'before.json')), read_json(folder / (prefix + 'after.json'))
    checked(digest(before) == receipt['BeforeHash'] and digest(after) == receipt['AfterHash'], 'A transaction backup was modified')
    return before, after


def rollback_run(folder):
    manifest, _, _, changes, plan = load_run(folder)
    receipt = read_json(folder / 'receipt.json')
    checked(receipt['Status'] in ('committed', 'committed_verified'), 'Rollback requires a confirmed committed run')
    checked(not (folder / 'rollback-receipt.json').exists(), 'A rollback was already attempted; verify it first')
    before, after = committed_snapshots(folder, receipt, 'transaction-')
    validate_transition(before, after, changes, plan['Records'])
    previous = {p['ProductId']: p for p in before['Tables']['Products']}
    applied = {p['ProductId']: p for p in after['Tables']['Products']}
    records = [{'ProductId': r['ProductId'], 'BeforeRow': applied[r['ProductId']],
                'AfterSpecs': previous[r['ProductId']]['Specifications']} for r in plan['Records']]
    reverse = [{**c, 'Before': c['Proposed'], 'Proposed': c['Before'], 'Classification': 'verified_correction'} for c in changes]
    return execute_transaction(folder, manifest, reverse, records, rollback=True)


def verify_run(folder, *, rollback=False):
    manifest, _, _, changes, plan = load_run(folder)
    receipt_path = folder / ('rollback-receipt.json' if rollback else 'receipt.json')
    receipt = read_json(receipt_path)
    checked(receipt['Status'] in ('committed', 'committed_verified', 'commit_unknown', 'ready_to_commit'),
            'This run has no commit to verify')
    prefix = 'rollback-' if rollback else 'transaction-'
    before, after = committed_snapshots(folder, receipt, prefix)
    current = capture()
    ids = {r['ProductId'] for r in plan['Records']}
    def targets(snapshot):
        return [r for r in snapshot['Tables']['Products'] if r['ProductId'] in ids]
    matches_after = targets(current) == targets(after)
    matches_before = targets(current) == targets(before)
    verification = {'CheckedAt': now(), 'ReadOnly': True, 'MatchesCommittedTargetRows': matches_after,
                    'MatchesBeforeTargetRows': matches_before,
                    'SchemaUnchanged': current['SchemaFingerprint'] == before['SchemaFingerprint'],
                    'WholeCatalogMatchesTransactionAfter': current['CatalogFingerprint'] == after['CatalogFingerprint'],
                    'CostFingerprintMatchesTransactionAfter': current['ProtectedCostFingerprint'] == after['ProtectedCostFingerprint'],
                    'Counts': current['Counts'], 'ValueChanges': len(changes), 'ProductUpdates': len(ids)}
    save_json(folder / ('rollback-verification.json' if rollback else 'verification.json'), verification, replace=True)
    save_json(folder / ('rollback-live-after.json' if rollback else 'live-after.json'), current, replace=True)
    if matches_after and verification['SchemaUnchanged']:
        receipt.update(Status='committed_verified', VerifiedAt=now())
        save_json(receipt_path, receipt, replace=True)
    checked(matches_after and verification['SchemaUnchanged'], 'Post-commit SELECT differs; inspect verification.json before any action')
    return verification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--apply', type=Path, metavar='RUN_DIRECTORY')
    mode.add_argument('--rollback', type=Path, metavar='RUN_DIRECTORY')
    mode.add_argument('--verify', type=Path, metavar='RUN_DIRECTORY')
    parser.add_argument('--verify-rollback', action='store_true')
    parser.add_argument('--source', type=Path, default=ROOT / 'output/catalog-standardization')
    parser.add_argument('--evidence', type=Path, default=BACKEND / 'data/catalog-standardization-evidence-2026-10-29.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/catalog-standardization/phase-b')
    parser.add_argument('--expected-changes', type=int)
    parser.add_argument('--expected-products', type=int)
    args = parser.parse_args()
    if args.prepare and (args.expected_changes is None or args.expected_products is None):
        parser.error('--prepare requires the authorized --expected-changes and --expected-products counts')
    if args.verify_rollback and not args.verify:
        parser.error('--verify-rollback requires --verify')
    try:
        if args.prepare:
            prepare(args.source, args.evidence, args.output, args.expected_changes, args.expected_products)
        elif args.apply:
            print(json.dumps(apply_run(args.apply), ensure_ascii=False))
        elif args.rollback:
            print(json.dumps(rollback_run(args.rollback), ensure_ascii=False))
        else:
            print(json.dumps(verify_run(args.verify, rollback=args.verify_rollback), ensure_ascii=False))
        return 0
    except GuardError as error:
        print('Phase B stopped:', str(error))
        return 2
    except Exception as error:
        # Driver exception strings/tracebacks may contain credentials. Never print them.
        print('Phase B failed:', type(error).__name__)
        code = getattr(getattr(error, 'orig', None), 'sqlstate', None)
        if code:
            print('SQLSTATE:', code)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
