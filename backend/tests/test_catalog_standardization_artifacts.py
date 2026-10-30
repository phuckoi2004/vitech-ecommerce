"""Independent checks of the real Phase A proposal in output/catalog-standardization (ignored folder; skipped when absent).

Shares no comparison code with catalog_standardization.validate_proposal: walkers, format test and reader runs are
written again here, so a bug in the generator cannot hide itself. Offline only: no database, no provider.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/catalog-standardization'
EVIDENCE = ROOT / 'backend/data/catalog-standardization-evidence-2026-10-29.json'
pytestmark = pytest.mark.skipif(not (OUT / 'catalog-cleaned.json').exists() or not EVIDENCE.exists(),
                                reason='Phase A artifacts are generated locally into an ignored folder')
sys.path.insert(0, str(ROOT / 'backend/scripts'))

IDS = {'Products': 'ProductId', 'ProductVariants': 'ProductVariantId', 'Categories': 'CategoryId',
       'Brands': 'BrandId', 'ProductImages': 'ProductImageId'}
MANUFACTURER_HOSTS = ('apple.com', 'samsung.com', 'lg.com', 'edifier.com', 'jbl.com', 'anker.com', 'huawei.com', 'mi.com',
                      'intel.com')


def load(name):
    return json.loads((OUT / name).read_text(encoding='utf-8'))


def rows(name):
    with (OUT / name).open(encoding='utf-8-sig', newline='') as file:
        return list(csv.DictReader(file))


@pytest.fixture(scope='module')
def data():
    original, cleaned = load('catalog-original.json'), load('catalog-cleaned.json')
    changes = rows('catalog-changes.csv')
    for row in changes:
        row['Before'], row['Proposed'] = json.loads(row['Before']), json.loads(row['Proposed'])
    evidence = json.loads(EVIDENCE.read_text(encoding='utf-8'))
    return original, cleaned, changes, evidence


def walk(value, path=()):
    if isinstance(value, dict):
        yield path, 'dict', tuple(value)
        for key, child in value.items():
            yield from walk(child, (*path, key))
    elif isinstance(value, list):
        yield path, 'list', len(value)
        for index, child in enumerate(value):
            yield from walk(child, (*path, index))
    else:
        yield path, type(value).__name__, value


def pointer(path):
    return '/' + '/'.join(str(p).replace('~', '~0').replace('/', '~1') for p in path)


def changed_leaves(original, cleaned):
    after = {p['ProductId']: p for p in cleaned['Tables']['Products']}
    found = {}
    for product in original['Tables']['Products']:
        for (path, kind, old), (_, _, new) in zip(walk(product['Specifications'] or {}),
                                                  walk(after[product['ProductId']]['Specifications'] or {})):
            if kind not in ('dict', 'list') and old != new:
                found[(product['ProductId'], pointer(path))] = (old, new)
    return found


def test_counts_ids_order_and_every_protected_table_are_unchanged(data):
    original, cleaned, _, _ = data
    assert cleaned['Counts'] == original['Counts']
    for table, key in IDS.items():
        before, after = original['Tables'][table], cleaned['Tables'][table]
        assert len(after) == len(before) == original['Counts'][table]
        assert [r[key] for r in after] == [r[key] for r in before]
        if table != 'Products':
            assert after == before  # variants: SKU, price, compare-at price, stock, min stock, flags
    assert cleaned['SchemaFingerprint'] == original['SchemaFingerprint']
    assert cleaned['ProtectedCostFingerprint'] == original['ProtectedCostFingerprint']


def test_skus_and_slugs_stay_identical_and_unique(data):
    original, cleaned, _, _ = data
    for table, key in (('Products', 'Slug'), ('ProductVariants', 'Sku')):
        values = [r[key] for r in cleaned['Tables'][table]]
        assert values == [r[key] for r in original['Tables'][table]] and len(set(values)) == len(values)


def test_only_specification_values_differ_and_keys_types_and_media_are_kept(data):
    original, cleaned, _, _ = data
    for old, new in zip(original['Tables']['Products'], cleaned['Tables']['Products']):
        assert {k: v for k, v in old.items() if k != 'Specifications'} == {k: v for k, v in new.items() if k != 'Specifications'}
        a, b = list(walk(old['Specifications'] or {})), list(walk(new['Specifications'] or {}))
        assert [(p, kind, value if kind in ('dict', 'list') else None) for p, kind, value in a] == \
               [(p, kind, value if kind in ('dict', 'list') else None) for p, kind, value in b]
        if '_vietech_variant_media' in (old['Specifications'] or {}):
            assert new['Specifications']['_vietech_variant_media'] == old['Specifications']['_vietech_variant_media']


def test_every_difference_is_listed_with_exact_before_and_after(data):
    original, cleaned, changes, _ = data
    listed = {(r['ProductId'], r['Path']): (r['Before'], r['Proposed']) for r in changes}
    assert len(listed) == len(changes)
    assert changed_leaves(original, cleaned) == listed


def canonical(text):
    for wrong, right in (('Ghz', 'GHz'), ('GHZ', 'GHz'), ('inches', 'inch')):
        text = text.replace(wrong, right)
    return re.sub(r'\s+', '', re.sub(r'(?<=\d)(?:hz|HZ)\b', 'Hz', text.replace(' ', ' ')))


def test_format_only_rows_keep_every_number_and_unit(data):
    _, _, changes, _ = data
    number = re.compile(r'\d+(?:[.,]\d+)*')
    for row in (r for r in changes if r['Classification'] == 'format_only'):
        old, new = row['Before'], row['Proposed']
        # Case-sensitive: Gb/s (bits) can never become GB/s (bytes), mAh never Wh.
        assert isinstance(old, str) and canonical(old) == canonical(new), row['Path']
        assert number.findall(old) == number.findall(new), row['Path']


def test_content_changes_are_exactly_the_reviewed_manufacturer_corrections(data):
    _, _, changes, evidence = data
    corrections = {(v['ProductId'], v['Path']): v for v in evidence['Values'] if v['Decision'] == 'correction'}
    content = {(r['ProductId'], r['Path']): r for r in changes if r['Classification'] != 'format_only'}
    assert set(content) == set(corrections)
    for key, row in content.items():
        source = corrections[key]
        host = urlparse(row['SourceURL']).hostname or ''
        assert row['Before'] == source['Before'] and row['Proposed'] == source['Proposed']
        assert row['VerificationStatus'] == 'verified' and row['SourceURL'].startswith('https://')
        assert any(host == h or host.endswith('.' + h) for h in MANUFACTURER_HOSTS)


def test_unverified_or_manual_evidence_never_changes_a_value_or_counts_as_verified(data):
    original, cleaned, _, evidence = data
    after = {p['ProductId']: p['Specifications'] for p in cleaned['Tables']['Products']}
    audit_rows = {(r['ProductId'], r['Path'], r['Code']): r for r in rows('catalog-audit.csv')}
    manual = [v for v in evidence['Values'] if v['Decision'] == 'manual']
    format_rows = {(r['ProductId'], r['Path']) for r in rows('catalog-changes.csv') if r['Classification'] == 'format_only'}
    assert manual
    for item in manual:
        value = after[item['ProductId']][item['Path'][1:].replace('~1', '/').replace('~0', '~')]
        # Spacing may still be normalized; the stated content may not.
        assert value == item['Before'] or ((item['ProductId'], item['Path']) in format_rows
                                           and canonical(value) == canonical(item['Before']))
        assert (item['ProductId'], item['Path'], 'manufacturer_match') not in audit_rows
        assert audit_rows[(item['ProductId'], item['Path'], 'source_review')]['VerificationStatus'] == 'partial_or_unresolved'


@pytest.mark.parametrize(('name', 'key', 'kept'), [
    ('Xiaomi Pad 8 Pro 8GB 128GB', 'Pin', '9.200 mAh'),          # Source not readable by the reviewer.
    ('Loa Bluetooth Sony SRS-XB100 Extra Bass', 'Trọng lượng', '274 g'),  # Format only; source not readable.
])
def test_review_decisions_restore_unverified_or_lossy_proposals(data, name, key, kept):
    _, cleaned, _, _ = data
    product = next(p for p in cleaned['Tables']['Products'] if p['Name'] == name)
    assert product['Specifications'][key] == kept


def test_corrections_keep_the_details_the_original_and_the_source_both_state(data):
    _, cleaned, _, _ = data
    boombox = next(p for p in cleaned['Tables']['Products'] if p['Name'] == 'Loa Bluetooth JBL Boombox 4')
    drivers = boombox['Specifications']['Cấu tạo']
    assert all(part in drivers for part in ('5 inch', '123 mm', '0,75 inch', '20 mm', 'tweeter', 'racetrack'))
    assert 'loa trầm 20' not in drivers
    # Apple publishes cores but no clock: the stored clock is kept beside them, never deleted.
    iphone = next(p for p in cleaned['Tables']['Products'] if p['Name'] == 'iPhone 13 128GB')
    cpu = iphone['Specifications']['Loại CPU']
    assert '3.22 GHz' in cpu and 'CPU 6 lõi với 2 lõi hiệu năng và 4 lõi tiết kiệm điện' in cpu
    # Intel ARK: "12 MB Intel® Smart Cache"; only the unit was wrong.
    dell = next(p for p in cleaned['Tables']['Products'] if p['Name'] == 'Laptop Dell 14 DC14250 DC4C5386W')
    assert dell['Specifications']['Loại CPU'] == 'Intel Core 5 120U (Up to 5 GHz, 12 MB Cache)'


def test_lg_usb_c_becomes_a_display_input_without_an_assumed_alt_mode_or_timing(data):
    from app.services.compatibility_specs import normalize_video_specs
    original, cleaned, _, _ = data
    pick = lambda snapshot: next(p for p in snapshot['Tables']['Products'] if p['Name'] == 'Màn hình LG 24U631A-B 24 inch')  # noqa: E731
    before, after = (normalize_video_specs(pick(s)['Specifications']).ports for s in (original, cleaned))
    usb_before, usb_after = (next(p for p in ports if p.connector == 'usb_c') for ports in (before, after))
    assert usb_before.video is None and usb_before.direction is None
    assert (usb_after.direction, usb_after.video, usb_after.alt_mode, usb_after.modes) == ('input', True, None, ())
    hdmi = lambda ports: [(p.direction, p.video, p.alt_mode, p.version, p.modes, p.max_resolution, p.max_hz)  # noqa: E731
                          for p in ports if p.connector == 'hdmi']  # Evidence text quotes the field, so it differs.
    assert hdmi(after) == hdmi(before)


@pytest.fixture(scope='module')
def readers(data):
    from app.core.catalog_facets import ProductFacts, facet_group
    from app.core.catalog_media import technical_specifications
    from app.services.ai_comparison import normalized_specs, ranking_specs
    from app.services.ai_grounding import _Corpus
    from app.services.ai_tools import public_specifications
    from app.services.compatibility_specs import normalize_video_specs
    from app.services.recommendation import NEEDS, Candidate, RankingCriteria, assess, product_type
    original, cleaned, changes, _ = data
    categories = {c['CategoryId']: c for c in original['Tables']['Categories']}
    variants = defaultdict(list)
    for v in original['Tables']['ProductVariants']:
        variants[v['ProductId']].append(v)

    def root(product):
        category = categories[product['CategoryId']]
        while category.get('ParentCategoryId'):
            category = categories[category['ParentCategoryId']]
        return category

    def read(product):
        specs, kind = product['Specifications'], product_type(root(product)['Name'])
        public = technical_specifications(specs) or {}
        visible = [v['Storage'] for v in variants[product['ProductId']] if v['IsActive'] and not v['IsDeleted']]
        facts = ProductFacts.of(product['Name'], specs, visible)  # As catalog.py passes them: raw Specifications.
        filters = {f'{f.key}={o.value}': o.matches(facts) for f in facet_group(root(product)['Slug']).facets for o in f.options}
        scores = []
        for v in variants[product['ProductId']]:
            compare = ranking_specs(normalized_specs(public, SimpleNamespace(**v), kind), kind)
            for values in (public, compare):
                candidate = Candidate(v['ProductVariantId'], product['BrandId'], product['Name'], '', kind, values,
                                      Decimal(v['Price']))
                for need in [(), *[(k,) for k in NEEDS]]:
                    scores.append([(i, w, r.status, round(r.score, 9)) for i, w, r in assess(RankingCriteria(need), candidate)])
        video = [(p.connector, p.direction, p.video, p.alt_mode, p.version, p.max_resolution, p.max_hz)
                 for p in normalize_video_specs(specs).ports]
        pairs = _Corpus([f'{k}: {v}' for k, v in public_specifications(specs, 20).items()], ()).pairs
        return filters, scores, video, pairs

    content = {r['ProductId'] for r in changes if r['Classification'] != 'format_only'}
    after = {p['ProductId']: p for p in cleaned['Tables']['Products']}
    return [(p, read(p), read(after[p['ProductId']]), p['ProductId'] in content) for p in original['Tables']['Products']]


def test_filters_recommendation_compare_and_video_ports_read_format_only_products_the_same(readers):
    for product, before, after, content in readers:
        if not content:
            assert before[:3] == after[:3], product['Name']


def test_formatting_never_removes_a_number_unit_fact_the_chat_can_cite(readers):
    for product, before, after, content in readers:
        if not content:
            assert before[3] <= after[3], product['Name']


def test_compatibility_verdicts_do_not_change_and_4k144_is_never_confirmed(data):
    from app.schemas.ai_compatibility import VideoRequest
    from app.services.compatibility import check_compatibility
    from app.services.compatibility_specs import normalize_video_specs
    original, cleaned, _, _ = data
    categories = {c['CategoryId']: c for c in original['Tables']['Categories']}
    after = {p['ProductId']: p for p in cleaned['Tables']['Products']}

    def root_slug(product):
        category = categories[product['CategoryId']]
        while category.get('ParentCategoryId'):
            category = categories[category['ParentCategoryId']]
        return category['Slug']

    laptops = [p for p in original['Tables']['Products'] if root_slug(p) == 'laptop']
    monitors = [p for p in original['Tables']['Products'] if root_slug(p) == 'man-hinh']
    assert laptops and monitors
    requests = [VideoRequest(Width=w, Height=h, RefreshHz=hz, SourceConnector=c)
                for w, h, hz in ((None, None, None), (1920, 1080, 60), (2560, 1440, 100), (3840, 2160, 144))
                for c in (None, 'hdmi', 'usb_c', 'thunderbolt')]
    profile = lambda p: normalize_video_specs(p['Specifications'])  # noqa: E731
    for laptop in laptops:
        for monitor in [None, *monitors]:
            for request in requests:
                old = check_compatibility(profile(laptop), monitor and profile(monitor), request).status
                new = check_compatibility(profile(after[laptop['ProductId']]),
                                          monitor and profile(after[monitor['ProductId']]), request).status
                assert old == new, (laptop['Name'], monitor and monitor['Name'], request)
                if request.RefreshHz == 144:
                    assert new not in ('compatible', 'requires_adapter')


def test_exported_csv_and_json_are_well_formed_and_match_the_summary(data):
    summary = load('catalog-summary.json')
    for name in ('catalog-audit.csv', 'catalog-changes.csv', 'catalog-missing-specs.csv', 'catalog-manual-review.csv',
                 'catalog-products.csv', 'catalog-source-candidates.csv', 'catalog-source-register.csv'):
        with (OUT / name).open(encoding='utf-8-sig', newline='') as file:
            table = list(csv.reader(file))
        assert table and len(table[0]) == len(set(table[0]))
        assert all(len(line) == len(table[0]) for line in table)
        if 'Before' in table[0]:
            for line in table[1:]:
                json.loads(line[table[0].index('Before')]), json.loads(line[table[0].index('Proposed')])
    for name in ('catalog-original.json', 'catalog-cleaned.json', 'catalog-ai-validation.json', 'catalog-summary.json'):
        load(name)
    changes = rows('catalog-changes.csv')
    assert summary['FormatProposals'] == sum(r['Classification'] == 'format_only' for r in changes)
    assert summary['VerifiedCorrections'] == sum(r['Classification'] == 'verified_correction' for r in changes)
    assert summary['MissingFindings'] == len(rows('catalog-missing-specs.csv'))
    assert summary['ManualFindings'] == len(rows('catalog-manual-review.csv'))
    assert summary['Products'] == len(rows('catalog-products.csv')) == 203 and summary['DatabaseWrites'] == 0


def test_rerunning_the_tool_reproduces_the_proposal_and_adds_nothing(data):
    from catalog_standardization import audit
    original, cleaned, changes, evidence = data
    again = audit(original, evidence)
    assert again['proposed'] == cleaned
    assert [(r['ProductId'], r['Path'], r['Proposed']) for r in again['changes']] == \
           [(r['ProductId'], r['Path'], r['Proposed']) for r in changes]
    assert audit(cleaned, {'Values': []})['summary']['FormatProposals'] == 0
