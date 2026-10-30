"""Add reviewed launch years to existing Specifications, without DDL or other catalog edits."""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parent))

from apply_catalog_standardization import BATCH_UPDATE, GuardError, checked, now, save_json, snapshot_in_transaction
from audit_catalog_specs import capture, digest
from catalog_standardization import validate_snapshot
from enrich_catalog_details import check_target, read_json, TARGET

KEY = 'Năm ra mắt'
EXISTING_DATE_KEYS = ('Thời điểm ra mắt', 'Ngày ra mắt', KEY)
SOURCE_HOSTS = ('apple.com', 'samsung.com', 'oppo.com', 'mi.com', 'honor.com', 'huawei.com',
                'acer.com', 'asus.com', 'msi.com', 'lenovo.com', 'dell.com', 'delltechnologies.com',
                'hp.com', 'hpcloud.hp.com', 'gigabyte.com', 'lg.com', 'lge.co.kr', 'philips.com',
                'sony.com', 'sony.com.cn', 'sony.co.uk', 'sony.com.hk', 'sony.com.au', 'sony.jp', 'sony.net',
                'bose.com', 'bose.co.uk', 'bosecreative.com', 'marshall.com', 'jbl.com', 'harman.com',
                'logitech.com', 'logi.com', 'logitechg.com', 'soundcore.com', 'anker.com', 'ankerjapan.com',
                'edifier.com', 'teclast.com', 'nubia.com', 'meizu.com', 'baseus.com', 'cuktech.com', 'edravn.com',
                'e-dra.vn', 'hyperwork.vn', 'ugreen.com', 'dareu.com', 'dareu.com.vn',
                'cellphones.com.vn', 'fptshop.com.vn', 'thegioididong.com', 'dienmayxanh.com',
                'gearvn.com', 'targus.com', 'itel-life.com', 'akkogear.com')
REVIEWED_EXTERNAL_SOURCES = {
    'https://www.mynewsdesk.com/de/asus-dach/pressreleases/asus-republic-of-gamers-announces-azoth-96-he-3422906': 'ASUS Computer GmbH',
    'https://prtimes.jp/main/html/rd/p/000000948.000017808.html': 'ASUS JAPAN',
    'https://prtimes.jp/main/html/rd/p/000000504.000012767.html': 'Harman International Japan',
    'https://www.prnewswire.com/apac/news-releases/redefining-charging-anker-innovations-showcases-smart-and-sustainable-solutions-at-ces-302344616.html': 'Anker Innovations',
    'https://www.prnewswire.com/apac/news-releases/soundcore-r60i-nc-arrives-in-malaysia-with-smarter-active-noise-cancellation-and-powerful-audio-302612328.html': 'Anker Innovations',
    'https://prtimes.jp/main/html/rd/p/000000480.000080488.html': 'Teclast / GUANGZHOU SHANGKE INFORMATION TECHNOLOGY (HK) LIMITED',
    'https://www.hartware.de/2025/07/01/baseus-produktstart-drei-neue-produkte-kommen-auf-den-markt/': 'Baseus manufacturer press release',
    'https://ifdesign.com/en/winner-ranking/project/ace-68-air/741679': 'MCHOSE manufacturer submission, Date of Launch field',
    'https://www.linkedin.com/posts/delphinedonne_innovation-china-logitech-activity-7234852926488211458-fy-e': 'Logitech launch announcement by Delphine Donne',
    'https://telset.id/gizmo/soundcore-luncurkan-tws-r50i-nc-bawa-fitur-noise-canceling': 'Soundcore official launch statement received by Telset on 17 May 2024',
    'https://thanhnien.vn/soundcore-ra-mat-dong-tai-nghe-open-ear-wireless-stereo-185251103181907391.htm': 'Firsthand Vietnam launch report and photographs by Thanh Nien author Thanh Luan',
}


def has_launch_date(specs):
    return any(re.search(r'\b(?:19|20)\d{2}\b', str(specs.get(key, ''))) for key in EXISTING_DATE_KEYS)


def make_plan(snapshot, evidence):
    validate_snapshot(snapshot)
    checked(evidence.get('Operation') == 'add_launch_year', 'Unsupported operation')
    reviewed = date.fromisoformat(evidence['ReviewedAt'])
    checked(reviewed <= date.today(), 'Review date is in the future')
    rows = {p['ProductId']:p for p in snapshot['Tables']['Products']}
    entries = evidence['Products']
    checked(len({item['ProductId'] for item in entries}) == len(entries), 'Duplicate product evidence')
    records = []
    retained = [p['ProductId'] for p in snapshot['Tables']['Products'] if has_launch_date(p['Specifications'])]
    for item in entries:
        row = rows.get(item['ProductId'])
        checked(row is not None and row['Name'] == item['Name'], 'Evidence product identity mismatch')
        value = item['Year']
        checked(isinstance(value, str) and re.fullmatch(r'(?:19|20)\d{2}', value) is not None,
                'Launch year must be a four-digit string')
        checked(1970 <= int(value) <= reviewed.year, 'Launch year is outside the reviewed range')
        checked(item.get('Scope') and item.get('Basis') and item.get('ModelMatch'), 'Missing exact-model launch evidence')
        sources = item.get('Sources', [])
        checked(sources, 'Launch year requires a source')
        for source in sources:
            parsed = urlparse(source)
            host = (parsed.hostname or '').lower()
            checked(parsed.scheme == 'https' and not parsed.username and not parsed.password and
                    (source in REVIEWED_EXTERNAL_SOURCES or
                     any(host == allowed or host.endswith('.' + allowed) for allowed in SOURCE_HOSTS)),
                    'Unreviewed launch source host')
        before = row['Specifications']
        checked(isinstance(before, dict), 'Expected a Specifications object')
        if has_launch_date(before):
            years = {year for key in EXISTING_DATE_KEYS for year in
                     re.findall(r'\b(?:19|20)\d{2}\b', str(before.get(key, '')))}
            checked(years == {value}, 'Existing launch date disagrees with reviewed year')
            continue
        checked(KEY not in before, 'Existing launch-year value must be reviewed separately')
        after = copy.deepcopy(before)
        after[KEY] = value
        records.append({'ProductId':row['ProductId'], 'BeforeRow':copy.deepcopy(row), 'AfterSpecs':after})
    return {'Operation':'add_launch_year', 'Records':records, 'RetainedProductIds':retained}


def validate_transition(before, after, records):
    for field in ('Counts', 'SchemaFingerprint', 'ProtectedCostFingerprint'):
        checked(before[field] == after[field], 'Protected invariant changed: ' + field)
    planned = {r['ProductId']:r for r in records}
    checked(len(planned) == len(records), 'Duplicate update')
    tables = copy.deepcopy(after['Tables'])
    old = {p['ProductId']:p for p in before['Tables']['Products']}
    seen = set()
    for row in tables['Products']:
        pid = row['ProductId']
        if pid not in planned:
            continue
        record = planned[pid]
        seen.add(pid)
        expected = record['AfterSpecs']
        original = old[pid]['Specifications']
        checked(not has_launch_date(original) and KEY not in original, 'Existing launch information cannot be overwritten')
        checked(set(expected) == set(original) | {KEY} and
                {k:v for k,v in expected.items() if k != KEY} == original and
                isinstance(expected[KEY], str) and re.fullmatch(r'(?:19|20)\d{2}', expected[KEY]),
                'Only the launch-year entry may be added')
        checked(row['Specifications'] == expected, 'Applied Specifications differ from frozen plan')
        checked(datetime.fromisoformat(row['UpdatedAt']) >= datetime.fromisoformat(old[pid]['UpdatedAt']),
                'UpdatedAt moved backwards')
        row['Specifications'] = original
        row['UpdatedAt'] = old[pid]['UpdatedAt']
    checked(seen == set(planned), 'A planned product is missing')
    checked(tables == before['Tables'], 'An existing specification, description, media or protected catalog field changed')
    return {'SchemaUnchanged':True, 'OnlyLaunchYearAdded':True, 'ExistingDatesRetained':True,
            'OtherSpecificationsUnchanged':True, 'OtherCatalogFieldsUnchanged':True}


def prepare(snapshot_path, evidence_path, output):
    snapshot, evidence = read_json(snapshot_path), read_json(evidence_path)
    plan = make_plan(snapshot, evidence)
    checked(plan['Records'], 'No missing launch years to add')
    folder = output / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8])
    folder.mkdir(parents=True)
    for filename, value in [('preflight.json',snapshot), ('evidence.json',evidence), ('plan.json',plan)]:
        save_json(folder / filename, value)
    save_json(folder / 'manifest.json', {'Version':1, 'Target':check_target(), 'Project':TARGET,
        'BeforeHash':digest(snapshot), 'EvidenceHash':digest(evidence), 'PlanHash':digest(plan)})
    save_json(folder / 'receipt.json', {'Status':'prepared', 'PreparedAt':now()})
    return {'Status':'prepared', 'RunDirectory':str(folder), 'Products':len(plan['Records']),
            'RetainedDates':len(plan['RetainedProductIds'])}


def load(folder):
    manifest, before, evidence, plan = (read_json(folder / f) for f in
        ('manifest.json', 'preflight.json', 'evidence.json', 'plan.json'))
    checked(manifest['Target'] == check_target() and manifest['Project'] == TARGET, 'Database target changed')
    checked(manifest['BeforeHash'] == digest(before) and manifest['EvidenceHash'] == digest(evidence)
            and manifest['PlanHash'] == digest(plan), 'Frozen input changed')
    checked(make_plan(before, evidence) == plan, 'Plan differs from reviewed evidence')
    return before, plan


def apply(folder):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from app.core.env import database_url
    baseline, plan = load(folder)
    checked(read_json(folder / 'receipt.json')['Status'] == 'prepared', 'Run already attempted, verify before another write')
    records = plan['Records']
    engine = create_engine(database_url(), connect_args={'connect_timeout':12}, hide_parameters=True)
    state = {'Status':'starting', 'StartedAt':now(), 'Project':TARGET, 'Products':len(records)}
    committing = False
    try:
        with Session(engine, autoflush=False) as db:
            db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            db.execute(text("SET LOCAL statement_timeout = '25s'"))
            db.execute(text("SET LOCAL idle_in_transaction_session_timeout = '60s'"))
            ids = sorted(r['ProductId'] for r in records)
            locked = db.scalars(text('SELECT "ProductId" FROM "Products" WHERE "ProductId"=ANY(CAST(:ids AS uuid[])) ORDER BY "ProductId" FOR UPDATE'), {'ids':ids}).all()
            checked({str(pid) for pid in locked} == set(ids), 'Could not lock every reviewed product')
            before = snapshot_in_transaction(db)
            current = {p['ProductId']:p for p in before['Tables']['Products']}
            checked(before['SchemaFingerprint'] == baseline['SchemaFingerprint'], 'Schema changed')
            checked(all(current.get(r['ProductId']) == r['BeforeRow'] for r in records),
                    'A reviewed product changed, no updates applied')
            save_json(folder / 'transaction-before.json', before)
            state.update(Status='backup_ready', BeforeHash=digest(before))
            save_json(folder / 'receipt.json', state, replace=True)
            patches = [{'ProductId':r['ProductId'], 'Before':r['BeforeRow']['Specifications'],
                        'After':r['AfterSpecs'], 'UpdatedAt':r['BeforeRow']['UpdatedAt']} for r in records]
            updated = db.scalars(text(BATCH_UPDATE), {'patches':json.dumps(patches, ensure_ascii=False)}).all()
            checked({str(pid) for pid in updated} == set(ids) and len(updated) == len(ids), 'Batch incomplete, roll back all updates')
            after = snapshot_in_transaction(db)
            checks = validate_transition(before, after, records)
            save_json(folder / 'transaction-after.json', after)
            state.update(Status='ready_to_commit', AfterHash=digest(after), Checks=checks)
            save_json(folder / 'receipt.json', state, replace=True)
            committing = True
            db.commit()
            state.update(Status='committed', CommittedAt=now())
            save_json(folder / 'receipt.json', state, replace=True)
            committing = False
    except Exception:
        state.update(Status='commit_unknown' if committing else 'rolled_back', StoppedAt=now())
        save_json(folder / 'receipt.json', state, replace=True)
        raise
    finally:
        engine.dispose()
    return state


def verify(folder):
    _, plan = load(folder)
    receipt = read_json(folder / 'receipt.json')
    checked(receipt['Status'] in ('committed', 'committed_verified', 'ready_to_commit', 'commit_unknown'), 'No commit to verify')
    before, expected = (read_json(folder / f'transaction-{part}.json') for part in ('before', 'after'))
    checked(digest(before) == receipt['BeforeHash'] and digest(expected) == receipt['AfterHash'], 'Recovery backup changed')
    current = capture()
    ids = {r['ProductId'] for r in plan['Records']}
    select = lambda snap: [p for p in snap['Tables']['Products'] if p['ProductId'] in ids]
    result = {'CheckedAt':now(), 'ReadOnly':True, 'Products':len(ids), 'Counts':current['Counts'],
        'MatchesCommittedRows':select(current) == select(expected),
        'SchemaUnchanged':current['SchemaFingerprint'] == before['SchemaFingerprint'],
        'CostFingerprintUnchanged':current['ProtectedCostFingerprint'] == before['ProtectedCostFingerprint'],
        'WholeCatalogMatchesTransactionAfter':current['CatalogFingerprint'] == expected['CatalogFingerprint']}
    save_json(folder / 'verification.json', result, replace=True)
    checked(result['MatchesCommittedRows'] and result['SchemaUnchanged'] and result['CostFingerprintUnchanged'],
            'Post-commit verification differs, do not reapply')
    receipt.update(Status='committed_verified', VerifiedAt=now())
    save_json(folder / 'receipt.json', receipt, replace=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--apply', type=Path)
    group.add_argument('--verify', type=Path)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--evidence', type=Path, default=ROOT / 'backend/data/catalog-launch-year-evidence-2026-10-30.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/catalog-launch-year-20261030/runs')
    args = parser.parse_args()
    try:
        if args.prepare:
            checked(args.snapshot is not None, 'Prepare requires a live read-only snapshot')
            result = prepare(args.snapshot, args.evidence, args.output)
        else:
            result = apply(args.apply) if args.apply else verify(args.verify)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        # Connection exceptions may contain credentials, only report safe guard messages and error types.
        print(str(error) if isinstance(error, GuardError) else type(error).__name__, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
