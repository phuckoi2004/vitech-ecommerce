"""Offline, value-only catalog proposals. Never imports a database connection or writes SQL."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

from app.core.catalog_media import technical_specifications
from app.core.search_text import fold
from app.schemas.ai_compatibility import VideoRequest
from app.services.ai_comparison import normalized_specs, ranking_specs
from app.services.compatibility import check_compatibility
from app.services.compatibility_specs import normalize_video_specs
from app.services.recommendation import Candidate, NEEDS, RankingCriteria, assess, evaluate, product_type

UNIT_PATTERN = re.compile(
    r"(?<![\w.,])(\d+(?:[.,]\d+)*)[ \u00a0]*(GB|TB|MHz|GHz|Ghz|GHZ|Hz|hz|HZ|kHz|mAh|Wh|W|kg|g|mm|cm|ms|MP|inches|inch)(?![A-Za-z0-9_])")
UNIT_CASE = {'Ghz': 'GHz', 'GHZ': 'GHz', 'hz': 'Hz', 'HZ': 'Hz', 'inches': 'inch'}
# Characters of one value the AI readers keep: chat facts (ai_tools.public_specifications) and Smart Compare
# (ai_comparison.normalized_specs). Inserted spaces must not push stated content out of either window.
AI_TEXT_WINDOWS = (160, 200)
EMPTY = {'', '-', '--', 'n/a', 'null', 'unknown', 'dang cap nhat', 'chua cap nhat', 'chua co du lieu', 'chua co thong tin'}
PRIMARY_DOMAINS = ('apple.com', 'samsung.com', 'lg.com', 'asus.com', 'lenovo.com', 'sony.com', 'sony.com.vn',
                   'jbl.com', 'jbl.com.vn', 'jbl.cl', 'edifier.com', 'anker.com', 'logitech.com', 'logi.com',
                   'marshall.com', 'harman.com', 'harmankardon.com', 'mi.com', 'oppo.com', 'honor.com', 'bose.com',
                   'huawei.com', 'logitechg.com', 'intel.com',
                   # Port-data round of 29/10/2026: manufacturer spec pages, datasheets and service guides.
                   'dell.com', 'hp.com', 'msi.com', 'philips.com',
                   # Round 3: Acer's own manual, LG Korea's per-input limits, EDRA's physical mounts.
                   'acer.com', 'lge.co.kr', 'edravn.com',
                   # ViewSonic's product page links the user guide on its official download host.
                   'viewsonic.com', 'viewsonicglobal.com',
                   # Completion round of 30/10/2026, reviewed manufacturer specification pages.
                   'gigabyte.com', 'meizu.com', 'vsp.vn')
FIELDS = ['ProductId', 'ProductName', 'Brand', 'Category', 'ProductVariantId', 'Sku', 'Path', 'Attribute',
          'Classification', 'Code', 'Before', 'Proposed', 'Reason', 'SourceURL', 'VerifiedAt', 'Confidence',
          'ModelMatch', 'RegionScope', 'VerificationStatus', 'AIImpact']

# Feature groups are audit requirements, not new Specifications keys. Aliases never replace original names.
COMMON_SCREEN = [
    ('screen_size', ('Kích thước màn hình', 'Kích thước thực tế (bao gồm viền)')),
    ('resolution', ('Độ phân giải màn hình',)), ('panel', ('Công nghệ màn hình', 'Tấm nền', 'Loại tấm nền')),
    ('refresh_rate', ('Tần số quét', 'Tính năng màn hình', 'Công nghệ màn hình')),
]
FEATURES = {
    'laptop': [('cpu', ('Loại CPU', 'CPU', 'Chip xử lý', 'Chipset')), ('ram', ('Dung lượng RAM', 'RAM')),
               ('storage', ('Ổ cứng', 'SSD')), ('gpu', ('Loại card đồ họa', 'GPU')),
               ('battery', ('Pin', 'Dung lượng pin')), ('weight', ('Trọng lượng', 'Khối lượng')),
               ('ports', ('Cổng giao tiếp', 'Cổng kết nối')), ('os', ('Hệ điều hành', 'Hệ điều hành khi ra mắt')),
               *COMMON_SCREEN],
    'phone': [('cpu', ('Chipset', 'Chip xử lý', 'Loại CPU')), ('ram', ('Dung lượng RAM', 'RAM')),
              ('storage', ('Bộ nhớ trong',)), ('battery', ('Pin', 'Dung lượng pin')),
              ('charging', ('Công nghệ sạc', 'Công suất sạc hỗ trợ tối đa', 'Công nghệ pin')),
              ('rear_camera', ('Camera sau', 'Độ phân giải camera sau')),
              ('front_camera', ('Camera trước', 'Độ phân giải camera trước')),
              ('os', ('Hệ điều hành', 'Hệ điều hành khi ra mắt', 'Phiên bản HĐH')),
              ('connectivity', ('Hỗ trợ mạng', 'WiFi', 'Kết nối')), *COMMON_SCREEN],
    'tablet': [('cpu', ('Chipset', 'Chip xử lý', 'Loại CPU')), ('ram', ('Dung lượng RAM', 'RAM')),
               ('storage', ('Bộ nhớ trong',)), ('battery', ('Pin', 'Dung lượng pin')),
               ('rear_camera', ('Camera sau',)), ('front_camera', ('Camera trước',)),
               ('connectivity', ('Kết nối', 'Hỗ trợ mạng', 'WiFi')),
               ('os', ('Hệ điều hành', 'Hệ điều hành khi ra mắt')), *COMMON_SCREEN],
    'monitor': [('ports', ('Cổng kết nối', 'Cổng giao tiếp')), *COMMON_SCREEN],
    'headphone': [('connectivity', ('Kết nối', 'Cổng kết nối', 'Phương thức kết nối')),
                  ('battery_runtime', ('Thời lượng sử dụng Pin', 'Thời lượng pin')),
                  ('audio', ('Công nghệ âm thanh',)), ('microphone', ('Micro',))],
    'keyboard': [('connectivity', ('Kết nối', 'Phương thức kết nối')),
                 ('key_count_or_layout', ('Số phím', 'Số lượng phím', 'Kích thước/Layout')),
                 ('switch_or_type', ('Loại bàn phím',)), ('compatibility', ('Tương thích',))],
    'mouse': [('connectivity', ('Kết nối',)), ('sensor', ('Cảm biến (Sensor)',)),
              ('dpi', ('Độ phân giải', 'Độ phân giải (DPI)')), ('weight', ('Trọng lượng',))],
    'speaker': [('power', ('Công suất',)), ('connectivity', ('Kết nối', 'Cổng kết nối')),
                ('audio', ('Công nghệ âm thanh',)), ('battery_runtime', ('Thời lượng pin',))],
    'powerbank': [('battery_capacity', ('Dung lượng pin',)), ('power', ('Công suất sạc',)),
                  ('input', ('Cổng sạc vào',)), ('output', ('Cổng sạc ra',))],
}
ROOT_KINDS = {'laptop': 'laptop', 'dien-thoai': 'phone', 'may-tinh-bang': 'tablet', 'man-hinh': 'monitor',
              'tai-nghe': 'headphone', 'ban-phim': 'keyboard', 'chuot': 'mouse', 'loa': 'speaker',
              'pin-sac-du-phong': 'powerbank', 'sac-du-phong': 'powerbank'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def normalize_value(value):
    """Spacing/case of unambiguous existing units only. Gb/s is never changed into GB/s."""
    return UNIT_PATTERN.sub(lambda m: f'{m[1]} {UNIT_CASE.get(m[2], m[2])}', value.replace('\u00a0', ' ').strip())


def shrinks_ai_window(old, new):
    """Whether the AI readers would see less of the stated content after formatting (spaces/case only differ)."""
    def seen(text, size):
        return len(re.sub(r'\s+', '', normalize_value(text[:size])))
    return any(seen(new, size) < seen(old, size) for size in AI_TEXT_WINDOWS)


def pointer(path):
    return '/' + '/'.join(str(part).replace('~', '~0').replace('/', '~1') for part in path)


def leaves(value, path=(), *, include_private=False):
    if isinstance(value, dict):
        for key, child in value.items():
            if include_private or not str(key).startswith('_'):
                yield from leaves(child, (*path, key), include_private=include_private)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from leaves(child, (*path, index), include_private=include_private)
    else:
        yield path, value


def at(value, path):
    for part in path:
        value = value[part]
    return value


def replace(value, path, new):
    parent = at(value, path[:-1])
    if type(parent[path[-1]]) is not type(new):
        raise ValueError('Changing JSON scalar type is forbidden')
    parent[path[-1]] = new


def shape(value):
    if isinstance(value, dict):
        return {key: shape(child) for key, child in value.items()}
    if isinstance(value, list):
        return [shape(child) for child in value]
    return type(value).__name__


def root_category(product, categories):
    current, seen = categories[product['CategoryId']], set()
    while current.get('ParentCategoryId'):
        if current['CategoryId'] in seen:
            raise ValueError('Category cycle')
        seen.add(current['CategoryId'])
        current = categories[current['ParentCategoryId']]
    return current


def inventory_context(original):
    tables = original['Tables']
    categories = {c['CategoryId']: c for c in tables['Categories']}
    brands = {b['BrandId']: b for b in tables['Brands']}
    variants = defaultdict(list)
    for row in tables['ProductVariants']:
        variants[row['ProductId']].append(row)
    return categories, brands, variants


def ai_signature(product, specs, variants, category, root_name):
    """Run current Recommendation and Compare readers for every SKU/need, compare scores not wording."""
    kind = product_type(root_name)
    results = []
    for variant in variants:
        selected = SimpleNamespace(**variant)
        public = technical_specifications(specs) or {}
        comparison = normalized_specs(public, selected, kind)
        for reader, values in [('recommendation', public), ('comparison', ranking_specs(comparison, kind))]:
            candidate = Candidate(variant['ProductVariantId'], product['BrandId'], product['Name'], category['Name'],
                                  kind, values, Decimal(variant['Price']))
            for need in [(), *[(key,) for key in NEEDS]]:
                criteria = RankingCriteria(need)
                rows = assess(criteria, candidate)
                result = evaluate(criteria, candidate, budget_max=30000000, rows=rows)
                results.append((variant['ProductVariantId'], reader, need, result.score, result.completeness,
                                [(id_, weight, r.status, r.score) for id_, weight, r in rows]))
    profile = normalize_video_specs(specs)
    video = [(p.connector, p.direction, p.video, p.alt_mode, p.version,
              [m.signature() for m in p.modes], p.max_resolution, p.max_hz) for p in profile.ports]
    cables = [(c.source, c.target, [m.signature() for m in c.modes]) for c in profile.cables]
    return results, video, cables, profile.outputs_complete, profile.inputs_complete


def validate_proposal(original, proposed, changes):
    """Only listed, existing public Specifications scalar values may differ; preserve every other byte/value."""
    before, after = original['Tables'], proposed['Tables']
    if ({k: v for k, v in original.items() if k not in ('Tables', 'CatalogFingerprint')}
            != {k: v for k, v in proposed.items() if k not in ('Tables', 'CatalogFingerprint')}):
        raise ValueError('Snapshot metadata changed')
    if set(before) != set(after):
        raise ValueError('Table set changed')
    allowed = {(c['ProductId'], c['Path']): c for c in changes}
    observed = set()
    if len(allowed) != len(changes):
        raise ValueError('Duplicate proposed path')
    for table in before:
        if len(before[table]) != len(after[table]):
            raise ValueError('Catalog row count changed')
        if table != 'Products':
            if before[table] != after[table]:
                raise ValueError('Protected catalog table changed')
            continue
        for old, new in zip(before[table], after[table]):
            old_other = {k: v for k, v in old.items() if k != 'Specifications'}
            new_other = {k: v for k, v in new.items() if k != 'Specifications'}
            if old_other != new_other or shape(old['Specifications']) != shape(new['Specifications']):
                raise ValueError('Identity, non-spec column, key set or JSON shape changed')
            for key, value in (old['Specifications'] or {}).items():
                if str(key).startswith('_') and new['Specifications'][key] != value:
                    raise ValueError('Private metadata changed')
            for path, value in leaves(old['Specifications'], include_private=True):
                target = at(new['Specifications'], path)
                if value != target:
                    if any(isinstance(part, str) and part.startswith('_') for part in path):
                        raise ValueError('Private metadata changed')
                    identity = (old['ProductId'], pointer(path))
                    row = allowed.get(identity)
                    if row is None or row['Before'] != value or row['Proposed'] != target:
                        raise ValueError('Unlisted change or stale before value')
                    if row['Classification'] not in ('format_only', 'verified_correction'):
                        raise ValueError('Unapproved change classification')
                    if row['Classification'] == 'format_only' and (
                            not isinstance(value, str) or normalize_value(value) != target):
                        raise ValueError('Format-only change altered technical content')
                    if row['Classification'] == 'format_only' and shrinks_ai_window(value, target):
                        raise ValueError('Format-only change hides content from an AI reader')
                    observed.add(identity)
    if observed != set(allowed):
        raise ValueError('Proposal has an unapplied or nonexistent path')
    if original['SchemaFingerprint'] != proposed['SchemaFingerprint']:
        raise ValueError('Schema fingerprint changed')
    if original['ProtectedCostFingerprint'] != proposed['ProtectedCostFingerprint']:
        raise ValueError('Cost fingerprint changed')
    return True


def validate_evidence(item, product, path, old):
    host = (urlparse(item.get('SourceURL', '')).hostname or '').lower()
    trusted = urlparse(item.get('SourceURL', '')).scheme == 'https' and any(
        host == domain or host.endswith('.' + domain) for domain in PRIMARY_DOMAINS)
    if (item.get('ProductId') != product['ProductId'] or item.get('ProductName') != product['Name']
            or item.get('Path') != pointer(path) or item.get('Before') != old):
        raise ValueError('Evidence identity/path/before does not match live snapshot')
    if item.get('Decision') in ('correction', 'verified_match') and not (
            trusted and item.get('VerifiedAt') and item.get('ModelMatch') == 'exact'
            and item.get('RegionScope') and item.get('Reason') and item.get('Confidence') == 'high'):
        raise ValueError('Verified change requires exact, reviewed manufacturer evidence')
    if item.get('Decision') == 'verified_match' and item.get('Proposed') != old:
        raise ValueError('A verified match cannot contain a correction')


def validate_snapshot(original):
    tables = original['Tables']
    if original.get('Source') != 'configured_postgresql_live_select' or original.get('ReadOnly') is not True:
        raise ValueError('Expected a read-only live catalog snapshot, not an import manifest')
    if digest(tables) != original['CatalogFingerprint']:
        raise ValueError('Original snapshot fingerprint does not match its contents')
    for table, rows in tables.items():
        if len(rows) != original['Counts'][table]:
            raise ValueError('Snapshot count mismatch')
        id_key = {'Products': 'ProductId', 'ProductVariants': 'ProductVariantId', 'Categories': 'CategoryId',
                  'Brands': 'BrandId', 'ProductImages': 'ProductImageId'}[table]
        if len({row[id_key] for row in rows}) != len(rows):
            raise ValueError('Duplicate catalog identity')
    for table, key in [('Products', 'Slug'), ('ProductVariants', 'Sku')]:
        if len({row[key] for row in tables[table]}) != len(tables[table]):
            raise ValueError('Duplicate catalog slug or SKU')


def audit(original, evidence):
    validate_snapshot(original)
    if evidence.get('SnapshotFingerprint', original['CatalogFingerprint']) != original['CatalogFingerprint']:
        raise ValueError('Evidence belongs to a different snapshot')
    proposed = copy.deepcopy(original)
    categories, brands, variants = inventory_context(original)
    source_index = {(r['ProductId'], r['Path']): r for r in evidence.get('Values', [])}
    if len(source_index) != len(evidence.get('Values', [])):
        raise ValueError('Duplicate evidence path')
    used = set()
    findings, changes, product_rows = [], [], []

    for product, cleaned in zip(original['Tables']['Products'], proposed['Tables']['Products']):
        category, root = categories[product['CategoryId']], root_category(product, categories)
        kind = ROOT_KINDS.get(root['Slug']) or product_type(root['Name'])
        if kind is None and 'sac' in root['Slug']:
            kind = 'powerbank'
        own = variants[product['ProductId']]
        base = {'ProductId': product['ProductId'], 'ProductName': product['Name'], 'Brand': brands[product['BrandId']]['Name'],
                'Category': category['Name'], 'ProductVariantId': ';'.join(v['ProductVariantId'] for v in own),
                'Sku': ';'.join(v['Sku'] for v in own)}
        start, changed_count, verified_count = len(findings), 0, 0
        def add(classification, code, reason, *, path=(), old=None, new=None, **extra):
            row = {**base, 'Path': pointer(path) if path else '', 'Attribute': str(path[-1]) if path else '',
                   'Classification': classification, 'Code': code, 'Before': old, 'Proposed': new, 'Reason': reason,
                   'VerificationStatus': 'unverified', **extra}
            findings.append(row)
            return row

        specs = product['Specifications']
        if specs is not None and not isinstance(specs, dict):
            add('manual_review', 'invalid_spec_container', 'Specifications không phải object; giữ nguyên, không sửa cấu trúc.')
            product_rows.append({**base, 'RootCategory': root['Name'], 'RootSlug': root['Slug'], 'Kind': kind,
                                 'TechnicalValueCount': 0, 'ProposedValueCount': 0, 'ManufacturerCheckedValues': 0,
                                 'VerificationStatus': 'unverified', 'FindingCount': 1})
            continue
        spec_leaves = list(leaves(specs)) if specs else []
        for path, value in spec_leaves:
            verified = source_index.get((product['ProductId'], pointer(path)))
            if verified:
                validate_evidence(verified, product, path, value)
                used.add((product['ProductId'], pointer(path)))
                extras = {k: verified.get(k, '') for k in ('SourceURL', 'VerifiedAt', 'Confidence', 'ModelMatch', 'RegionScope')}
                if verified['Decision'] == 'correction':
                    new = verified['Proposed']
                    if type(new) is not type(value) or new == value:
                        raise ValueError('Correction must change only a scalar value without changing type')
                    replace(cleaned['Specifications'], path, new)
                    code = 'manufacturer_clarification' if verified.get('ChangeKind') == 'clarification' else 'manufacturer_correction'
                    row = add('verified_correction', code, verified['Reason'], path=path, old=value, new=new,
                              VerificationStatus='verified', AIImpact='verified_content_change_review_required', **extras)
                    changes.append(row); changed_count += 1; verified_count += 1
                    continue
                if verified['Decision'] == 'verified_match':
                    add('valid', 'manufacturer_match', verified['Reason'], path=path, old=value, new=value,
                        VerificationStatus='verified', **extras)
                    verified_count += 1
                else:
                    add('manual_review', 'source_review', verified['Reason'], path=path, old=value,
                        VerificationStatus='partial_or_unresolved', **extras)
            if value is None or isinstance(value, str) and fold(value).strip() in EMPTY:
                add('missing', 'empty_existing_value', 'Giá trị trống/chưa xác định trong khóa hiện có; không tự điền.', path=path, old=value)
            elif isinstance(value, str):
                new = normalize_value(value)
                if new != value and shrinks_ai_window(value, new):
                    add('manual_review', 'format_shifts_ai_window',
                        'Thêm khoảng trắng đẩy phần cuối giá trị ra ngoài giới hạn ký tự AI đọc (chat 160, so sánh 200); giữ nguyên.',
                        path=path, old=value, new=new, AIImpact='blocked')
                elif new != value:
                    trial = copy.deepcopy(cleaned['Specifications'])
                    replace(trial, path, new)
                    previous_sig = ai_signature(product, cleaned['Specifications'], own, category, root['Name'])
                    trial_sig = ai_signature(product, trial, own, category, root['Name'])
                    if previous_sig != trial_sig:
                        add('manual_review', 'format_changes_ai_semantics', 'Chuẩn hóa làm thay đổi kết quả đọc AI; giữ nguyên để kiểm tra.',
                            path=path, old=value, new=new, AIImpact='blocked')
                    else:
                        replace(cleaned['Specifications'], path, new)
                        row = add('format_only', 'unit_spacing', 'Chỉ chuẩn hóa khoảng trắng/đơn vị, giữ nguyên số và ý nghĩa; không xác minh nội dung kỹ thuật.',
                            path=path, old=value, new=new, SourceURL='local:catalog-original.json', Confidence='high_format_only',
                            VerificationStatus='format_only_not_manufacturer_verified', AIImpact='unchanged')
                        changes.append(row); changed_count += 1
                if re.search(r'\b\d{1,3}[.,]\d{3}\s*mAh\b', value):
                    add('manual_review', 'ambiguous_thousands_separator', 'Dấu phân cách hàng nghìn/thập phân có thể khiến AI đọc sai; chỉ đổi số sau khi có nguồn đúng model.', path=path, old=value)
                if fold(str(path[-1])) == 'loai cpu' and re.fullmatch(r'\d+(?:[.,]\d+)?\s*[GM]Hz', value):
                    add('manual_review', 'cpu_field_contains_clock_only', 'Khóa loại CPU chỉ chứa xung nhịp; không đổi tên khóa hoặc suy ra CPU từ xung nhịp.', path=path, old=value)
                if fold(str(path[-1])) in ('dung luong pin',) and re.search(r'\bgio\b', fold(value)) and not re.search(r'mAh|Wh', value):
                    add('manual_review', 'capacity_contains_runtime', 'Khóa dung lượng chứa thời lượng; không chuyển giờ thành mAh/Wh hoặc đổi khóa.', path=path, old=value)

        by_label = defaultdict(list)
        for path, value in spec_leaves:
            by_label[fold(str(path[-1]))].append((path, value))
        accessory = kind == 'monitor' and re.search(r'\b(?:gia treo|tay treo)\b', fold(product['Name']))
        if accessory:
            add('manual_review', 'accessory_in_monitor_category', 'Tên là giá/tay treo, không phải màn hình phát hình; không đổi danh mục và không yêu cầu thông số panel.')
        for feature, aliases in (() if accessory else FEATURES.get(kind, ())):
            present = [item for alias in aliases for item in by_label[fold(alias)]]
            filled = [(path, value) for path, value in present if value is not None and fold(str(value)).strip() not in EMPTY]
            if feature == 'battery_runtime' and not filled and kind in ('speaker', 'headphone'):
                add('manual_review', 'battery_runtime_applicability',
                    'Chưa xác nhận có dùng pin hay chỉ dùng dây/nguồn điện; không coi thiếu thời lượng pin là lỗi trước khi xác định loại thiết bị.', Attribute=feature)
                continue
            if not filled:
                add('missing', 'missing_key' if not present else 'empty_feature',
                    f'Chưa có dữ liệu nhóm {feature}. Không thêm khóa hoặc suy đoán giá trị.',
                    path=present[0][0] if present else (), old=present[0][1] if present else None,
                    Attribute=feature)
            elif feature == 'refresh_rate' and not any(re.search(r'\d+\s*hz\b', fold(str(v))) for _, v in filled):
                add('missing', 'insufficient_detail', 'Có thông tin màn hình nhưng chưa ghi rõ Hz; không tự tạo khóa tần số quét.',
                    path=filled[0][0], old=filled[0][1], Attribute=feature)
            elif feature == 'battery' and kind in ('phone', 'tablet') and not any(
                    re.search(r'\d\s*(?:mah|wh|watt.?gio)', fold(str(value))) for _, value in filled):
                add('missing', 'battery_capacity_unverified',
                    'Chỉ có hóa học pin/thời lượng, chưa có dung lượng; không quy đổi giờ sang mAh hoặc tự điền số hãng chưa công bố.',
                    path=filled[0][0], old=filled[0][1], Attribute=feature)
        if kind in ('laptop', 'monitor') and not accessory:
            profile = normalize_video_specs(specs)
            direction = 'output' if kind == 'laptop' else 'input'
            if not any(p.usable(direction) for p in profile.ports):
                add('missing', 'video_direction_unverified', 'Thiếu căn cứ chức năng/chiều video của cổng; Compatibility phải giữ unknown khi không có đường khác đã xác minh.')
            if any(p.connector == 'usb_c' and (p.video is None or p.alt_mode is None) for p in profile.ports):
                add('manual_review', 'usb_c_video_unverified', 'Không đồng nhất USB-C dữ liệu/sạc với DP Alt Mode; giữ nguyên khi chưa có nguồn đúng model.')
            if not any(p.modes for p in profile.ports) or not profile.cables:
                add('missing', 'end_to_end_signal_unverified', 'Chưa đủ timing từng cổng và bằng chứng cáp/màu/DSC để xác nhận 4K 144Hz; không thêm cấu trúc JSON mới.')
        # A product-level storage value may describe only one SKU; never propagate it to other variants.
        storage_aliases = ('Ổ cứng', 'Bộ nhớ trong', 'SSD')
        disk_values = [str(value) for alias in storage_aliases for _, value in by_label[fold(alias)]]
        def capacity(value):
            match = re.search(r'(\d+(?:[.,]\d+)?)\s*(GB|TB)\b', value)
            return (Decimal(match[1].replace(',', '.')) * (1024 if match[2] == 'TB' else 1)) if match else None
        disk = next((capacity(value) for value in disk_values if capacity(value) is not None), None)
        if kind in ('laptop', 'phone', 'tablet'):
            named = re.findall(r'\b\d+(?:[.,]\d+)?\s*(?:GB|TB)\b', product['Name'])
            if named and disk is not None and disk != capacity(named[-1]):
                add('manual_review', 'name_storage_conflict', 'Dung lượng ghi rõ trong tên khác thông số chung; chỉ đánh dấu, không dùng tên để sửa giá trị.', old=disk_values)
            ram_values = [str(value) for alias in ('Dung lượng RAM', 'RAM') for _, value in by_label[fold(alias)]]
            if len(named) >= 2 and ram_values and capacity(ram_values[0]) != capacity(named[-2]):
                add('manual_review', 'name_ram_conflict', 'RAM ghi rõ trong tên khác thông số chung; cần xác minh đúng SKU, không tự sửa theo tên.', old=ram_values)
        for variant in own:
            explicit = capacity(variant.get('Storage') or '')
            if disk is not None and explicit is not None and disk != explicit:
                add('manual_review', 'shared_storage_differs_from_sku', 'Thông số chung khác dung lượng SKU; phải giữ giá trị theo biến thể, không ghi đè bằng thông số chung.',
                    old=disk_values, ProductVariantId=variant['ProductVariantId'], Sku=variant['Sku'])
        own_rows = findings[start:]
        if not own_rows:
            add('valid', 'format_valid_unverified', 'Không phát hiện lỗi định dạng theo quy tắc; chưa có nghĩa mọi thông số đã được hãng xác nhận.')
        product_rows.append({**base, 'RootCategory': root['Name'], 'RootSlug': root['Slug'], 'Kind': kind,
                             'TechnicalValueCount': len(spec_leaves), 'ProposedValueCount': changed_count,
                             'ManufacturerCheckedValues': verified_count,
                             'VerificationStatus': ('verified' if spec_leaves and verified_count == len(spec_leaves)
                                                    else 'partial' if verified_count else 'unverified'),
                             'FindingCount': len(findings) - start})

    if used != set(source_index):
        raise ValueError('Evidence references a missing product or existing scalar path')
    validate_proposal(original, proposed, changes)
    manual = [r for r in findings if r['Classification'] == 'manual_review']
    # Coverage is explicit for every product; unchecked facts are not presented as technically certified.
    for row in product_rows:
        manual.append({**row, 'Classification': 'manual_review', 'Code': 'verification_coverage',
                       'Reason': 'Chỉ các giá trị có evidence mới được xác minh; các giá trị còn lại cần đối chiếu đúng model/khu vực.',
                       'Path': '', 'Attribute': '', 'Before': None, 'Proposed': None})
    summary = {'Products': len(product_rows), 'Variants': len(original['Tables']['ProductVariants']),
               'ClassificationCounts': dict(Counter(r['Classification'] for r in findings)),
               'FormatProposals': sum(r['Classification'] == 'format_only' for r in changes),
               'VerifiedCorrections': sum(r['Classification'] == 'verified_correction' for r in changes),
               'VerifiedErrors': sum(r['Code'] == 'manufacturer_correction' for r in changes),
               'VerifiedClarifications': sum(r['Code'] == 'manufacturer_clarification' for r in changes),
               'VerifiedMatches': sum(r['Code'] == 'manufacturer_match' for r in findings),
               'ManufacturerCheckedProducts': sum(p['ManufacturerCheckedValues'] > 0 for p in product_rows),
               'ReviewedValues': len(source_index), 'SourceRecords': len(evidence.get('Sources', [])),
               'MissingFindings': sum(r['Classification'] == 'missing' for r in findings),
               'ManualFindings': len(manual), 'ManualProducts': len({r['ProductId'] for r in manual}),
               'ProductsWithoutDetectedIssues': sum(not any(r['ProductId'] == p['ProductId'] and r['Classification'] not in ('valid',)
                                                         for r in findings) for p in product_rows),
               'FullyManufacturerVerifiedProducts': sum(p['VerificationStatus'] == 'verified' for p in product_rows),
               'ChangedProducts': len({c['ProductId'] for c in changes}),
               'UnchangedSchemaAndProtectedData': True, 'DatabaseWrites': 0}
    proposed['CatalogFingerprint'] = digest(proposed['Tables'])
    return {'proposed': proposed, 'findings': findings, 'changes': changes,
            'missing': [r for r in findings if r['Classification'] == 'missing'], 'manual': manual,
            'products': product_rows, 'summary': summary}


def csv_write(path, rows, fields=FIELDS):
    with path.open('w', encoding='utf-8-sig', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            cells = {k: json.dumps(v, ensure_ascii=False) if k in ('Before', 'Proposed') else v for k, v in row.items()}
            # Preserve raw values in JSON cells; neutralize formulas in display-only text columns.
            writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v for k, v in cells.items()})


def write_reports(folder, original, result):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'catalog-cleaned.json').write_text(json.dumps(result['proposed'], ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / 'catalog-summary.json').write_text(json.dumps(result['summary'], ensure_ascii=False, indent=2), encoding='utf-8')
    for name, key in [('catalog-audit.csv', 'findings'), ('catalog-changes.csv', 'changes'),
                      ('catalog-missing-specs.csv', 'missing'), ('catalog-manual-review.csv', 'manual')]:
        csv_write(folder / name, result[key])
    csv_write(folder / 'catalog-products.csv', result['products'],
              [*FIELDS[:6], 'RootCategory', 'RootSlug', 'Kind', 'TechnicalValueCount', 'ProposedValueCount',
               'ManufacturerCheckedValues', 'VerificationStatus', 'FindingCount'])


def source_candidates(original, evidence, manifest_path):
    """Legacy data supplies URLs only, after exact slug AND SKU matching; never supplies specifications."""
    legacy = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {'products': []}
    by_slug = {r['slug']: r for r in legacy['products']}
    reviewed = defaultdict(set)
    for row in evidence.get('Values', []):
        reviewed[row['ProductId']].add(row['SourceURL'])
    _, _, variants = inventory_context(original)
    rows = []
    for product in original['Tables']['Products']:
        own = variants[product['ProductId']]
        old = by_slug.get(product['Slug'])
        matches = old and old['sku'] in {v['Sku'] for v in own}
        rows.append({'ProductId': product['ProductId'], 'ProductName': product['Name'], 'Slug': product['Slug'],
                     'ProductVariantId': ';'.join(v['ProductVariantId'] for v in own), 'Sku': ';'.join(v['Sku'] for v in own),
                     'ManufacturerURLsReviewed': ';'.join(sorted(reviewed[product['ProductId']])),
                     'LegacySourceURL': old['source_url'] if matches else '',
                     'LegacyStatus': 'unverified_url_hint_only' if matches else 'no_exact_legacy_hint'})
    return rows


def validate_consumers(original, result):
    """Read the proposal using production Pydantic/AI readers, with no database/provider calls."""
    from app.schemas.catalog import ProductResponse, ProductVariantResponse
    proposed = result['proposed']
    validate_proposal(original, proposed, result['changes'])
    categories, _, variants = inventory_context(original)
    after = {p['ProductId']: p for p in proposed['Tables']['Products']}
    content_ids = {r['ProductId'] for r in result['changes'] if r['Classification'] == 'verified_correction'}
    changed_scores = []
    format_only = []
    for product in original['Tables']['Products']:
        new = after[product['ProductId']]
        response = ProductResponse.model_validate(new)
        if response.Specifications and '_vietech_variant_media' in response.Specifications:
            raise ValueError('Private media leaked through public schema')
        root, category = root_category(product, categories), categories[product['CategoryId']]
        before_sig = ai_signature(product, product['Specifications'], variants[product['ProductId']], category, root['Name'])
        after_sig = ai_signature(new, new['Specifications'], variants[product['ProductId']], category, root['Name'])
        if product['ProductId'] not in content_ids and before_sig != after_sig:
            raise ValueError('A format-only product changed AI interpretation')
        if product['ProductId'] not in content_ids:
            format_only.append(product['ProductId'])
        for old, current in zip(before_sig[0], after_sig[0]):
            if old != current:
                changed_scores.append({'ProductId': product['ProductId'], 'ProductVariantId': old[0], 'Reader': old[1],
                                       'Needs': old[2], 'BeforeScore': old[3], 'ProposedScore': current[3],
                                       'BeforeCompleteness': old[4], 'ProposedCompleteness': current[4],
                                       'Reason': 'Manufacturer-verified content changed; requires approval with proposal'})
    for variant in proposed['Tables']['ProductVariants']:
        ProductVariantResponse.model_validate(variant)
    laptops, monitors = [], []
    for product in original['Tables']['Products']:
        slug = root_category(product, categories)['Slug']
        if slug == 'laptop':
            laptops.append(product)
        elif slug == 'man-hinh' and not re.search(r'\b(?:gia treo|tay treo)\b', fold(product['Name'])):
            monitors.append(product)
    comparisons, status_changes, advanced_positive = 0, [], 0
    for laptop in laptops:
        for monitor in monitors:
            for request in [VideoRequest(), VideoRequest(Width=3840, Height=2160, RefreshHz=144)]:
                def checked(p, q):
                    return check_compatibility(normalize_video_specs(p['Specifications']),
                                               normalize_video_specs(q['Specifications']), request).status
                old_status, new_status = checked(laptop, monitor), checked(after[laptop['ProductId']], after[monitor['ProductId']])
                comparisons += 1
                if request.Width and new_status in ('compatible', 'requires_adapter'):
                    advanced_positive += 1
                if old_status != new_status:
                    if not {laptop['ProductId'], monitor['ProductId']} & content_ids:
                        raise ValueError('Format-only change altered compatibility')
                    status_changes.append({'LaptopId': laptop['ProductId'], 'MonitorId': monitor['ProductId'],
                                           'Request': request.model_dump(), 'Before': old_status, 'Proposed': new_status})
    return {'ProductResponseValidations': len(after), 'ProductVariantResponseValidations': len(proposed['Tables']['ProductVariants']),
            'FormatOnlyProductsAIUnchanged': len(format_only), 'NeedProfilesPerSKUPerReader': len(NEEDS) + 1,
            'VerifiedContentScoreChanges': changed_scores, 'CompatibilityPairScenarios': comparisons,
            'CompatibilityStatusChanges': status_changes, 'Advanced4K144PositiveScenarios': advanced_positive,
            'ProtectedInvariants': True, 'DatabaseWrites': 0}
