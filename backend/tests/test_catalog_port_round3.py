"""Manufacturer provenance and reader behavior for LG 4K / Swift Air round 3, offline only."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from catalog_standardization import validate_evidence
from app.schemas.ai_compatibility import VideoRequest
from app.services.compatibility import PUBLISHED_NOTE, check_compatibility
from app.services.compatibility_specs import normalize_video_specs
from tests.test_catalog_standardization import evidence, original

EVIDENCE = Path(__file__).resolve().parents[1] / 'data/catalog-port-evidence-round3-2026-10-29.json'


def correction(pid):
    return next(v for v in json.loads(EVIDENCE.read_text(encoding='utf-8'))['Values']
                if v['ProductId'] == pid and v['Decision'] == 'correction')


@pytest.mark.parametrize('url', [
    'https://global-download.acer.com/manual.pdf', 'https://www.lge.co.kr/monitors/27g850a',
    'https://edravn.com/gia-do-man-hinh-edra-ema7310',
])
def test_review_accepts_only_the_reviewed_manufacturer_hosts(url):
    snapshot = original()
    item = evidence(snapshot, SourceURL=url)['Values'][0]
    validate_evidence(item, snapshot['Tables']['Products'][0], ('Dung lượng RAM',), '16GB')


@pytest.mark.parametrize('url', [
    'https://global-download.acer.com.attacker.example/manual.pdf', 'https://acer.example/manual.pdf',
    'http://global-download.acer.com/manual.pdf', 'https://lge.co.kr.attacker.example/specs',
    'https://edravn.com.attacker.example/specs', 'https://iternix.co.th/retailer-specs',
])
def test_lookalikes_and_retailers_cannot_authorize_manufacturer_corrections(url):
    snapshot = original()
    item = evidence(snapshot, SourceURL=url)['Values'][0]
    with pytest.raises(ValueError, match='manufacturer evidence'):
        validate_evidence(item, snapshot['Tables']['Products'][0], ('Dung lượng RAM',), '16GB')


def lg_profile():
    item = correction('1ed340b9-02e6-49d3-b40d-211e9bdbeae8')
    return normalize_video_specs({'Cổng kết nối': item['Proposed']}, device_kind='monitor')


def test_lg_has_per_input_4k_and_dual_mode_limits_without_fabricated_signal_details():
    ports = [p for p in lg_profile().ports if p.usable('input')]
    assert {p.connector for p in ports} == {'hdmi', 'displayport'}
    for port in ports:
        assert port.limits and not port.inferred
        assert {(m.width, m.height, m.hz) for m in port.modes} == {(3840, 2160, 240), (1920, 1080, 480)}
        assert all(m.color is None and m.bits is None and m.dsc is None for m in port.modes)


@pytest.mark.parametrize('hz', [60, 144, 240])
def test_lg_accepts_a_published_4k_mode_only_with_r4b_cable_and_signal_limitations(hz):
    source = normalize_video_specs({'Cổng giao tiếp': f'HDMI 2.1 (xuất hình tối đa 4K@{hz}Hz)'}, device_kind='laptop')
    result = check_compatibility(source, lg_profile(), VideoRequest(Width=3840, Height=2160, RefreshHz=hz))
    assert result.status == 'compatible'
    assert PUBLISHED_NOTE in result.limitations
    assert f'Cáp hoặc bộ chuyển đổi phải hỗ trợ 3840×2160 @ {hz} Hz.' in result.conditions


def test_a_version_without_published_laptop_timing_still_cannot_confirm_4k60():
    source = normalize_video_specs({'Cổng giao tiếp': 'HDMI 2.1'}, device_kind='laptop')
    result = check_compatibility(source, lg_profile(), VideoRequest(Width=3840, Height=2160, RefreshHz=60))
    assert result.status == 'unknown'


def test_swift_manual_confirms_basic_dp_over_usb_c_without_inventing_4k_hz():
    item = correction('af1642ca-c06a-416a-8514-db105f4b4d99')
    assert item['SourceURL'].startswith('https://global-download.acer.com/')
    assert '1x USB-C' not in item['Proposed']  # DC-in is no longer misrepresented as a third USB-C socket.
    source = normalize_video_specs({'Cổng giao tiếp': item['Proposed']}, device_kind='laptop')
    outputs = [p for p in source.ports if p.usable('output')]
    assert outputs and all(not p.inferred for p in outputs)
    assert all(not p.modes and p.max_resolution is None and p.max_hz is None for p in outputs)
    assert all(p.alt_mode is True for p in outputs)
    assert check_compatibility(source, lg_profile(), VideoRequest()).status == 'requires_adapter'
    assert check_compatibility(source, lg_profile(), VideoRequest(Width=3840, Height=2160, RefreshHz=60)).status == 'unknown'


def test_mounts_keep_verified_mechanical_values_and_do_not_gain_video_ports():
    values = json.loads(EVIDENCE.read_text(encoding='utf-8'))['Values']
    corrections = [v for v in values if v['Decision'] == 'correction']
    assert len(corrections) == 2 and {v['Path'] for v in corrections} == {'/Cổng giao tiếp', '/Cổng kết nối'}
    for pid in ('1000f3e8-59ff-4555-ae56-277b70d842fc', '406a2e3f-d0a8-44e4-aa93-e0b8d1a97050'):
        matched = [v for v in values if v['ProductId'] == pid and v['Decision'] == 'verified_match']
        assert len(matched) == 2 and all(v['Before'] == v['Proposed'] for v in matched)
        profile = normalize_video_specs({v['Path'][1:]: v['Proposed'] for v in matched}, device_kind='monitor')
        assert not profile.ports
    unresolved = [v for v in values if v['Decision'] == 'manual_review']
    assert len(unresolved) == 1 and unresolved[0]['Before'] == unresolved[0]['Proposed']
