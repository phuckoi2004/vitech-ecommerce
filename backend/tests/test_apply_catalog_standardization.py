"""Phase B guards and recovery paths, entirely offline; never opt into database tests."""
import copy
import csv
import io
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import apply_catalog_standardization as phase_b
from catalog_standardization import audit
from tests.test_catalog_standardization import evidence, original


def review_inputs(snapshot=None, *, corrected=False):
    before = snapshot or original()
    proof = evidence(before) if corrected else {'SnapshotFingerprint': before['CatalogFingerprint'], 'Values': []}
    result = audit(before, proof)
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=list(result['changes'][0]))
    writer.writeheader()
    for row in result['changes']:
        writer.writerow({k: json.dumps(v, ensure_ascii=False) if k in ('Before', 'Proposed') else v
                         for k, v in row.items()})
    inputs = {name: json.dumps(value, ensure_ascii=False).encode('utf-8') for name, value in (
        ('catalog-original.json', before), ('catalog-cleaned.json', result['proposed']), ('evidence.json', proof))}
    inputs['catalog-changes.csv'] = output.getvalue().encode('utf-8-sig')
    return inputs, before, result


def two_products():
    before = original()
    product = copy.deepcopy(before['Tables']['Products'][0])
    product.update(ProductId=str(uuid.uuid4()), Slug='test-laptop-two', Name='Test Laptop Two')
    before['Tables']['Products'].append(product)
    variant = copy.deepcopy(before['Tables']['ProductVariants'][0])
    variant.update(ProductVariantId=str(uuid.uuid4()), ProductId=product['ProductId'], Sku='SKU-TWO')
    before['Tables']['ProductVariants'].append(variant)
    before['Tables']['Products'].sort(key=lambda r: r['ProductId'])
    before['Tables']['ProductVariants'].sort(key=lambda r: r['ProductVariantId'])
    before['Counts'] = {name: len(rows) for name, rows in before['Tables'].items()}
    before['CatalogFingerprint'] = phase_b.digest(before['Tables'])
    return before


@pytest.mark.parametrize('corrected', [False, True])
def test_review_requires_exact_reviewed_values_and_evidence(corrected):
    inputs, before, result = review_inputs(corrected=corrected)
    loaded_before, loaded_proposed, loaded_changes = phase_b.reviewed(inputs)
    assert (loaded_before, loaded_proposed) == (before, result['proposed'])
    # CSV represents optional absent display fields as empty strings.
    assert [{k: v for k, v in row.items() if v != ''} for row in loaded_changes] == [
        {k: v for k, v in row.items() if v != ''} for row in result['changes']]
    proof = json.loads(inputs['evidence.json'])
    proof['SnapshotFingerprint'] = 'other-snapshot'
    inputs['evidence.json'] = json.dumps(proof).encode()
    with pytest.raises(phase_b.GuardError, match='snapshot'):
        phase_b.reviewed(inputs)


def test_review_rejects_changed_correction_even_when_csv_and_json_agree():
    inputs, before, result = review_inputs(corrected=True)
    after = json.loads(inputs['catalog-cleaned.json'])
    after['Tables']['Products'][0]['Specifications']['Dung lượng RAM'] = '64 GB'
    after['CatalogFingerprint'] = phase_b.digest(after['Tables'])
    inputs['catalog-cleaned.json'] = json.dumps(after).encode()
    inputs['catalog-changes.csv'] = inputs['catalog-changes.csv'].replace(b'32 GB', b'64 GB')
    with pytest.raises(phase_b.GuardError, match='evidence'):
        phase_b.reviewed(inputs)


@pytest.mark.parametrize('edit', ['spec', 'timestamp', 'name', 'private_media', 'missing', 'sku', 'schema'])
def test_preflight_rejects_stale_rows_and_wrong_skus(edit):
    _, before, result = review_inputs()
    current = copy.deepcopy(before)
    p = current['Tables']['Products'][0]
    if edit == 'spec':
        p['Specifications']['Dung lượng RAM'] = '64 GB'
    elif edit == 'timestamp':
        p['UpdatedAt'] = '2026-10-29T01:00:00+07:00'
    elif edit == 'name':
        p['Name'] = 'Other SKU'
    elif edit == 'private_media':
        p['Specifications']['_vietech_variant_media']['DefaultVariantId'] = 'changed'
    elif edit == 'missing':
        current['Tables']['Products'].clear()
    elif edit == 'sku':
        current['Tables']['ProductVariants'][0]['Sku'] = 'OTHER'
    else:
        current['SchemaFingerprint'] = 'other'
    with pytest.raises(phase_b.GuardError):
        phase_b.records_for(before, result['proposed'], result['changes'], current)


def test_preflight_preserves_newer_stock_price_and_returns_noop_for_fully_applied_list():
    _, before, result = review_inputs()
    current = copy.deepcopy(before)
    current['Tables']['ProductVariants'][0].update(Price='17000000', StockQuantity=99)
    records = phase_b.records_for(before, result['proposed'], result['changes'], current)
    assert len(records) == 1 and records[0]['BeforeRow'] == before['Tables']['Products'][0]
    current['Tables']['Products'][0].update(Specifications=result['proposed']['Tables']['Products'][0]['Specifications'],
                                           UpdatedAt='2026-10-29T01:00:00+07:00')
    assert phase_b.records_for(before, result['proposed'], result['changes'], current) == []


def test_mixed_applied_and_original_products_are_not_silently_reapplied():
    _, before, result = review_inputs(two_products())
    current = copy.deepcopy(before)
    current['Tables']['Products'][0]['Specifications'] = result['proposed']['Tables']['Products'][0]['Specifications']
    with pytest.raises(phase_b.GuardError, match='edited'):
        phase_b.records_for(before, result['proposed'], result['changes'], current)


@pytest.fixture
def run(tmp_path, monkeypatch):
    inputs, before, result = review_inputs(two_products())
    source = tmp_path / 'source'
    source.mkdir()
    for name, data in inputs.items():
        (source / name).write_bytes(data)
    target = {'Provider': 'supabase', 'Fingerprint': 'test-target'}
    monkeypatch.setattr(phase_b, 'target_identity', lambda: target)
    monkeypatch.setattr(phase_b, 'capture', lambda: copy.deepcopy(before))
    monkeypatch.setattr(phase_b, 'validate_consumers', lambda *_: {'Offline': True})
    folder = phase_b.prepare(source, source / 'evidence.json', tmp_path / 'phase-b', 4, 2)
    return SimpleNamespace(folder=folder, before=before, result=result, target=target)


@pytest.mark.parametrize('file', ['inputs/catalog-changes.csv', 'inputs/evidence.json', 'plan.json', 'preflight.json'])
def test_frozen_run_rejects_modified_files(run, file):
    path = run.folder / file
    data = path.read_bytes()
    path.write_bytes(data.replace(b'16GB', b'64GB') if b'16GB' in data else data + b' ')
    with pytest.raises((phase_b.GuardError, ValueError)):
        phase_b.load_run(run.folder)


def test_prepared_run_rejects_a_changed_connection_target(run, monkeypatch):
    monkeypatch.setattr(phase_b, 'target_identity', lambda: {'Provider': 'supabase', 'Fingerprint': 'other'})
    with pytest.raises(phase_b.GuardError, match='target changed'):
        phase_b.load_run(run.folder)


def test_backup_is_exclusive_and_never_overwrites(tmp_path):
    path = tmp_path / 'before.json'
    phase_b.save_json(path, {'original': 'keep'})
    with pytest.raises(FileExistsError):
        phase_b.save_json(path, {'original': 'lost'})
    assert phase_b.read_json(path) == {'original': 'keep'}


@pytest.fixture
def database(run, monkeypatch):
    """Emulate isolation/commit, CAS and failure injection; no SQL driver is connected."""
    import sqlalchemy
    import sqlalchemy.orm
    import app.core.env

    state = SimpleNamespace(live=copy.deepcopy(run.before), commits=0, updates=0, fail_after_first=False,
                            corrupt_after_update=False, ambiguous_commit=False, fail_cas=False)

    class Rows(list):
        def all(self):
            return list(self)

    class Session:
        def __init__(self, *_args, **_kwargs):
            self.workspace = copy.deepcopy(state.live)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass  # Uncommitted workspace is discarded.

        def execute(self, *_args):
            pass

        def scalar(self, *_args):
            return 'off'

        def scalars(self, sql, params):
            if 'FOR UPDATE' in str(sql):
                return Rows(sorted(p['ProductId'] for p in self.workspace['Tables']['Products'] if p['ProductId'] in params['ids']))
            assert str(sql) == phase_b.BATCH_UPDATE
            # Every recovery file must exist before even the first simulated row update.
            prefix = 'rollback-' if (run.folder / 'rollback-receipt.json').exists() else 'transaction-'
            assert (run.folder / (prefix + 'before.json')).exists()
            assert phase_b.read_json(run.folder / ('rollback-receipt.json' if prefix == 'rollback-' else 'receipt.json'))['Status'] == 'backup_ready'
            updated = Rows()
            by_id = {p['ProductId']: p for p in self.workspace['Tables']['Products']}
            for index, patch in enumerate(json.loads(params['patches'])):
                p = by_id[patch['ProductId']]
                if state.fail_cas and index == 0:
                    continue
                if p['Specifications'] == patch['Before'] and p['UpdatedAt'] == patch['UpdatedAt']:
                    p['Specifications'] = patch['After']
                    p['UpdatedAt'] = f'2026-10-29T0{state.commits + 1}:00:00+07:00'
                    updated.append(p['ProductId'])
                    state.updates += 1
                if state.fail_after_first:
                    raise RuntimeError('simulated connection loss before commit')
            if state.corrupt_after_update:
                self.workspace['Tables']['ProductVariants'][0]['Price'] = '1'
            self.workspace['CatalogFingerprint'] = phase_b.digest(self.workspace['Tables'])
            return updated

        def commit(self):
            state.live = copy.deepcopy(self.workspace)
            state.commits += 1
            if state.ambiguous_commit:
                raise ConnectionError('simulated lost COMMIT response')

    monkeypatch.setattr(sqlalchemy, 'create_engine', lambda *_args, **_kwargs: SimpleNamespace(dispose=lambda: None))
    monkeypatch.setattr(sqlalchemy.orm, 'Session', Session)
    monkeypatch.setattr(app.core.env, 'database_url', lambda: 'postgresql://unused')
    monkeypatch.setattr(phase_b, 'snapshot_in_transaction', lambda db: copy.deepcopy(db.workspace))
    monkeypatch.setattr(phase_b, 'capture', lambda: copy.deepcopy(state.live))
    return state


def test_apply_commits_exact_values_once_then_select_verifies(run, database):
    receipt = phase_b.apply_run(run.folder)
    assert receipt['Status'] == 'committed' and receipt['ProductUpdates'] == 2 and receipt['ValueChanges'] == 4
    assert database.commits == 1 and database.updates == 2
    assert database.live['Tables']['ProductVariants'] == run.before['Tables']['ProductVariants']
    assert receipt['Checks']['AutomaticUpdatedAtProducts'] == 2
    assert phase_b.verify_run(run.folder)['MatchesCommittedTargetRows']
    with pytest.raises(phase_b.GuardError, match='not prepared'):
        phase_b.apply_run(run.folder)
    assert database.commits == 1 and database.updates == 2


@pytest.mark.parametrize('failure', ['fail_after_first', 'corrupt_after_update', 'fail_cas', 'stale_timestamp'])
def test_any_failure_rolls_back_every_row(run, database, failure):
    if failure == 'stale_timestamp':
        database.live['Tables']['Products'][0]['UpdatedAt'] = '2026-10-29T00:30:00+07:00'
    else:
        setattr(database, failure, True)
    before = copy.deepcopy(database.live)
    with pytest.raises((ValueError, RuntimeError)):
        phase_b.apply_run(run.folder)
    assert database.live == before and database.commits == 0
    assert phase_b.read_json(run.folder / 'receipt.json')['Status'] == 'rolled_back'


def test_lost_commit_response_is_resolved_by_select_without_replaying_writes(run, database):
    database.ambiguous_commit = True
    with pytest.raises(ConnectionError):
        phase_b.apply_run(run.folder)
    assert phase_b.read_json(run.folder / 'receipt.json')['Status'] == 'commit_unknown'
    assert phase_b.verify_run(run.folder)['MatchesCommittedTargetRows']
    assert phase_b.read_json(run.folder / 'receipt.json')['Status'] == 'committed_verified'
    assert database.commits == 1 and database.updates == 2


def test_rollback_restores_only_original_specs_and_does_not_write_old_timestamps(run, database):
    phase_b.apply_run(run.folder)
    # A later stock/price change is independent and must survive rollback.
    database.live['Tables']['ProductVariants'][0].update(Price='17000000', StockQuantity=9)
    receipt = phase_b.rollback_run(run.folder)
    assert receipt['Status'] == 'committed' and database.commits == 2
    for old, current in zip(run.before['Tables']['Products'], database.live['Tables']['Products']):
        assert old['Specifications'] == current['Specifications']
        assert old['UpdatedAt'] != current['UpdatedAt']
        assert current['UpdatedAt'] == '2026-10-29T02:00:00+07:00'
    assert database.live['Tables']['ProductVariants'][0]['Price'] == '17000000'
    assert database.live['Tables']['ProductVariants'][0]['StockQuantity'] == 9
    assert phase_b.verify_run(run.folder, rollback=True)['MatchesCommittedTargetRows']


@pytest.mark.parametrize('edit', ['same_value_new_timestamp', 'different_spec', 'description'])
def test_rollback_refuses_to_overwrite_later_product_edits(run, database, edit):
    phase_b.apply_run(run.folder)
    p = database.live['Tables']['Products'][0]
    if edit == 'same_value_new_timestamp':
        p['UpdatedAt'] = '2026-10-29T01:30:00+07:00'
    elif edit == 'different_spec':
        p['Specifications']['Dung lượng RAM'] = '64 GB'
    else:
        p['Description'] = 'new description'
    before = copy.deepcopy(database.live)
    with pytest.raises(phase_b.GuardError, match='changed since preparation'):
        phase_b.rollback_run(run.folder)
    assert database.live == before and database.commits == 1


@pytest.mark.parametrize('edit', ['key', 'type', 'private', 'price', 'stock', 'schema', 'cost', 'untargeted_timestamp'])
def test_transition_rejects_every_unapproved_difference(edit):
    _, before, result = review_inputs()
    records = phase_b.records_for(before, result['proposed'], result['changes'], before)
    after = copy.deepcopy(result['proposed'])
    p = after['Tables']['Products'][0]
    p['UpdatedAt'] = '2026-10-29T01:00:00+07:00'
    if edit == 'key':
        p['Specifications']['New'] = 'value'
    elif edit == 'type':
        p['Specifications']['Dung lượng RAM'] = 16
    elif edit == 'private':
        p['Specifications']['_vietech_variant_media']['DefaultVariantId'] = 'changed'
    elif edit in ('price', 'stock'):
        after['Tables']['ProductVariants'][0]['Price' if edit == 'price' else 'StockQuantity'] = 0
    elif edit in ('schema', 'cost'):
        after['SchemaFingerprint' if edit == 'schema' else 'ProtectedCostFingerprint'] = 'changed'
    else:
        other = copy.deepcopy(before['Tables']['Products'][0])
        other.update(ProductId=str(uuid.uuid4()), Slug='other')
        before['Tables']['Products'].append(other)
        after['Tables']['Products'].append({**other, 'UpdatedAt': '2026-10-29T01:00:00+07:00'})
    with pytest.raises(ValueError):
        phase_b.validate_transition(before, after, result['changes'], records)


def test_batch_sql_only_sets_specs_uses_bound_json_and_compares_original_timestamp():
    from sqlalchemy import text
    from sqlalchemy.dialects import postgresql

    statement = str(text(phase_b.BATCH_UPDATE).compile(dialect=postgresql.dialect()))
    assert 'SET "Specifications" = change."After"' in statement
    assert '%(patches)s' in statement
    assert 'p."Specifications" = change."Before"' in statement
    assert 'p."UpdatedAt" IS NOT DISTINCT FROM change."UpdatedAt"' in statement
    assert 'ALTER' not in statement and 'INSERT' not in statement and 'DELETE' not in statement
