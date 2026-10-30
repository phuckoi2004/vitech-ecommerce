"""Freeze, apply and verify reviewed descriptions and existing specification values, with no DDL.

Reuses the established read-only catalog capture, durable backups and transaction inventory.
All other columns, JSON keys, private media, variants and catalog tables are protected.
"""
from __future__ import annotations

import argparse
import copy
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parent))

from apply_catalog_standardization import GuardError, checked, now, save_json, snapshot_in_transaction, target_identity
from audit_catalog_specs import capture, digest
from catalog_standardization import validate_snapshot

TARGET = 'stkvyiqosljeehbkqteb'
MARKER = '<h2>Thông số kỹ thuật chi tiết</h2>'
OFFICIAL = ('apple.com', 'samsung.com', 'honor.com', 'sony.com', 'sony.com.vn', 'marshall.com', 'jbl.com', 'anker.com', 'msi.com')
# Product listings and direct device measurements used only by the explicit VN review mode.
VN_REVIEW_HOSTS = ('fptshop.com.vn', 'www.thegioididong.com', 'cellphones.com.vn', 'didongviet.vn')
XCODE_RAM_REPORT = 'https://www.macrumors.com/2026/09/09/iphone-18-pro-and-pro-max-ram/'
PUNCTUATION = re.compile(r'&(?:#\d+|#x[0-9a-f]+|[a-z][a-z0-9]*);|[;；]', re.I)
UPDATE = '''UPDATE "Products" AS p
 SET "Description" = x."Description", "Specifications" = x."Specifications"
 FROM jsonb_to_recordset(CAST(:patches AS jsonb)) AS x(
   "ProductId" uuid, "BeforeDescription" text, "BeforeSpecifications" jsonb,
   "Description" text, "Specifications" jsonb, "UpdatedAt" timestamptz)
 WHERE p."ProductId" = x."ProductId"
   AND p."Description" IS NOT DISTINCT FROM x."BeforeDescription"
   AND p."Specifications" IS NOT DISTINCT FROM x."BeforeSpecifications"
   AND p."UpdatedAt" IS NOT DISTINCT FROM x."UpdatedAt"
 RETURNING p."ProductId"'''
UPDATE_DESCRIPTION = UPDATE.replace(', "Specifications" = x."Specifications"', '')


def commas(value):
    return PUNCTUATION.sub(lambda match: match[0] if match[0].startswith('&') else ',', value)


def same_shape(before, after):
    checked(type(before) is type(after), 'A specification type changed')
    if isinstance(before, dict):
        checked(before.keys() == after.keys(), 'Specification keys changed')
        for key in before:
            if key.startswith('_'):
                checked(before[key] == after[key], 'Private metadata changed')
            else:
                same_shape(before[key], after[key])
    elif isinstance(before, list):
        checked(len(before) == len(after), 'A specification list changed shape')
        for old, new in zip(before, after):
            same_shape(old, new)


def display(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'Có' if value else 'Không'
    if isinstance(value, list):
        return ', '.join(filter(None, (display(item) for item in value)))
    if isinstance(value, dict):
        return ', '.join(f'{key}: {display(item)}' for key, item in value.items() if not key.startswith('_'))
    return str(value).strip()


def detailed_description(original, specs, evidence, *, include_technical_details=False):
    checked(MARKER not in (original or ''), 'Description already enriched, capture and inspect before preparing another run')
    original = original or ''
    for old, new in evidence.get('DescriptionReplacements', {}).items():
        original = original.replace(old, new)
    pieces = re.split(r'(<[^>]*>)', original or '')
    original = ''.join(piece if i % 2 else commas(piece) for i, piece in enumerate(pieces))
    extra = ''.join(f'<p>{html.escape(commas(line))}</p>' for line in evidence.get('DescriptionFacts', []))
    if extra:
        extra = '<h2>Đặc điểm và cách sử dụng</h2>' + extra
    result = original + extra
    # Only historical frozen plans use the old technical appendix during verification.
    # New descriptions leave tabular specifications in the storefront's existing table.
    if not include_technical_details:
        checked(bool(result.strip()), 'A narrative description is required')
        checked(not re.search(r'<\s*(?:script|iframe|object)\b|\son[a-z]+\s*=', result, re.I), 'Unsafe description HTML')
        return result
    groups = {}
    for key, value in specs.items():
        if key.startswith('_'):
            continue
        shown = display(value)
        if not shown:
            continue
        if re.search(r'CPU|RAM|GPU|[Cc]hipset|Ổ cứng|Bộ nhớ|card đồ họa|[Ss]ố khe', key):
            group = 'Bộ xử lý và bộ nhớ'
        elif 'màn hình' in key or 'phân giải' in key or 'Tần số quét' in key:
            group = 'Màn hình và hiển thị'
        elif 'Camera' in key or 'âm thanh' in key or key == 'Micro':
            group = 'Camera và âm thanh'
        elif re.search(r'[Pp]in|[Ss]ạc|[Cc]ông suất|[Nn]guồn', key):
            group = 'Pin và nguồn điện'
        elif re.search(r'[Cc]ổng|[Kk]ết nối|[Đđ]iều khiển|[Mm]ạng|SIM|NFC', key):
            group = 'Kết nối và điều khiển'
        else:
            group = 'Thiết kế và tính năng'
        groups.setdefault(group, []).append(f'<li><strong>{html.escape(key)}:</strong> {html.escape(commas(shown))}</li>')
    result = original + extra + MARKER + ''.join(f'<h3>{group}</h3><ul>{"".join(rows)}</ul>' for group, rows in groups.items())
    checked(bool(groups), 'No displayable technical specifications')
    checked(not re.search(r'<\s*(?:script|iframe|object)\b|\son[a-z]+\s*=', result, re.I), 'Unsafe description HTML')
    checked(re.findall(r'<img\b[^>]*>', result, re.I) == re.findall(r'<img\b[^>]*>', original, re.I), 'Description images changed')
    return result


def make_plan(snapshot, evidence, *, include_technical_details=False):
    from app.core.catalog_media import technical_specifications
    from app.schemas.catalog import ProductUpdate

    entries = evidence['Products']
    reviewed = {entry['Name']: entry for entry in entries}
    checked(len(entries) == len(reviewed), 'Duplicate reviewed product')
    products = snapshot['Tables']['Products']
    names = {row['Name'] for row in products}
    checked(set(reviewed) <= names, 'Reviewed product identity missing from snapshot')
    records, changes = [], []
    for row in products:
        checked(not row['IsDeleted'] and row['Status'] == 'Active', 'Inactive product requires a separate review')
        item = reviewed.get(row['Name'], {})
        for url in item.get('Sources', []):
            parsed = urlparse(url)
            hostname = parsed.hostname or ''
            checked(parsed.scheme == 'https' and any(hostname == host or hostname.endswith('.' + host) for host in OFFICIAL), 'Unreviewed source host')
        specs = copy.deepcopy(row['Specifications'])
        fields = {**item.get('Fields', {}), **{key: prefix + ', ' + commas(specs.get(key, '')) for key, prefix in item.get('PrefixFields', {}).items()}}
        for key, value in fields.items():
            checked(key in specs and isinstance(specs[key], str) and not key.startswith('_'), 'Only existing public string attributes can be enriched')
            checked(item.get('Sources') and item.get('Scope'), 'A technical edit needs reviewed exact-model evidence')
            checked(not re.search('[;；]', value), 'Use commas in new customer prose')
            if specs[key] != value:
                changes.append({'ProductId':row['ProductId'], 'Name':row['Name'], 'Attribute':key,
                                'Before':specs[key], 'After':value, 'Sources':item['Sources'], 'Scope':item['Scope']})
                specs[key] = value
        same_shape(row['Specifications'], specs)
        description = detailed_description(row['Description'], specs, item, include_technical_details=include_technical_details)
        ProductUpdate(Description=description, Specifications=technical_specifications(specs))
        records.append({'ProductId':row['ProductId'], 'BeforeRow':row, 'Description':description, 'Specifications':specs})
    result = {'Records':records, 'SpecificationChanges':changes, 'DescriptionUpdates':len(records), 'VerifiedProducts':len(entries)}
    if not include_technical_details:
        result['DescriptionLayout'] = 'narrative'
    return result


def make_removal_plan(snapshot, evidence):
    """Remove only each exact appendix owned by the verified source run, preserving newer prefix edits."""
    from app.schemas.catalog import ProductUpdate

    suffixes = evidence['Appendices']
    checked(len({item['ProductId'] for item in suffixes}) == len(suffixes), 'Duplicate appendix target')
    products = {row['ProductId']:row for row in snapshot['Tables']['Products']}
    records = []
    for item in suffixes:
        row = products.get(item['ProductId'])
        checked(row is not None, 'A source product no longer exists')
        suffix = item['Suffix']
        description = row['Description'] or ''
        checked(suffix.startswith(MARKER) and suffix.count(MARKER) == 1, 'Invalid owned technical appendix')
        checked(description.count(MARKER) == 1 and description.endswith(suffix), 'Technical appendix changed after enrichment, cleanup refused')
        narrative = description[:-len(suffix)]
        checked(bool(narrative.strip()), 'Cleanup would leave an empty description')
        ProductUpdate(Description=narrative)
        records.append({'ProductId':row['ProductId'], 'BeforeRow':row,
                        'Description':narrative, 'Specifications':copy.deepcopy(row['Specifications'])})
    return {'Operation':'remove_redundant_specs', 'DescriptionLayout':'narrative', 'Records':records,
            'SpecificationChanges':[], 'DescriptionUpdates':len(records), 'VerifiedProducts':0}


def make_scoped_content_plan(snapshot, evidence):
    """Apply exact reviewed paragraphs and existing values to selected products only."""
    from app.core.catalog_media import technical_specifications
    from app.schemas.catalog import ProductUpdate
    from catalog_standardization import PRIMARY_DOMAINS

    entries = evidence['Products']
    checked(entries and len({item['ProductId'] for item in entries}) == len(entries), 'Duplicate or empty content targets')
    products = {row['ProductId']: row for row in snapshot['Tables']['Products']}
    records, changes = [], []
    for item in entries:
        row = products.get(item['ProductId'])
        checked(row is not None and row['Name'] == item['Name'], 'Reviewed product identity changed')
        checked(not row['IsDeleted'] and row['Status'] == 'Active', 'Inactive product requires a separate review')
        checked(item.get('Sources') and item.get('Scope'), 'Content needs reviewed exact-model evidence')
        for source in item['Sources']:
            parsed = urlparse(source)
            host = parsed.hostname or ''
            manufacturer = any(host == domain or host.endswith('.' + domain) for domain in PRIMARY_DOMAINS)
            teardown = (item.get('SourceKind') == 'primary_teardown' and host == 'www.ifixit.com'
                        and parsed.path.startswith('/Teardown/'))
            vn_review = (item.get('SourceKind') == 'vietnam_crosscheck' and host in VN_REVIEW_HOSTS
                         and parsed.path not in ('', '/'))
            xcode_analysis = (item.get('SourceKind') == 'vietnam_crosscheck' and source == XCODE_RAM_REPORT)
            checked(parsed.scheme == 'https' and not parsed.username and not parsed.password
                    and (manufacturer or teardown or vn_review or xcode_analysis), 'Unreviewed source host')
        if item.get('SourceKind') == 'vietnam_crosscheck':
            local_sources = item.get('VietnamSources', [])
            checked(local_sources and set(local_sources) <= set(item['Sources']), 'VN review needs linked local sources')
            checked(all((urlparse(url).hostname or '') in VN_REVIEW_HOSTS or
                        (urlparse(url).path.startswith('/vn/') and any(
                            (urlparse(url).hostname or '') == domain or
                            (urlparse(url).hostname or '').endswith('.' + domain) for domain in PRIMARY_DOMAINS))
                        for url in local_sources), 'VN review source is not local')
            checked(item.get('VariantScope') and item.get('VerificationBasis'), 'VN review needs exact variant and evidence basis')
        specs = copy.deepcopy(row['Specifications'])
        for key, value in item.get('Fields', {}).items():
            checked(key in specs and isinstance(specs[key], str) and isinstance(value, str)
                    and not key.startswith('_'), 'Only existing public string attributes can be enriched')
            checked(bool(value.strip()) and not re.search('[;；]', value), 'Use commas in new customer prose')
            if value != specs[key]:
                changes.append({'ProductId': row['ProductId'], 'Name': row['Name'], 'Attribute': key,
                                'Before': specs[key], 'After': value, 'Sources': item['Sources'], 'Scope': item['Scope']})
                specs[key] = value
        original = row['Description'] or ''
        description = original
        for edit in item.get('DescriptionEdits', []):
            old, new = edit['Before'], edit['After']
            checked(isinstance(old, str) and isinstance(new, str) and old.strip() and new.strip()
                    and old != new, 'Empty or identical description edit')
            checked(description.count(old) == 1 and new not in description,
                    'Description anchor changed, ambiguous or already applied')
            checked(all(commas(piece) == piece for piece in re.split(r'(<[^>]*>)', new)[::2]),
                    'Use commas in new customer prose')
            description = description.replace(old, new, 1)
        checked(MARKER not in description, 'Technical appendix must stay in the existing specifications table')
        checked(re.findall(r'<h2\b[^>]*>.*?</h2>', description, re.I | re.S)
                == re.findall(r'<h2\b[^>]*>.*?</h2>', original, re.I | re.S), 'Description sections changed')
        checked(re.findall(r'<img\b[^>]*>', description, re.I)
                == re.findall(r'<img\b[^>]*>', original, re.I), 'Description images changed')
        checked(not re.search(r'<\s*(?:script|iframe|object)\b|\son[a-z]+\s*=', description, re.I), 'Unsafe description HTML')
        same_shape(row['Specifications'], specs)
        ProductUpdate(Description=description, Specifications=technical_specifications(specs))
        checked(description != original or specs != row['Specifications'], 'Reviewed product has no content changes')
        records.append({'ProductId': row['ProductId'], 'BeforeRow': row,
                        'Description': description, 'Specifications': specs})
    return {'Operation': 'enrich_scoped_content', 'DescriptionLayout': 'narrative', 'Records': records,
            'SpecificationChanges': changes,
            'DescriptionUpdates': sum(item['Description'] != item['BeforeRow']['Description'] for item in records),
            'VerifiedProducts': len(entries)}


def validate_transition(before, after, records):
    for key in ('Counts', 'SchemaFingerprint', 'ProtectedCostFingerprint'):
        checked(before[key] == after[key], 'Protected invariant changed: ' + key)
    planned = {record['ProductId']:record for record in records}
    normalized = copy.deepcopy(after['Tables'])
    old = {row['ProductId']:row for row in before['Tables']['Products']}
    for row in normalized['Products']:
        if row['ProductId'] not in planned:
            continue
        target = planned[row['ProductId']]
        checked(row['Description'] == target['Description'] and row['Specifications'] == target['Specifications'], 'Applied values differ from frozen proposal')
        same_shape(old[row['ProductId']]['Specifications'], row['Specifications'])
        checked(datetime.fromisoformat(row['UpdatedAt']) >= datetime.fromisoformat(old[row['ProductId']]['UpdatedAt']), 'Timestamp moved backwards')
        for field in ('Description', 'Specifications', 'UpdatedAt'):
            row[field] = old[row['ProductId']][field]
    checked(normalized == before['Tables'], 'A protected column, variant, image or other catalog table changed')
    return {'ExactPlannedValues':True, 'SchemaUnchanged':True, 'SpecificationKeysAndTypesUnchanged':True,
            'PrivateMediaUnchanged':True, 'OtherCatalogFieldsUnchanged':True, 'CostFingerprintUnchanged':True}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def check_target():
    from sqlalchemy.engine import make_url
    from app.core.env import database_url
    url = make_url(database_url())
    checked(url.host == f'db.{TARGET}.supabase.co' or (url.username or '').endswith('.' + TARGET), 'Configured database does not match authorized VieTech project')
    return target_identity()


def prepare(snapshot_path, evidence_path, output):
    snapshot, evidence = read_json(snapshot_path), read_json(evidence_path)
    validate_snapshot(snapshot)
    plan = (make_scoped_content_plan(snapshot, evidence) if evidence.get('Operation') == 'enrich_scoped_content'
            else make_plan(snapshot, evidence))
    freeze_plan(snapshot, evidence, plan, output)


def freeze_plan(snapshot, evidence, plan, output):
    checked(bool(plan['Records']), 'Empty enrichment plan')
    folder = output / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8])
    folder.mkdir(parents=True)
    save_json(folder / 'preflight.json', snapshot)
    save_json(folder / 'evidence.json', evidence)
    save_json(folder / 'plan.json', plan)
    save_json(folder / 'manifest.json', {'Version':1, 'Target':check_target(), 'Project':TARGET,
        'SnapshotHash':digest(snapshot), 'EvidenceHash':digest(evidence), 'PlanHash':digest(plan)})
    save_json(folder / 'receipt.json', {'Status':'prepared', 'PreparedAt':now()})
    reviewed_label = 'ReviewedProducts' if plan.get('Operation') == 'enrich_scoped_content' else 'ManufacturerReviewedProducts'
    print(json.dumps({'Status':'prepared', 'RunDirectory':str(folder), 'Descriptions':plan['DescriptionUpdates'],
                      'SpecificationValues':len(plan['SpecificationChanges']), reviewed_label:plan['VerifiedProducts']}))


def prepare_removal(source, output):
    _, plan = load(source)
    receipt = read_json(source / 'receipt.json')
    checked(receipt['Status'] == 'committed_verified', 'Cleanup requires a verified enrichment run')
    applied = read_json(source / 'transaction-after.json')
    checked(digest(applied) == receipt['AfterHash'], 'Source transaction backup changed')
    checked(not plan.get('Operation'), 'Source must be the original enrichment')
    appendices = []
    for record in plan['Records']:
        checked(record['Description'].count(MARKER) == 1, 'Source has no unique technical appendix')
        _, suffix = record['Description'].split(MARKER, 1)
        appendices.append({'ProductId':record['ProductId'], 'Suffix':MARKER + suffix})
    evidence = {'Operation':'remove_redundant_specs', 'SourcePlanHash':digest(plan), 'Appendices':appendices}
    current = capture()
    validate_snapshot(current)
    freeze_plan(current, evidence, make_removal_plan(current, evidence), output)


def load(folder):
    manifest, before, evidence, plan = (read_json(folder / name) for name in ('manifest.json', 'preflight.json', 'evidence.json', 'plan.json'))
    checked(manifest['Target'] == check_target() and manifest['Project'] == TARGET, 'Database target changed')
    checked(digest(before) == manifest['SnapshotHash'] and digest(evidence) == manifest['EvidenceHash'] and digest(plan) == manifest['PlanHash'], 'Frozen recovery input changed')
    validate_snapshot(before)
    operation = evidence.get('Operation')
    expected = (make_removal_plan(before, evidence) if operation == 'remove_redundant_specs'
                else make_scoped_content_plan(before, evidence) if operation == 'enrich_scoped_content'
                else make_plan(before, evidence, include_technical_details='DescriptionLayout' not in plan))
    checked(expected == plan, 'Frozen plan differs from reviewed evidence')
    return before, plan


def apply(folder, *, rollback=False):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from app.core.env import database_url
    baseline, plan = load(folder)
    receipt = read_json(folder / 'receipt.json')
    checked(receipt['Status'] in ('committed', 'committed_verified') if rollback else receipt['Status'] == 'prepared', 'Run already attempted, verify before any further write')
    prefix = 'rollback-' if rollback else 'transaction-'
    receipt_path = folder / ('rollback-receipt.json' if rollback else 'receipt.json')
    checked(not rollback or not receipt_path.exists(), 'Rollback already attempted')
    records = plan['Records']
    if rollback:
        baseline = read_json(folder / 'transaction-after.json')
        applied = {row['ProductId']:row for row in baseline['Tables']['Products']}
        records = [{'ProductId':record['ProductId'], 'BeforeRow':applied[record['ProductId']],
                    'Description':record['BeforeRow']['Description'], 'Specifications':record['BeforeRow']['Specifications']} for record in records]
    engine = create_engine(database_url(), connect_args={'connect_timeout':12}, hide_parameters=True)
    committing = False
    state = {'Status':'starting', 'StartedAt':now(), 'Project':TARGET, 'Products':len(records)}
    try:
        with Session(engine, autoflush=False) as db:
            db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            db.execute(text("SET LOCAL statement_timeout = '25s'"))
            db.execute(text("SET LOCAL idle_in_transaction_session_timeout = '60s'"))
            ids = sorted(record['ProductId'] for record in records)
            locked = db.scalars(text('SELECT "ProductId" FROM "Products" WHERE "ProductId"=ANY(CAST(:ids AS uuid[])) ORDER BY "ProductId" FOR UPDATE'), {'ids':ids}).all()
            checked({str(pid) for pid in locked} == set(ids), 'Could not lock every planned product')
            before = snapshot_in_transaction(db)
            current = {row['ProductId']:row for row in before['Tables']['Products']}
            checked(before['SchemaFingerprint'] == baseline['SchemaFingerprint'], 'Schema changed')
            checked(all(current.get(record['ProductId']) == record['BeforeRow'] for record in records), 'A product changed after review, update refused')
            save_json(folder / (prefix + 'before.json'), before)
            state.update(Status='backup_ready', BeforeHash=digest(before))
            save_json(receipt_path, state, replace=not rollback)
            patches = [{'ProductId':record['ProductId'], 'BeforeDescription':record['BeforeRow']['Description'],
                'BeforeSpecifications':record['BeforeRow']['Specifications'], 'UpdatedAt':record['BeforeRow']['UpdatedAt'],
                'Description':record['Description'], 'Specifications':record['Specifications']} for record in records]
            description_only = (plan.get('Operation') == 'remove_redundant_specs' or
                                (plan.get('Operation') == 'enrich_scoped_content' and not plan['SpecificationChanges']))
            statement = UPDATE_DESCRIPTION if description_only else UPDATE
            updated = db.scalars(text(statement), {'patches':json.dumps(patches, ensure_ascii=False)}).all()
            checked(len(updated) == len(ids) and {str(pid) for pid in updated} == set(ids), 'Concurrent edit rejected part of batch, all updates rolled back')
            after = snapshot_in_transaction(db)
            checks = validate_transition(before, after, records)
            save_json(folder / (prefix + 'after.json'), after)
            state.update(Status='ready_to_commit', AfterHash=digest(after), Checks=checks)
            save_json(receipt_path, state, replace=True)
            committing = True
            db.commit()
            state.update(Status='committed', CommittedAt=now())
            save_json(receipt_path, state, replace=True)
            committing = False
    except Exception:
        state.update(Status='commit_unknown' if committing else 'rolled_back', StoppedAt=now())
        if receipt_path.exists():
            save_json(receipt_path, state, replace=True)
        raise
    finally:
        engine.dispose()
    return state


def verify(folder, *, rollback=False):
    _, plan = load(folder)
    prefix = 'rollback-' if rollback else 'transaction-'
    receipt_path = folder / ('rollback-receipt.json' if rollback else 'receipt.json')
    receipt = read_json(receipt_path)
    checked(receipt['Status'] in ('committed', 'committed_verified', 'commit_unknown', 'ready_to_commit'), 'No commit to verify')
    before, expected = (read_json(folder / (prefix + part + '.json')) for part in ('before', 'after'))
    checked(digest(before) == receipt['BeforeHash'] and digest(expected) == receipt['AfterHash'], 'Transaction backup changed')
    current = capture()
    wanted = {record['ProductId'] for record in plan['Records']}
    targets = lambda snap: [row for row in snap['Tables']['Products'] if row['ProductId'] in wanted]
    result = {'CheckedAt':now(), 'ReadOnly':True, 'Project':TARGET, 'Products':len(wanted),
        'MatchesCommittedRows':targets(current) == targets(expected),
        'SchemaUnchanged':current['SchemaFingerprint'] == before['SchemaFingerprint'],
        'WholeCatalogMatchesTransactionAfter':current['CatalogFingerprint'] == expected['CatalogFingerprint'],
        'CostFingerprintUnchanged':current['ProtectedCostFingerprint'] == expected['ProtectedCostFingerprint'],
        'Counts':current['Counts']}
    save_json(folder / (prefix + 'verification.json'), result, replace=True)
    save_json(folder / (prefix + 'live-after.json'), current, replace=True)
    checked(result['MatchesCommittedRows'] and result['SchemaUnchanged'], 'Post-commit verification differs, do not rerun apply')
    receipt.update(Status='committed_verified', VerifiedAt=now())
    save_json(receipt_path, receipt, replace=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--remove-technical-section', type=Path, metavar='VERIFIED_SOURCE_RUN',
                      help='Prepare removal of the exact redundant appendix from a verified run, read-only')
    mode.add_argument('--apply', type=Path)
    mode.add_argument('--verify', type=Path)
    mode.add_argument('--rollback', type=Path)
    parser.add_argument('--verify-rollback', action='store_true')
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--evidence', type=Path, default=ROOT / 'backend/data/catalog-details-evidence-2026-10-30.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/catalog-enrichment-20261030/runs')
    args = parser.parse_args()
    try:
        if args.remove_technical_section:
            prepare_removal(args.remove_technical_section, args.output)
        elif args.prepare:
            checked(args.snapshot is not None, 'Prepare requires a current read-only snapshot')
            prepare(args.snapshot, args.evidence, args.output)
        else:
            result = verify(args.verify, rollback=args.verify_rollback) if args.verify else apply(args.apply or args.rollback, rollback=bool(args.rollback))
            print(json.dumps(result, ensure_ascii=False))
        return 0
    except GuardError as error:
        print('Enrichment stopped:', str(error))
        return 2
    except Exception as error:
        print('Enrichment failed:', type(error).__name__)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
