"""VN variant matching and RAM evidence do not become invented specification keys."""
import json
import re
from pathlib import Path

import pytest

EVIDENCE = json.loads((Path(__file__).resolve().parents[1] / 'data/catalog-vietnam-evidence-2026-10-30.json').read_text(encoding='utf-8'))


def reviewed(name):
    return next(p for p in EVIDENCE['Products'] if p['Name'] == name)


def check(name):
    return next(p for p in EVIDENCE['VietnamCrossChecks'] if p['Name'] == name)


@pytest.mark.parametrize(('name', 'ram', 'storage'), [
    ('iPhone 17 256GB', 8, '256 GB'), ('iPhone 17 Pro Max 512GB', 12, '512 GB'),
    ('iPhone 18 Pro 1TB', 12, '1 TB'), ('iPhone 18 Pro Max 1TB', 12, '1 TB'),
    ('iPad A16 Wifi 256GB 2025', 6, '256 GB'),
])
def test_every_missing_ram_is_written_only_in_performance_description_of_exact_variant(name, ram, storage):
    row = reviewed(name)
    assert row['Fields'] == {} and len(row['DescriptionEdits']) == 1
    edit = row['DescriptionEdits'][0]
    assert edit['Section'] == 'Hiệu năng' and f'RAM {ram} GB' in edit['After']
    assert f'RAM {ram} GB' not in edit['Before']
    assert storage in row['VariantScope'] and row['VietnamSources']
    assert check(name)['ApplePublishedRAM'] is False
    assert '<h2>Thông số kỹ thuật chi tiết</h2>' not in edit['After']


@pytest.mark.parametrize('name', ['iPhone 18 Pro 1TB', 'iPhone 18 Pro Max 1TB'])
def test_empty_local_ram_cell_is_not_misrepresented_as_manufacturer_confirmation(name):
    data = check(name)
    assert data['LocalStructuredRAM'] == ''
    assert data['VerificationBasis'] == 'vn_variant_plus_xcode'
    assert 'https://www.macrumors.com/2026/09/09/iphone-18-pro-and-pro-max-ram/' in data['Sources']
    assert 'sku=' in data['VietnamSources'][0]
    assert data['Value'] == '12 GB'


def test_regional_details_not_confirmed_in_vietnam_are_removed_without_erasing_verified_facts():
    name = 'HONOR Pad V9 Wifi 8GB 256GB'
    edit = reviewed(name)['DescriptionEdits'][0]
    assert 'Camera trước 8 MP' in edit['After']
    old_front = re.search(r'<p>Camera trước.*?</p>', edit['Before'])[0]
    new_front = re.search(r'<p>Camera trước.*?</p>', edit['After'])[0]
    assert 'f/2.0' in old_front and 'f/2.0' not in new_front
    assert '<strong>13MP, f/2.0</strong>' in edit['After']  # Rear camera stays intact.
    assert 'lấy nét cố định' not in edit['After']
    assert 'RAM 8 GB' in check(name)['Value'] and '256 GB' in check(name)['Value']
    name = 'Huawei MatePad 11.5 S 2026 12GB 256GB - Kèm bàn phím'
    edit = reviewed(name)['DescriptionEdits'][0]
    assert 'Kirin T92C 6 nhân' in edit['Before'] and 'Kirin T92C' in edit['After']
    assert 'Kirin T92C 6 nhân' not in edit['After']
    assert check(name)['ManufacturerVietnamPublishesCPU'] is False


@pytest.mark.parametrize(('name', 'ram'), [('iPhone Air 256GB', 12), ('iPhone 16e 128GB', 8), ('iPhone 17 Pro 256GB', 12)])
def test_already_correct_ram_has_vietnam_sources_and_is_not_rewritten(name, ram):
    data = check(name)
    assert data['Value'] == f'{ram} GB' and data['VietnamSources']
    assert data['Action'] == 'verified_existing_description'
    assert not any(p['Name'] == name for p in EVIDENCE['Products'])
