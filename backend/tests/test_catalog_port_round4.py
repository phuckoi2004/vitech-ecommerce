"""New manufacturer input data must stay on the correct port, without changing schema or other product values."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from catalog_standardization import validate_evidence
from app.schemas.ai_compatibility import VideoRequest
from app.services.compatibility import check_compatibility
from app.services.compatibility_specs import normalize_video_specs
from tests.test_catalog_standardization import evidence, original

PATH = Path(__file__).resolve().parents[1] / 'data/catalog-port-evidence-round4-2026-10-30.json'
VALUES = json.loads(PATH.read_text(encoding='utf-8'))['Values']


def ports(pid):
    item = next(value for value in VALUES if value['ProductId'] == pid)
    return normalize_video_specs({'Cổng kết nối': item['Proposed']}, device_kind='monitor').ports


def modes(port):
    return {(mode.width, mode.height, mode.hz) for mode in port.modes}


def test_six_corrections_are_exact_existing_string_fields_with_primary_provenance():
    assert len(VALUES) == len({value['ProductId'] for value in VALUES}) == 6
    for value in VALUES:
        assert value['Path'] == '/Cổng kết nối' and value['Decision'] == 'correction'
        assert isinstance(value['Before'], str) and isinstance(value['Proposed'], str)
        assert value['Before'] != value['Proposed']
        product = {'ProductId': value['ProductId'], 'Name': value['ProductName']}
        validate_evidence(value, product, ('Cổng kết nối',), value['Before'])


@pytest.mark.parametrize('url', ['https://www.viewsonic.com/global/products/lcd/VA2708-2K-MHD',
                                 'https://www.viewsonicglobal.com/public/manual.pdf'])
def test_viewsonic_owned_product_and_download_hosts_are_accepted(url):
    snapshot = original()
    item = evidence(snapshot, SourceURL=url)['Values'][0]
    validate_evidence(item, snapshot['Tables']['Products'][0], ('Dung lượng RAM',), '16GB')


@pytest.mark.parametrize('url', ['https://viewsonic.com.attacker.example/manual.pdf',
                                 'https://viewsonicglobal.example/manual.pdf',
                                 'http://www.viewsonicglobal.com/manual.pdf'])
def test_similar_or_unencrypted_hosts_cannot_authorize_a_write(url):
    snapshot = original()
    item = evidence(snapshot, SourceURL=url)['Values'][0]
    with pytest.raises(ValueError, match='manufacturer evidence'):
        validate_evidence(item, snapshot['Tables']['Products'][0], ('Dung lượng RAM',), '16GB')


def test_lg_27g610a_hdmi_144_and_dp_200_are_never_swapped():
    profile = ports('4e16f4a8-996a-4810-9037-57326a1e174d')
    assert [(p.connector, modes(p)) for p in profile] == [
        ('hdmi', {(2560, 1440, 144)}), ('displayport', {(2560, 1440, 200)})]
    assert all(p.direction == 'input' and not p.inferred for p in profile)


def test_lg_24u631a_has_explicit_qhd100_on_both_hdmi_and_usb_c():
    profile = ports('79127e04-ac3b-4679-81f3-a485f07502fa')
    assert {p.connector for p in profile} == {'hdmi', 'usb_c'}
    assert all(modes(p) == {(2560, 1440, 100)} and p.usable('input') for p in profile)


def test_lg_24u411a_dsub_does_not_create_an_extra_hdmi_mode():
    profile = ports('4b94cd26-3648-49d5-969c-13316fb87eca')
    assert len(profile) == 1 and profile[0].connector == 'hdmi'
    assert modes(profile[0]) == {(1920, 1080, 120)}


def test_dell_dp_out_and_data_usb_do_not_inherit_displayport_input_modes():
    profile = ports('994b21cc-e898-4fd8-8c5f-e011fa2081b3')
    dp_in = [p for p in profile if p.connector == 'displayport' and p.direction == 'input']
    dp_out = [p for p in profile if p.connector == 'displayport' and p.direction == 'output']
    assert len(dp_in) == len(dp_out) == 1 and modes(dp_in[0]) == {(1920, 1080, 120)}
    assert not dp_out[0].modes
    assert all(not p.usable('input') and not p.modes for p in profile if p.connector == 'usb_c')


def test_asus_portable_monitor_accepts_usb_c_and_mini_hdmi_at_fhd60_only():
    profile = ports('7b6e5dbc-ab5c-4890-89f9-5857ecff0ddb')
    assert {p.connector for p in profile} == {'usb_c', 'hdmi'}
    assert all(modes(p) == {(1920, 1080, 60)} and p.usable('input') for p in profile)


def test_viewsonic_input_limits_match_the_guide_without_invented_signal_format():
    profile = ports('9c384149-98c5-4ec1-96b2-2206462aef0a')
    assert {p.connector for p in profile} == {'hdmi', 'displayport'}
    assert all(modes(p) == {(2560, 1440, 100)} for p in profile)
    assert all(mode.color is None and mode.bits is None and mode.dsc is None for p in profile for mode in p.modes)


@pytest.mark.parametrize('hz,status', [(60, 'compatible'), (144, 'compatible'), (200, 'incompatible')])
def test_hdmi_cannot_reach_dp200_on_lg_27g610a(hz, status):
    laptop = normalize_video_specs({'Cổng giao tiếp': 'HDMI 2.1 (xuất hình tối đa 4K@240Hz)'}, device_kind='laptop')
    value = next(value for value in VALUES if value['ProductId'] == '4e16f4a8-996a-4810-9037-57326a1e174d')
    monitor = normalize_video_specs({'Cổng kết nối': value['Proposed']}, device_kind='monitor')
    result = check_compatibility(laptop, monitor, VideoRequest(Width=2560, Height=1440, RefreshHz=hz))
    assert result.status == status
