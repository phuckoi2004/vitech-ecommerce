"""Product-specific comparisons, readable cameras and bounded claims, entirely offline."""
import copy
import uuid
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from app.services.ai_comparison import build_comparison, normalized_specs
from app.services.ai_comparison_details import camera_parts, narrative_ram

RENO = {'Chipset': 'Dimensity 7300-Energy 5G', 'Dung lượng RAM': '8 GB', 'GPU': 'Arm Mali-G615@1.047 GHz',
        'Kích thước màn hình': '6.57 inch', 'Công nghệ màn hình': 'AMOLED',
        'Độ phân giải màn hình': '1080 x 2372 pixels (FullHD+)', 'Tính năng màn hình': 'Tần số quét 120 Hz',
        'Pin': '7000 mAh', 'Camera sau': '50 MP OIS, f/1.8; 8 MP góc rộng, f/2.2; 50 MP OIS Tele, f/2.8',
        'Camera trước': '50 MP, f/2.0', 'Bộ nhớ trong': '256 GB'}
FIND = {'Chipset': 'Qualcomm Snapdragon 8 Gen 1', 'Loại CPU': 'MariSilicon X Imaging NPU',
        'Dung lượng RAM': '12 GB', 'GPU': 'Adreno 730 @818 MHz', 'Kích thước màn hình': '6.7 inch',
        'Công nghệ màn hình': 'AMOLED', 'Độ phân giải màn hình': '1440 x 3216 pixels (QHD+)',
        'Tính năng màn hình': 'Tần số quét 120 Hz (Dynamic)', 'Pin': '5.000 mAh',
        'Camera sau': 'Camera chính: 50 MP, f/1.7; Camera góc rộng: 50 MP, f/2.2; FOV 112°; Camera tele: 13 MP, f/2.4',
        'Camera trước': 'Camera chính 32 MP: f/2.4; FOV 90°, ống kính: 5P, lấy nét cố định', 'Bộ nhớ trong': '256 GB'}


def variant(ram=None):
    return NS(ProductVariantId=uuid.uuid4(), VariantName=f'{ram} GB / 256 GB' if ram else '256 GB',
              Storage='256 GB', Color='Đen', SalePrice=None, Price=Decimal('15000000'), StockQuantity=2)


def comparison(question='So sánh OPPO Reno16 F và OPPO Find X5 Pro', specs=None, descriptions=None):
    items = []
    for i, (name, source) in enumerate(zip(('OPPO Reno16 F 5G 8GB 256GB', 'OPPO Find X5 Pro 5G 12GB 256GB'), specs or (RENO, FIND))):
        detail = NS(ProductId=uuid.uuid4(), Name=name, Slug=f'phone-{i}', BrandId=uuid.uuid4(), CategoryId=uuid.uuid4(),
                    Category=NS(Name='Điện thoại'), Brand=NS(Name='OPPO'), Specifications=copy.deepcopy(source),
                    Description=descriptions[i] if descriptions else '', VariantImages={}, Images=[])
        items.append((detail, variant()))
    intent = NS(needs=(), max_budget=None, soft_brands=lambda: ())
    context = NS(question=question, intent=intent, vocab=NS(kind=lambda _id: 'phone'))
    return build_comparison(items, context, '2026-10-30T00:00:00Z')


def test_customer_camera_case_uses_model_names_separate_lenses_and_practical_differences():
    result = comparison()
    rows = {row['Key']: row['Values'] for row in result['Rows']}
    assert rows['cpu'] == ['Dimensity 7300-Energy 5G', 'Qualcomm Snapdragon 8 Gen 1']
    assert rows['imaging'] == ['Chưa có dữ liệu', 'MariSilicon X Imaging NPU']
    assert rows['camera'][0].splitlines() == ['50 MP OIS, f/1.8', '8 MP góc rộng, f/2.2', '50 MP OIS Tele, f/2.8']
    assert 'Camera góc rộng: 50 MP, f/2.2, FOV 112°' in rows['camera'][1].splitlines()
    differences = '\n'.join(result['Differences'])
    assert 'mẫu 1' not in differences and 'mẫu 2' not in differences
    assert 'Chênh lệch cao nhất 4 GB' in differences
    assert '2000 mAh' in differences and 'độ phân giải cao hơn' in differences.lower()
    assert 'Camera góc rộng:' in differences and 'Camera tele:' in differences
    assert 'xung MHz giữa hai kiến trúc khác nhau' in differences
    assert 'mở nhiều ứng dụng' in result['Recommendation']
    assert 'OPPO Reno16 F' in result['Recommendation'] and 'OPPO Find X5 Pro' in result['Recommendation']
    assert result['RecommendedProductVariantId'] is None
    assert any('Cortex-A78' in line for line in result['Products'][0]['Strengths'])
    assert any('Cortex-X2' in line for line in result['Products'][1]['Strengths'])


def test_color_is_omitted_by_default_and_shown_only_when_requested():
    assert not any(row['Key'] == 'color' for row in comparison()['Rows'])
    explicit = comparison('So sánh hai điện thoại về màu sắc và camera')
    assert any(row['Key'] == 'color' for row in explicit['Rows'])
    assert 'màu sắc' in explicit['Needs']
    negative = comparison('So sánh hai điện thoại, không cần so sánh màu sắc')
    assert not any(row['Key'] == 'color' for row in negative['Rows'])


@pytest.mark.parametrize('bad', [
    '<h2>Camera</h2><p>RAM 12 GB.</p>',
    '<h2>Hiệu năng</h2><p>Có thể nâng cấp RAM 12 GB.</p>',
    '<h2>Hiệu năng</h2><p>RAM 8 GB hoặc 12 GB.</p>',
    '<h2>Hiệu năng</h2><p>RAM 8 GB.</p><p>RAM 12 GB.</p>',
    '<h2>Hiệu năng</h2><img alt="RAM 12 GB"><script>RAM 12 GB</script>',
])
def test_description_does_not_invent_ram_from_other_topics_upgrades_or_untrusted_hidden_text(bad):
    assert narrative_ram(bad) is None


def test_verified_narrative_ram_fills_missing_cell_but_explicit_sku_still_wins():
    description = '<h2>Hiệu năng Chip A19</h2><p>RAM 8 GB phối hợp với bộ xử lý.</p><h2>Camera</h2>'
    assert normalized_specs({}, variant(), 'phone', description=description)['ram'] == '8 GB'
    assert normalized_specs({'RAM':'6 GB'}, variant(), 'phone', description=description)['ram'] == '6 GB'
    assert normalized_specs({}, variant(12), 'phone', description=description)['ram'] == '12 GB'
    with_ram = comparison(specs=({}, {}), descriptions=(description, description))
    assert next(row for row in with_ram['Rows'] if row['Key'] == 'ram')['Values'] == ['8 GB', '8 GB']


def test_missing_features_cannot_generate_architecture_or_winner_claims():
    result = comparison(specs=({}, {}))
    text = '\n'.join(p['Strengths'][0] if p['Strengths'] else '' for p in result['Products'])
    assert 'Cortex' not in text and 'chơi game' not in text
    assert result['RecommendedProductVariantId'] is None


def test_marisilicon_alone_never_becomes_an_application_cpu():
    specs = normalized_specs({'Loại CPU':'MariSilicon X Imaging NPU'}, variant(), 'phone')
    assert 'cpu' not in specs and specs['imaging'] == 'MariSilicon X Imaging NPU'


def test_camera_details_do_not_truncate_long_modules_or_separate_field_of_view_from_its_lens():
    camera = FIND['Camera sau'] + '; hỗ trợ ' + 'ghi hình ' * 18
    camera += '; Camera tele phụ: 10 MP, f/3.0'
    specs = normalized_specs({'Camera sau':camera}, variant(), 'phone')
    assert 'Camera tele phụ: 10 MP, f/3.0' in specs['camera']
    assert 'FOV 112°' in camera_parts(specs['camera'])[1]


def test_negative_ois_does_not_turn_into_a_strength():
    result = comparison(specs=({**RENO, 'Camera sau':'50 MP, không có OIS'}, FIND))
    assert not any('OIS hỗ trợ giảm' in line for line in result['Products'][0]['Strengths'])
