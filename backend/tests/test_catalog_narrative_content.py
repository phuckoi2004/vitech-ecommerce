"""Reviewed facts stay in the right topic without inventing specification keys."""
import json
import re
from pathlib import Path

import pytest

EVIDENCE = json.loads((Path(__file__).resolve().parents[1] / 'data/catalog-narrative-evidence-2026-10-30.json').read_text(encoding='utf-8'))


def item(fragment):
    matches = [row for row in EVIDENCE['Products'] if fragment in row['Name']]
    assert len(matches) == 1
    return matches[0]


def prose(fragment, section):
    return ' '.join(edit['After'] for edit in item(fragment)['DescriptionEdits'] if edit['Section'].startswith(section))


@pytest.mark.parametrize(('fragment', 'weight'), [
    ('SFA14-I31-55NR', '1,19 kg'), ('GL6J-9LJ', 'khoảng 2,2 kg'),
    ('MacBook Air M2', '1,24 kg'), ('MacBook Air M4', '1,24 kg'),
    ('MacBook Air M5 15', '1,51 kg'), ('A13UC-2082VN', '1,98 kg'),
])
def test_weight_is_written_in_intro_without_becoming_a_new_attribute(fragment, weight):
    row = item(fragment)
    assert weight in prose(fragment, 'intro')
    assert 'Trọng lượng' not in row['Fields'] and 'Dung lượng RAM' not in row['Fields']


def test_camera_processor_and_switch_details_stay_in_their_own_sections():
    assert 'Camera trước 8 MP' in prose('HONOR Pad V9', 'Camera')
    assert 'Camera sau' not in item('HONOR Pad V9')['Fields']
    assert 'Kirin T92C 6 nhân' in prose('MatePad 11.5 S 2026', 'Hiệu năng')
    assert 'Chipset' not in item('MatePad 11.5 S 2026')['Fields']
    assert 'ROG HFX V2' in prose('ROG Azoth', 'Hoàn thiện')
    assert 'switch' not in item('ROG Azoth')['Fields']['Phương thức kết nối'].lower()


def test_teardown_memory_is_scoped_to_exact_models_and_not_reused_for_regular_iphone17():
    for model, ram in [('iPhone Air 256GB', '12 GB'), ('iPhone 17 Pro 256GB', '12 GB'), ('iPhone 16e 128GB', '8 GB')]:
        row = item(model)
        assert row['SourceKind'] == 'primary_teardown'
        assert any('/Teardown/' in source for source in row['Sources'])
        assert f'RAM {ram} chuẩn LPDDR5X' in prose(model, 'Hiệu năng')
        assert 'GPU' not in row['Fields'] and 'Loại CPU' not in row['Fields'] and 'Dung lượng RAM' not in row['Fields']
    assert not any(row['Name'] == 'iPhone 17 256GB' for row in EVIDENCE['Products'])


@pytest.mark.parametrize(('model', 'local', 'stream'), [
    ('iPhone 16 128GB', 22, 18), ('iPhone 16 Pro Max', 33, 29),
    ('iPhone 17 Pro 256GB', 31, 28), ('iPhone 17 Pro Max', 37, 33),
])
def test_battery_does_not_invent_capacity_or_mix_pro_and_max_runtimes(model, local, stream):
    text = prose(model, 'Pin')
    assert f'lên đến {local} giờ' in text and f'lên đến {stream} giờ' in text
    assert 'theo phép thử của Apple' in text and 'mAh' not in text
    assert 'Pin' not in item(model)['Fields']


def test_existing_values_keep_related_meanings_and_no_redundant_technical_appendix():
    assert '2772 x 1280' in item('Xiaomi 17T Pro')['Fields']['Tính năng màn hình']
    assert 'HyperOS 3' in prose('Xiaomi 17T Pro', 'Hiệu năng')
    assert 'One UI 7' in prose('Samsung Galaxy S25 Plus', 'Hiệu năng')
    assert 'Bluetooth 5.0 là chế độ kết nối riêng' in prose('ROG Azoth', 'Kết nối')
    for row in EVIDENCE['Products']:
        for edit in row['DescriptionEdits']:
            assert '<h2>Thông số kỹ thuật chi tiết</h2>' not in edit['After']
            assert '<ul>' not in edit['After'] and '<table' not in edit['After']
            visible = re.sub('<[^>]*>', '', edit['After'])
            assert ';' not in re.sub(r'&(?:#\d+|#x[0-9a-f]+|[a-z][a-z0-9]*);', '', visible)
