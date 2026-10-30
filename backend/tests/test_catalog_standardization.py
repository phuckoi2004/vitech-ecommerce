"""Value-only Phase A proposals: no shared database or external manufacturer access."""
import copy
import csv
import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from catalog_standardization import (AI_TEXT_WINDOWS, audit, digest, normalize_value, pointer, shape,
                                     source_candidates, validate_consumers, validate_proposal, write_reports)


def original(specs=None):
    pid, vid, cid, bid = (str(uuid.uuid4()) for _ in range(4))
    tables = {
        'Products': [{'ProductId': pid, 'CategoryId': cid, 'BrandId': bid, 'Name': 'Test Laptop', 'Slug': 'test-laptop',
                      'Specifications': specs if specs is not None else {'Dung lượng RAM': '16GB', 'Ổ cứng': '512GB',
                        '_vietech_variant_media': {'DefaultVariantId': vid, 'Variants': {vid: {'ImageUrls': ['/16GB.png']}}}},
                      'Description': None, 'Status': 'Active', 'WarrantyMonths': 12, 'AverageRating': '0',
                      'ReviewCount': 0, 'SoldQuantity': 0, 'IsDeleted': False,
                      'CreatedAt': '2026-10-29T00:00:00+07:00', 'UpdatedAt': '2026-10-29T00:00:00+07:00'}],
        'ProductVariants': [{'ProductVariantId': vid, 'ProductId': pid, 'Sku': 'SKU-KEEP', 'VariantName': '16GB / 512GB',
                             'Color': None, 'Storage': '512 GB', 'Price': '15000000', 'CompareAtPrice': None,
                             'StockQuantity': 3, 'IsActive': True, 'IsDeleted': False}],
        'Categories': [{'CategoryId': cid, 'Name': 'Laptop', 'Slug': 'laptop', 'ParentCategoryId': None}],
        'Brands': [{'BrandId': bid, 'Name': 'Test Brand', 'Slug': 'test-brand'}], 'ProductImages': [],
    }
    return {'Source': 'configured_postgresql_live_select', 'ReadOnly': True, 'CapturedAt': '2026-10-29',
            'Counts': {key: len(rows) for key, rows in tables.items()}, 'SchemaFingerprint': 'schema-keep',
            'ProtectedCostFingerprint': 'protected-cost-keep', 'CatalogFingerprint': digest(tables), 'Tables': tables}


def evidence(snapshot, *, key='Dung lượng RAM', before='16GB', new='32 GB', **overrides):
    product = snapshot['Tables']['Products'][0]
    return {'SnapshotFingerprint': snapshot['CatalogFingerprint'], 'Values': [{
        'ProductId': product['ProductId'], 'ProductName': product['Name'], 'Path': pointer((key,)), 'Before': before,
        'Proposed': new, 'Decision': 'correction', 'SourceURL': 'https://www.asus.com/model/verified-specs/',
        'VerifiedAt': '2026-10-29', 'Confidence': 'high', 'ModelMatch': 'exact', 'RegionScope': 'VN',
        'Reason': 'Test reviewed manufacturer fact', **overrides}]}


@pytest.mark.parametrize(('old', 'new'), [
    ('16GB', '16 GB'), ('1TB SSD', '1 TB SSD'), ('5000mAh', '5000 mAh'), ('144Hz', '144 Hz'),
    ('14 inches', '14 inch'), ('  42Wh ', '42 Wh'), ('59g', '59 g'), ('2.4Ghz', '2.4 GHz'),
    ('10Gb/s', '10Gb/s'), ('60GB/s', '60 GB/s'), ('USB-C 3.2 Gen 2', 'USB-C 3.2 Gen 2'),
    ('M.2 2280 PCIe 4.0x4', 'M.2 2280 PCIe 4.0x4'), ('4G/5G', '4G/5G'),
    ('10.100 mAh', '10.100 mAh'), ('S32CG552EEXXV', 'S32CG552EEXXV'),
])
def test_unit_formatting_preserves_numbers_bits_bytes_and_model_codes(old, new):
    assert normalize_value(old) == new
    assert normalize_value(new) == new


def test_phase_a_does_not_mutate_input_keys_media_or_protected_tables():
    before = original()
    frozen = copy.deepcopy(before)
    result = audit(before, {'Values': []})
    assert before == frozen
    assert result['summary']['FormatProposals'] == 2
    assert result['proposed']['Tables']['Products'][0]['Specifications']['Dung lượng RAM'] == '16 GB'
    assert shape(before) == shape(result['proposed'])
    assert validate_proposal(before, result['proposed'], result['changes'])
    assert result['summary']['DatabaseWrites'] == 0


@pytest.mark.parametrize('change', ['key', 'type', 'id', 'slug', 'sku', 'price', 'stock', 'category', 'brand',
                                   'warranty', 'media', 'nested_private', 'schema', 'cost', 'row', 'unlisted'])
def test_guard_rejects_forbidden_proposal_changes(change):
    before = original({'Dung lượng RAM': '16GB', '_vietech_variant_media': {'ImageUrls': ['/16GB.png']},
                       'Nested': {'_private': '16GB'}})
    result = audit(before, {'Values': []})
    after = result['proposed']
    p, v = after['Tables']['Products'][0], after['Tables']['ProductVariants'][0]
    if change == 'key':
        p['Specifications']['RAM mới'] = '16 GB'
    elif change == 'type':
        p['Specifications']['Dung lượng RAM'] = 16
    elif change == 'id':
        p['ProductId'] = str(uuid.uuid4())
    elif change == 'slug':
        p['Slug'] = 'changed'
    elif change == 'sku':
        v['Sku'] = 'changed'
    elif change == 'price':
        v['Price'] = '1'
    elif change == 'stock':
        v['StockQuantity'] = 42
    elif change == 'category':
        p['CategoryId'] = str(uuid.uuid4())
    elif change == 'brand':
        p['BrandId'] = str(uuid.uuid4())
    elif change == 'warranty':
        p['WarrantyMonths'] = 99
    elif change == 'media':
        p['Specifications']['_vietech_variant_media']['ImageUrls'] = ['/changed.png']
    elif change == 'nested_private':
        p['Specifications']['Nested']['_private'] = 'changed'
    elif change == 'schema':
        after['SchemaFingerprint'] = 'changed'
    elif change == 'cost':
        after['ProtectedCostFingerprint'] = 'changed'
    elif change == 'row':
        after['Tables']['Products'].append(copy.deepcopy(p))
    elif change == 'unlisted':
        p['Specifications']['Dung lượng RAM'] = '32 GB'
    with pytest.raises(ValueError):
        validate_proposal(before, after, result['changes'])


@pytest.mark.parametrize('override', [
    {'Before': '8GB'}, {'ProductName': 'Near Model'}, {'ProductId': str(uuid.uuid4())},
    {'Path': '/Missing key'}, {'SourceURL': 'https://www.asus.com.attacker.example/specs'},
    {'SourceURL': 'http://www.asus.com/specs'}, {'ModelMatch': 'family_only'},
    {'RegionScope': ''}, {'Confidence': 'guess'}, {'VerifiedAt': ''},
])
def test_content_change_requires_exact_snapshot_identity_and_verified_manufacturer(override):
    before = original()
    with pytest.raises(ValueError):
        audit(before, evidence(before, **override))


def test_verified_content_changes_only_existing_value_and_records_provenance():
    before = original()
    result = audit(before, evidence(before))
    assert result['summary']['VerifiedErrors'] == 1
    assert result['proposed']['Tables']['Products'][0]['Specifications']['Dung lượng RAM'] == '32 GB'
    row = next(r for r in result['changes'] if r['Classification'] == 'verified_correction')
    assert row['Before'] == '16GB' and row['SourceURL'].startswith('https://www.asus.com/')
    assert row['VerifiedAt'] == '2026-10-29' and row['ModelMatch'] == 'exact'


def test_format_classification_cannot_hide_a_technical_value_change():
    before = original()
    result = audit(before, {'Values': []})
    row = next(r for r in result['changes'] if r['Attribute'] == 'Dung lượng RAM')
    row['Proposed'] = '32 GB'
    result['proposed']['Tables']['Products'][0]['Specifications']['Dung lượng RAM'] = '32 GB'
    with pytest.raises(ValueError, match='Format-only'):
        validate_proposal(before, result['proposed'], result['changes'])


def test_stale_or_duplicate_evidence_and_changed_original_fail_closed():
    before = original()
    source = evidence(before)
    source['SnapshotFingerprint'] = 'old-snapshot'
    with pytest.raises(ValueError, match='different snapshot'):
        audit(before, source)
    source = evidence(before)
    source['Values'] *= 2
    with pytest.raises(ValueError, match='Duplicate evidence'):
        audit(before, source)
    before['Tables']['ProductVariants'][0]['Price'] = '1'
    with pytest.raises(ValueError, match='fingerprint'):
        audit(before, {'Values': []})


def test_empty_fields_and_missing_attributes_are_reported_without_creating_keys():
    before = original({'Pin': '', 'Cổng giao tiếp': 'USB-C; HDMI 2.1'})
    result = audit(before, {'Values': []})
    assert result['proposed']['Tables']['Products'][0]['Specifications'] == before['Tables']['Products'][0]['Specifications']
    assert any(r['Code'] == 'missing_key' for r in result['missing'])
    assert any(r['Code'] == 'video_direction_unverified' for r in result['missing'])
    assert not any('VideoOutputs' in p['Specifications'] for p in result['proposed']['Tables']['Products'])


def test_nested_paths_lists_and_private_metadata_are_preserved():
    before = original({'Nhóm / RAM': {'Dung lượng': ['16GB', '32GB'], '_private': '16GB'}, '_secret': ['16GB']})
    result = audit(before, {'Values': []})
    specs = result['proposed']['Tables']['Products'][0]['Specifications']
    assert specs['Nhóm / RAM']['Dung lượng'] == ['16 GB', '32 GB']
    assert specs['Nhóm / RAM']['_private'] == specs['_secret'][0] == '16GB'
    assert any(row['Path'] == '/Nhóm ~1 RAM/Dung lượng/0' for row in result['changes'])


def test_formatting_cannot_change_ai_interpretation_even_if_text_looks_equivalent(monkeypatch):
    import catalog_standardization as module
    monkeypatch.setattr(module, 'ai_signature', lambda product, specs, *args: specs.get('Dung lượng RAM'))
    result = audit(original(), {'Values': []})
    assert result['proposed']['Tables']['Products'][0]['Specifications']['Dung lượng RAM'] == '16GB'
    assert any(row['Code'] == 'format_changes_ai_semantics' for row in result['manual'])


def test_public_schemas_and_three_ai_readers_accept_value_only_proposal():
    before = original()
    result = audit(before, {'Values': []})
    checks = validate_consumers(before, result)
    assert checks['ProductResponseValidations'] == checks['ProductVariantResponseValidations'] == 1
    assert checks['FormatOnlyProductsAIUnchanged'] == 1 and checks['VerifiedContentScoreChanges'] == []
    assert checks['ProtectedInvariants'] and checks['DatabaseWrites'] == 0


def test_report_exports_roundtrip_json_and_csv_keep_raw_values_and_ids(tmp_path):
    before = original()
    result = audit(before, {'Values': []})
    write_reports(tmp_path, before, result)
    assert json.loads((tmp_path / 'catalog-cleaned.json').read_text(encoding='utf-8')) == result['proposed']
    with (tmp_path / 'catalog-changes.csv').open(encoding='utf-8-sig', newline='') as file:
        rows = list(csv.DictReader(file))
    assert rows[0]['ProductId'] == before['Tables']['Products'][0]['ProductId']
    assert json.loads(rows[0]['Before']) == '16GB' and json.loads(rows[0]['Proposed']) == '16 GB'
    header = (tmp_path / 'catalog-products.csv').read_text(encoding='utf-8-sig').splitlines()[0].split(',')
    assert len(header) == len(set(header))


def test_legacy_manifest_can_only_supply_a_url_after_exact_slug_and_sku_match(tmp_path):
    before = original()
    manifest = tmp_path / 'legacy.json'
    manifest.write_text(json.dumps({'products': [{'slug': 'test-laptop', 'sku': 'SKU-KEEP',
                         'source_url': 'https://example.com/legacy-source', 'specifications': {'RAM': '999GB'},
                         'price': 1}]}), encoding='utf-8')
    candidates = source_candidates(before, {'Values': []}, manifest)
    assert candidates[0]['LegacySourceURL'] == 'https://example.com/legacy-source'
    assert candidates[0]['LegacyStatus'] == 'unverified_url_hint_only'
    assert '999' not in json.dumps(candidates) and 'price' not in candidates[0]
    before['Tables']['ProductVariants'][0]['Sku'] = 'USER-CHANGED-SKU'
    assert source_candidates(before, {'Values': []}, manifest)[0]['LegacySourceURL'] == ''


def test_cli_has_no_apply_mode_and_rejects_it_before_any_database_access(monkeypatch):
    import audit_catalog_specs as cli
    monkeypatch.setattr(cli, 'capture', lambda: pytest.fail('Database must not be accessed'))
    monkeypatch.setattr(sys, 'argv', ['audit_catalog_specs.py', '--capture', '--apply'])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


def test_explicit_name_conflicts_are_flagged_but_names_and_capacities_are_not_corrected_from_names():
    before = original({'Dung lượng RAM': '16 GB', 'Ổ cứng': '512 GB'})
    before['Tables']['Products'][0]['Name'] = 'Laptop 8GB 256GB'
    before['CatalogFingerprint'] = digest(before['Tables'])
    result = audit(before, {'Values': []})
    assert {r['Code'] for r in result['manual']} >= {'name_ram_conflict', 'name_storage_conflict'}
    assert result['proposed']['Tables'] == before['Tables']


def test_wired_headphones_are_not_assumed_to_need_a_battery_attribute():
    before = original({'Cổng kết nối': '3.5 mm'})
    before['Tables']['Categories'][0].update(Name='Tai nghe', Slug='tai-nghe')
    before['CatalogFingerprint'] = digest(before['Tables'])
    result = audit(before, {'Values': []})
    assert any(r['Code'] == 'battery_runtime_applicability' for r in result['manual'])
    assert not any(r['Attribute'] == 'battery_runtime' for r in result['missing'])


def test_battery_runtime_does_not_become_capacity_when_manufacturer_does_not_publish_mah():
    before = original({'Pin': 'Phát video lên đến 20 giờ'})
    before['Tables']['Categories'][0].update(Name='Điện thoại', Slug='dien-thoai')
    before['CatalogFingerprint'] = digest(before['Tables'])
    result = audit(before, {'Values': []})
    assert any(r['Code'] == 'battery_capacity_unverified' for r in result['missing'])
    assert result['proposed']['Tables'] == before['Tables']


def test_formatting_never_pushes_stated_content_out_of_the_ai_reading_window():
    # 159 characters fit the chat window; "3.5 mm 60 Hz" would make it 161 and hide the last two.
    value = 'x' * 148 + ' 3.5mm 60Hz'
    before = original({'Cổng giao tiếp': value, 'Dung lượng RAM': '16GB'})
    result = audit(before, {'Values': []})
    specs = result['proposed']['Tables']['Products'][0]['Specifications']
    assert specs['Cổng giao tiếp'] == value and specs['Dung lượng RAM'] == '16 GB'
    assert any(r['Code'] == 'format_shifts_ai_window' for r in result['manual'])
    row = {**result['changes'][0], 'Path': pointer(('Cổng giao tiếp',)), 'Attribute': 'Cổng giao tiếp',
           'Before': value, 'Proposed': normalize_value(value)}
    result['changes'].append(row)
    specs['Cổng giao tiếp'] = normalize_value(value)
    with pytest.raises(ValueError, match='hides content'):
        validate_proposal(before, result['proposed'], result['changes'])


def test_formatting_that_keeps_the_visible_window_is_still_proposed():
    value = 'x' * 155 + ' 14 inches'  # Already over 160; "inch" shortens, so the AI sees the same content.
    result = audit(original({'Kích thước màn hình': value}), {'Values': []})
    assert result['proposed']['Tables']['Products'][0]['Specifications']['Kích thước màn hình'] == 'x' * 155 + ' 14 inch'


def test_ai_window_guard_matches_the_production_reader_limits():
    from types import SimpleNamespace
    from app.services.ai_comparison import normalized_specs
    from app.services.ai_tools import public_specifications
    value = 'USB-C ' * 60
    assert len(public_specifications({'Cổng giao tiếp': value})['Cổng giao tiếp']) == AI_TEXT_WINDOWS[0]
    variant = SimpleNamespace(Storage=None, VariantName='', Color=None)
    assert len(normalized_specs({'Cổng kết nối': value}, variant, 'laptop')['ports']) == AI_TEXT_WINDOWS[1]


@pytest.mark.parametrize('stored', ['9.200 mAh', '9200 mAh', '9200mAh'])
def test_thousands_separator_and_spacing_read_the_same_in_recommendation_and_filters(stored):
    from decimal import Decimal
    from app.core.catalog_facets import ProductFacts, largest
    from app.services.recommendation import Candidate, RankingCriteria, assess
    candidate = Candidate('v', 'b', 'Tablet', 'Máy tính bảng', 'tablet', {'Pin': stored}, Decimal(1))
    battery = [r for id_, _, r in assess(RankingCriteria(('battery',)), candidate) if 'mah' in id_]
    assert battery and battery[0].evidence == 'pin 9.200 mAh'
    assert largest('mah', 'dung lượng pin')(ProductFacts.of('Pin', {'Dung lượng pin': stored})) == [9200.0]
