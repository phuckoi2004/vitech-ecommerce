"""Description/specification updates are atomic, bounded and recoverable, with no shared database."""
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import enrich_catalog_details as details
from tests.test_apply_catalog_standardization import two_products


def proof(snapshot):
    return {'Products':[{'Name':row['Name'], 'Sources':['https://www.msi.com/verified/specifications'],
                         'Scope':'Exact fixture model', 'Fields':{'Dung lượng RAM':'32 GB'},
                         'DescriptionFacts':['USB-C chỉ truyền tệp, không xuất hình.']}
                        for row in snapshot['Tables']['Products']]}


def test_description_retains_images_escapes_values_and_keeps_private_media_out():
    original = '<p>Mô tả cũ; phần tiếp theo &amp; ảnh.</p><p><img src="https://example.com/a;b.png" alt="Máy"></p>'
    result = details.detailed_description(original, {'RAM':'16 GB', 'Cổng':'USB-C; không xuất hình',
        '_vietech_variant_media':{'secret':'keep'}, 'Nội dung':'<script>wrong</script>'},
        {'DescriptionFacts':['Không tự đoán; cần kiểm tra cáp.']})
    assert '<img src="https://example.com/a;b.png" alt="Máy">' in result
    assert 'Mô tả cũ, phần tiếp theo &amp; ảnh.' in result
    assert 'USB-C' not in result and 'Không tự đoán, cần kiểm tra cáp.' in result
    assert '_vietech_variant_media' not in result and 'secret' not in result
    assert details.MARKER not in result and '<ul>' not in result
    assert '16 GB' not in result and '<script>' not in result


@pytest.mark.parametrize('change', ['new_key', 'removed_key', 'type', 'list', 'private'])
def test_specification_shape_and_private_media_are_preserved(change):
    old = {'RAM':'16 GB', 'Nested':[{'value':'kept'}], '_vietech_variant_media':{'DefaultVariantId':'kept'}}
    new = copy.deepcopy(old)
    if change == 'new_key': new['GPU'] = 'new'
    elif change == 'removed_key': del new['RAM']
    elif change == 'type': new['RAM'] = 16
    elif change == 'list': new['Nested'].append({'value':'new'})
    else: new['_vietech_variant_media']['DefaultVariantId'] = 'changed'
    with pytest.raises(details.GuardError): details.same_shape(old, new)


@pytest.mark.parametrize('url', ['http://www.msi.com/specs', 'https://msi.com.attacker.example/specs',
                                'https://fake-msi.com/specs', 'https://attacker.example/msi.com/specs'])
def test_unreviewed_or_lookalike_source_hosts_cannot_authorize_updates(url):
    snapshot = two_products()
    evidence = proof(snapshot)
    evidence['Products'][0]['Sources'] = [url]
    with pytest.raises(details.GuardError, match='source host'): details.make_plan(snapshot, evidence)


@pytest.mark.parametrize('field', ['New GPU', '_vietech_variant_media'])
def test_only_preexisting_public_string_values_may_be_updated(field):
    snapshot = two_products()
    evidence = proof(snapshot)
    evidence['Products'][0]['Fields'] = {field:'new'}
    with pytest.raises(details.GuardError, match='existing public string'): details.make_plan(snapshot, evidence)


@pytest.mark.parametrize('change', ['price', 'stock', 'sku', 'media', 'name', 'category', 'image', 'schema', 'cost'])
def test_transaction_verification_rejects_every_protected_change(change):
    before = two_products()
    plan = details.make_plan(before, proof(before))
    after = copy.deepcopy(before)
    for row, record in zip(after['Tables']['Products'], plan['Records']):
        row.update(Description=record['Description'], Specifications=record['Specifications'], UpdatedAt='2026-10-30T00:00:00+07:00')
    assert details.validate_transition(before, after, plan['Records'])['OtherCatalogFieldsUnchanged']
    row = after['Tables']['Products'][0]
    if change in ('price', 'stock', 'sku'):
        after['Tables']['ProductVariants'][0][{'price':'Price','stock':'StockQuantity','sku':'Sku'}[change]] = 'changed'
    elif change == 'media': row['Specifications']['_vietech_variant_media']['DefaultVariantId'] = 'changed'
    elif change == 'name': row['Name'] = 'changed'
    elif change == 'category': row['CategoryId'] = 'changed'
    elif change == 'image': after['Tables']['ProductImages'].append({'ImageUrl':'changed'})
    elif change == 'schema': after['SchemaFingerprint'] = 'changed'
    else: after['ProtectedCostFingerprint'] = 'changed'
    with pytest.raises(details.GuardError): details.validate_transition(before, after, plan['Records'])


@pytest.fixture
def run(tmp_path, monkeypatch):
    snapshot = two_products()
    source, evidence_path = tmp_path / 'source.json', tmp_path / 'proof.json'
    details.save_json(source, snapshot)
    details.save_json(evidence_path, proof(snapshot))
    monkeypatch.setattr(details, 'check_target', lambda: {'Fingerprint':'offline'})
    details.prepare(source, evidence_path, tmp_path / 'runs')
    folder = next((tmp_path / 'runs').iterdir())
    return SimpleNamespace(folder=folder, before=snapshot)


@pytest.fixture
def database(run, monkeypatch):
    import sqlalchemy
    import sqlalchemy.orm
    import app.core.env
    state = SimpleNamespace(live=copy.deepcopy(run.before), commits=0, fail_cas=False, ambiguous=False, description_only=0)
    class Rows(list):
        def all(self): return self
    class Session:
        def __init__(self, *_args, **_kwargs): self.workspace = copy.deepcopy(state.live)
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, *_args, **_kwargs): pass
        def scalars(self, sql, params):
            if 'FOR UPDATE' in str(sql): return Rows(params['ids'])
            assert str(sql) in (details.UPDATE, details.UPDATE_DESCRIPTION)
            if str(sql) == details.UPDATE_DESCRIPTION:
                state.description_only += 1
            prefix = 'rollback-' if (run.folder / 'rollback-receipt.json').exists() else 'transaction-'
            assert (run.folder / (prefix + 'before.json')).exists()
            updated = Rows()
            by_id = {row['ProductId']:row for row in self.workspace['Tables']['Products']}
            for index, patch in enumerate(json.loads(params['patches'])):
                if state.fail_cas and index == 0: continue
                row = by_id[patch['ProductId']]
                assert row['Description'] == patch['BeforeDescription']
                assert row['Specifications'] == patch['BeforeSpecifications']
                assert row['UpdatedAt'] == patch['UpdatedAt']
                row.update(Description=patch['Description'], Specifications=patch['Specifications'],
                           UpdatedAt=f'2026-10-30T0{state.commits+1}:00:00+07:00')
                updated.append(row['ProductId'])
            self.workspace['CatalogFingerprint'] = details.digest(self.workspace['Tables'])
            return updated
        def commit(self):
            state.live = copy.deepcopy(self.workspace)
            state.commits += 1
            if state.ambiguous: raise ConnectionError('lost commit reply')
    monkeypatch.setattr(sqlalchemy, 'create_engine', lambda *_args, **_kwargs: SimpleNamespace(dispose=lambda: None))
    monkeypatch.setattr(sqlalchemy.orm, 'Session', Session)
    monkeypatch.setattr(app.core.env, 'database_url', lambda: 'postgresql://unused')
    monkeypatch.setattr(details, 'snapshot_in_transaction', lambda db: copy.deepcopy(db.workspace))
    monkeypatch.setattr(details, 'capture', lambda: copy.deepcopy(state.live))
    return state


def test_batch_commits_once_verifies_and_rejects_reapply(run, database):
    assert details.apply(run.folder)['Status'] == 'committed'
    assert database.commits == 1
    assert details.verify(run.folder)['MatchesCommittedRows']
    assert database.live['Tables']['ProductVariants'] == run.before['Tables']['ProductVariants']
    with pytest.raises(details.GuardError, match='already attempted'): details.apply(run.folder)
    assert database.commits == 1


@pytest.mark.parametrize('failure', ['stale', 'partial_cas'])
def test_stale_or_partially_accepted_updates_never_commit(run, database, failure):
    if failure == 'stale': database.live['Tables']['Products'][0]['Description'] = 'newer edit'
    else: database.fail_cas = True
    before = copy.deepcopy(database.live)
    with pytest.raises(details.GuardError): details.apply(run.folder)
    assert database.live == before and database.commits == 0
    assert details.read_json(run.folder / 'receipt.json')['Status'] == 'rolled_back'


def test_ambiguous_commit_is_resolved_by_select_and_never_replayed(run, database):
    database.ambiguous = True
    with pytest.raises(ConnectionError): details.apply(run.folder)
    assert details.read_json(run.folder / 'receipt.json')['Status'] == 'commit_unknown'
    assert details.verify(run.folder)['MatchesCommittedRows'] and database.commits == 1


def test_rollback_restores_descriptions_and_specs_but_keeps_newer_stock(run, database):
    details.apply(run.folder)
    database.live['Tables']['ProductVariants'][0]['StockQuantity'] = 9
    assert details.apply(run.folder, rollback=True)['Status'] == 'committed'
    assert details.verify(run.folder, rollback=True)['MatchesCommittedRows']
    for old, row in zip(run.before['Tables']['Products'], database.live['Tables']['Products']):
        assert old['Description'] == row['Description'] and old['Specifications'] == row['Specifications']
        assert old['UpdatedAt'] != row['UpdatedAt']
    assert database.live['Tables']['ProductVariants'][0]['StockQuantity'] == 9


def test_rollback_preserves_later_description_edits(run, database):
    details.apply(run.folder)
    database.live['Tables']['Products'][0]['Description'] = 'later description'
    before = copy.deepcopy(database.live)
    with pytest.raises(details.GuardError): details.apply(run.folder, rollback=True)
    assert database.live == before and database.commits == 1


def test_modified_frozen_plan_cannot_authorize_a_database_update(run, database):
    plan = details.read_json(run.folder / 'plan.json')
    plan['Records'][0]['Specifications']['Dung lượng RAM'] = '64 GB'
    details.save_json(run.folder / 'plan.json', plan, replace=True)
    with pytest.raises(details.GuardError, match='Frozen recovery input changed'): details.apply(run.folder)
    assert database.commits == 0


def cleanup_example():
    before = two_products()
    legacy = details.make_plan(before, proof(before), include_technical_details=True)
    current = copy.deepcopy(before)
    appendices = []
    for row, record in zip(current['Tables']['Products'], legacy['Records']):
        row.update(Description=record['Description'], Specifications=record['Specifications'])
        suffix = details.MARKER + record['Description'].split(details.MARKER, 1)[1]
        appendices.append({'ProductId':record['ProductId'], 'Suffix':suffix})
    return current, {'Operation':'remove_redundant_specs', 'Appendices':appendices}


def test_cleanup_keeps_new_specs_narrative_facts_images_and_later_prefix_edits():
    current, evidence = cleanup_example()
    added = '<p>Nội dung giới thiệu đã chỉnh thêm.</p><img src="/new.jpg" alt="Ảnh">'
    current['Tables']['Products'][0]['Description'] = added + current['Tables']['Products'][0]['Description']
    untouched = copy.deepcopy(current)
    plan = details.make_removal_plan(current, evidence)
    assert current == untouched and plan['SpecificationChanges'] == []
    assert plan['Records'][0]['Description'].startswith(added)
    for record, row in zip(plan['Records'], current['Tables']['Products']):
        assert details.MARKER not in record['Description']
        assert 'USB-C chỉ truyền tệp, không xuất hình.' in record['Description']
        assert record['Specifications'] == row['Specifications']
        assert record['Specifications']['Dung lượng RAM'] == '32 GB'


@pytest.mark.parametrize('edit', ['changed_suffix', 'content_after_suffix', 'already_removed'])
def test_cleanup_refuses_to_remove_changed_or_ambiguous_sections(edit):
    current, evidence = cleanup_example()
    row = current['Tables']['Products'][0]
    if edit == 'changed_suffix': row['Description'] = row['Description'].replace('<li>', '<li>Biên tập mới ', 1)
    elif edit == 'content_after_suffix': row['Description'] += '<p>Nội dung sau bảng cần giữ.</p>'
    else: row['Description'] = row['Description'].split(details.MARKER, 1)[0]
    with pytest.raises(details.GuardError, match='changed after enrichment'):
        details.make_removal_plan(current, evidence)


def test_cleanup_transaction_only_updates_descriptions_and_preserves_new_specs(run, database, tmp_path):
    current, evidence = cleanup_example()
    current['CatalogFingerprint'] = details.digest(current['Tables'])
    plan = details.make_removal_plan(current, evidence)
    details.freeze_plan(current, evidence, plan, tmp_path / 'cleanup')
    folder = next((tmp_path / 'cleanup').iterdir())
    run.folder = folder
    database.live = copy.deepcopy(current)
    assert details.apply(folder)['Status'] == 'committed'
    assert database.description_only == 1 and database.commits == 1
    assert details.verify(folder)['MatchesCommittedRows']
    assert database.live['Tables']['ProductVariants'] == current['Tables']['ProductVariants']
    for row, old in zip(database.live['Tables']['Products'], current['Tables']['Products']):
        assert row['Specifications'] == old['Specifications']
        assert details.MARKER not in row['Description']


def scoped_example():
    snapshot = two_products()
    row = snapshot['Tables']['Products'][0]
    row['Description'] = '<p>Giới thiệu.</p><h2>Hiệu năng</h2><p>CPU.</p><h2>Camera</h2><p><img src="/a.jpg"></p>'
    evidence = {'Operation': 'enrich_scoped_content', 'Products': [{
        'ProductId': row['ProductId'], 'Name': row['Name'], 'Scope': 'Exact reviewed fixture',
        'Sources': ['https://www.asus.com/vn/specs/'],
        'DescriptionEdits': [{'Before': '<p>CPU.</p>', 'After': '<p>CPU và RAM 12 GB.</p>'}]}]}
    snapshot['CatalogFingerprint'] = details.digest(snapshot['Tables'])
    return snapshot, evidence


def test_scoped_content_changes_only_reviewed_products_and_preserves_section_and_image_order():
    snapshot, evidence = scoped_example()
    original = copy.deepcopy(snapshot)
    plan = details.make_scoped_content_plan(snapshot, evidence)
    assert snapshot == original and len(plan['Records']) == 1
    assert plan['DescriptionUpdates'] == 1 and plan['SpecificationChanges'] == []
    record = plan['Records'][0]
    assert record['Specifications'] == snapshot['Tables']['Products'][0]['Specifications']
    assert '<h2>Hiệu năng</h2><p>CPU và RAM 12 GB.</p><h2>Camera</h2>' in record['Description']
    assert '<img src="/a.jpg">' in record['Description'] and details.MARKER not in record['Description']


@pytest.mark.parametrize('failure', ['identity', 'duplicate', 'source', 'scope', 'new_key', 'private',
    'stale_anchor', 'duplicate_anchor', 'image', 'section', 'script', 'punctuation', 'no_change'])
def test_scoped_content_refuses_unreviewed_or_structural_edits(failure):
    snapshot, evidence = scoped_example()
    item = evidence['Products'][0]
    edit = item['DescriptionEdits'][0]
    row = snapshot['Tables']['Products'][0]
    if failure == 'identity': item['Name'] = 'another model'
    elif failure == 'duplicate': evidence['Products'].append(copy.deepcopy(item))
    elif failure == 'source': item['Sources'] = ['https://asus.com.attacker.example/specs']
    elif failure == 'scope': del item['Scope']
    elif failure == 'new_key': item['Fields'] = {'New RAM': '12 GB'}
    elif failure == 'private': item['Fields'] = {'_vietech_variant_media': 'changed'}
    elif failure == 'stale_anchor': edit['Before'] = '<p>newer prose</p>'
    elif failure == 'duplicate_anchor': row['Description'] += edit['Before']
    elif failure == 'image': edit.update(Before='<img src="/a.jpg">', After='<img src="/other.jpg">')
    elif failure == 'section': edit['After'] += '<h2>Other topic</h2>'
    elif failure == 'script': edit['After'] += '<script>alert(1)</script>'
    elif failure == 'punctuation': edit['After'] = '<p>CPU, RAM; camera.</p>'
    else: item['DescriptionEdits'] = []
    with pytest.raises(details.GuardError): details.make_scoped_content_plan(snapshot, evidence)


def test_scoped_content_rejects_repeat_application_and_accepts_explicit_primary_teardown_only():
    snapshot, evidence = scoped_example()
    item = evidence['Products'][0]
    item['Sources'] = ['https://www.ifixit.com/Teardown/Model+Chip+ID/123']
    with pytest.raises(details.GuardError, match='source host'): details.make_scoped_content_plan(snapshot, evidence)
    item['SourceKind'] = 'primary_teardown'
    plan = details.make_scoped_content_plan(snapshot, evidence)
    snapshot['Tables']['Products'][0]['Description'] = plan['Records'][0]['Description']
    with pytest.raises(details.GuardError, match='anchor'): details.make_scoped_content_plan(snapshot, evidence)
    for source in ['https://www.ifixit.com/Device/Model', 'https://www.ifixit.com.attacker.example/Teardown/Model/123']:
        item['Sources'] = [source]
        with pytest.raises(details.GuardError, match='source host'): details.make_scoped_content_plan(snapshot, evidence)


@pytest.mark.parametrize('specification_edit', [False, True])
def test_scoped_content_frozen_batch_commits_and_preserves_other_products(run, database, tmp_path, specification_edit):
    snapshot, evidence = scoped_example()
    if specification_edit:
        evidence['Products'][0]['Fields'] = {'Dung lượng RAM': '32 GB'}
    plan = details.make_scoped_content_plan(snapshot, evidence)
    details.freeze_plan(snapshot, evidence, plan, tmp_path / 'scoped')
    folder = next((tmp_path / 'scoped').iterdir())
    run.folder = folder
    database.live = copy.deepcopy(snapshot)
    details.apply(folder)
    assert details.verify(folder)['MatchesCommittedRows'] and database.commits == 1
    assert database.live['Tables']['Products'][1] == snapshot['Tables']['Products'][1]
    assert database.description_only == (0 if specification_edit else 1)
    if specification_edit:
        assert database.live['Tables']['Products'][0]['Specifications']['Dung lượng RAM'] == '32 GB'
    else:
        assert database.live['Tables']['Products'][0]['Specifications'] == snapshot['Tables']['Products'][0]['Specifications']


def vietnam_example():
    snapshot, evidence = scoped_example()
    item = evidence['Products'][0]
    item.update(SourceKind='vietnam_crosscheck', Sources=['https://fptshop.com.vn/dien-thoai/test'],
                VietnamSources=['https://fptshop.com.vn/dien-thoai/test'], VariantScope='Exact VN/A fixture',
                VerificationBasis='direct_vn_listing')
    return snapshot, evidence


@pytest.mark.parametrize('failure', ['foreign_only', 'unlinked', 'spoof', 'http', 'identity', 'basis', 'report_spoof'])
def test_vietnam_crosscheck_requires_linked_local_sources_and_exact_scope(failure):
    snapshot, evidence = vietnam_example()
    item = evidence['Products'][0]
    if failure == 'foreign_only': item['VietnamSources'] = ['https://www.asus.com/uk/specs/']
    elif failure == 'unlinked': item['VietnamSources'] = ['https://fptshop.com.vn/dien-thoai/unreviewed']
    elif failure == 'spoof': item['Sources'] = item['VietnamSources'] = ['https://fptshop.com.vn.attacker.example/product']
    elif failure == 'http': item['Sources'] = item['VietnamSources'] = ['http://fptshop.com.vn/dien-thoai/test']
    elif failure == 'identity': del item['VariantScope']
    elif failure == 'basis': del item['VerificationBasis']
    else: item['Sources'].append(details.XCODE_RAM_REPORT + 'unreviewed')
    with pytest.raises(details.GuardError): details.make_scoped_content_plan(snapshot, evidence)


def test_vietnam_crosscheck_allows_reviewed_original_xcode_report_with_local_variant():
    snapshot, evidence = vietnam_example()
    evidence['Products'][0]['Sources'].append(details.XCODE_RAM_REPORT)
    assert len(details.make_scoped_content_plan(snapshot, evidence)['Records']) == 1
