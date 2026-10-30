"""Regression checks for the reviewed completion values, without a shared database."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from catalog_standardization import validate_evidence
from app.schemas.ai_compatibility import VideoRequest
from app.services.compatibility import check_compatibility
from app.services.compatibility_specs import normalize_video_specs

EVIDENCE = json.loads((Path(__file__).resolve().parents[1] / 'data/catalog-completion-evidence-2026-10-30.json').read_text(encoding='utf-8'))
VALUES = EVIDENCE['Values']


def value(fragment, key):
    return next(v for v in VALUES if fragment in v['ProductName'] and v['Path'] == '/' + key)


def profile(fragment, *, monitor=False):
    key = 'Cổng kết nối' if monitor else 'Cổng giao tiếp'
    return normalize_video_specs({key: value(fragment, key)['Proposed']}, device_kind='monitor' if monitor else 'laptop')


def modes(port):
    return {(m.width, m.height, m.hz) for m in port.modes}


def test_review_has_unique_existing_scalar_paths_and_primary_sources():
    assert len(VALUES) == 49
    assert len({v['ProductId'] for v in VALUES}) == 32
    assert len({(v['ProductId'], v['Path']) for v in VALUES}) == len(VALUES)
    source_urls = {s['URL'] for s in EVIDENCE['Sources']}
    for item in VALUES:
        assert item['Path'].count('/') == 1
        assert item['Path'] != '/Description' and not item['Path'].startswith('/_')
        assert isinstance(item['Before'], str) and isinstance(item['Proposed'], str)
        assert item['Before'] != item['Proposed']
        assert not any(c in item['Proposed'] for c in (';', '；'))
        assert item['SourceURL'] in source_urls
        validate_evidence(item, {'ProductId': item['ProductId'], 'Name': item['ProductName']},
                          (item['Path'][1:],), item['Before'])


@pytest.mark.parametrize('domain', ['gigabyte.com', 'meizu.com', 'vsp.vn'])
@pytest.mark.parametrize('url_format', ['https://www.{}/spec', 'https://{}.attacker.example/spec', 'http://{}/spec'])
def test_new_manufacturers_cannot_be_impersonated(domain, url_format):
    item = {**VALUES[0], 'SourceURL': url_format.format(domain)}
    product = {'ProductId': item['ProductId'], 'Name': item['ProductName']}
    if url_format == 'https://www.{}/spec':
        validate_evidence(item, product, (item['Path'][1:],), item['Before'])
    else:
        with pytest.raises(ValueError, match='manufacturer evidence'):
            validate_evidence(item, product, (item['Path'][1:],), item['Before'])


def test_native_refresh_does_not_invent_external_port_limits():
    for fragment, hz in [('SFA14-I31-55NR', 120), ('ANV15-52-50VA', 180), ('FX607VJ-RL034W', 144)]:
        text = value(fragment, 'Công nghệ màn hình')['Proposed']
        assert text.startswith(f'Tần số quét {hz} Hz,')
        # A built-in display's Hz must never become an external HDMI or DP mode.
        assert not normalize_video_specs({'Công nghệ màn hình': text}, device_kind='laptop').ports
    assert not any(v['Path'] == '/Cổng giao tiếp' and 'SFA14-I31-55NR' in v['ProductName'] for v in VALUES)


def test_phone_refresh_is_not_touch_sampling_or_backlight_frequency():
    assert value('Xiaomi 17T Pro 5G', 'Tính năng màn hình')['Proposed'].startswith('Tần số quét tối đa 144 Hz,')
    assert value('Xiaomi 17T 5G', 'Tính năng màn hình')['Proposed'].startswith('Tần số quét tối đa 120 Hz,')
    assert value('Mblu 22 Pro', 'Công nghệ màn hình')['Proposed'].startswith('Tần số quét tối đa 120 Hz,')
    camera = value('Xiaomi 17T 5G', 'Camera sau')['Proposed']
    assert 'tele tiềm vọng Leica 50 MP' in camera and 'Tele 0 MP' not in camera
    assert '67 W' in value('Xiaomi 17T 5G', 'Pin')['Proposed']
    assert '100 W' in value('Xiaomi 17T Pro 5G', 'Pin')['Proposed']


def test_data_only_usb_c_does_not_gain_video_from_another_port():
    ports = profile('D0BG7PA').ports
    usb = next(p for p in ports if p.connector == 'usb_c')
    hdmi = next(p for p in ports if p.connector == 'hdmi')
    assert usb.video is False and not usb.modes
    assert hdmi.usable('output') and not hdmi.modes
    vivobook = profile('X1404VA-EB355W').ports
    assert not any(p.usable('output') for p in vivobook if p.connector == 'usb_c')


def test_msi_laptop_limits_stay_on_hdmi_and_do_not_spread_to_usb_c():
    for fragment, expected in [
        ('Modern 15 F1MG-1225VN', {(3840, 2160, 30)}),
        ('Cyborg 15 A13UC-2082VN', {(3840, 2160, 60)}),
        ('Katana 15 B13VEK-2440VN', {(7680, 4320, 60), (3840, 2160, 120)}),
    ]:
        ports = profile(fragment).ports
        assert modes(next(p for p in ports if p.connector == 'hdmi')) == expected
        usb = [p for p in ports if p.connector == 'usb_c']
        assert usb and all(p.usable('output') and p.alt_mode is True and not p.modes for p in usb)


@pytest.mark.parametrize('fragment', ['GL6J-9LJR2VNF93SH', 'X1407CA-LY203W', 'FX607VJ-RL034W', 'BQ5D8PT'])
def test_direction_clarification_never_invents_per_port_modes(fragment):
    ports = profile(fragment).ports
    assert any(p.usable('output') for p in ports)
    assert all(not p.modes for p in ports)


def test_portable_msi_has_explicit_fhd60_on_each_digital_input():
    ports = profile('MP165 E6', monitor=True).ports
    assert {p.connector for p in ports} == {'usb_c', 'hdmi'}
    assert all(p.usable('input') and modes(p) == {(1920, 1080, 60)} for p in ports)
    assert all(m.color is None and m.bits is None and m.dsc is None for p in ports for m in p.modes)
    assert value('MP165 E6', 'Kích thước thực tế (bao gồm viền)')['Proposed'] == '15.6 inch'


@pytest.mark.parametrize('hz,status', [(60, 'compatible'), (120, 'incompatible')])
def test_portable_msi_does_not_inherit_laptop_hdmi_120hz(hz, status):
    laptop = profile('Katana 15 B13VEK-2440VN')
    monitor = profile('MP165 E6', monitor=True)
    assert check_compatibility(laptop, monitor, VideoRequest(Width=1920, Height=1080, RefreshHz=hz)).status == status
