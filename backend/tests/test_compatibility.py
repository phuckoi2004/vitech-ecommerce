"""Pure rules and spec normalization: no database, Gemini, network or invented catalog entries."""

import pytest

from app.schemas.ai_compatibility import VideoRequest
from app.services.compatibility import check_compatibility
from app.services.compatibility_specs import normalize_video_specs


def port(connector="HDMI", **kwargs):
    return {"Connector": connector, **kwargs}


def mode(width=3840, height=2160, hz=144, **kwargs):
    return {"Width": width, "Height": height, "RefreshHz": hz, **kwargs}


def profiles(outputs, inputs, complete=True, **source):
    return (normalize_video_specs({"VideoOutputs": outputs, "VideoOutputsComplete": complete, **source}),
            normalize_video_specs({"VideoInputs": inputs, "VideoInputsComplete": complete}))


def criterion(result, key):
    return next(c for c in result.criteria if c.Id == key)


def test_explicit_hdmi_video_output_and_input_confirm_only_basic_connection():
    laptop, display = profiles([port()], [port()])
    result = check_compatibility(laptop, display, VideoRequest())
    assert result.status == "compatible" and criterion(result, "connection").Status == "compatible"
    assert result.conditions and "HDMI" in result.conditions[0]


def test_basic_connection_does_not_confirm_4k_144_even_with_hdmi_21():
    laptop, display = profiles([port(Version="2.1")], [port(Version="2.1")])
    result = check_compatibility(laptop, display, VideoRequest(Width=3840, Height=2160, RefreshHz=144))
    assert result.status == "unknown"
    assert criterion(result, "connection").Status == "compatible"
    assert criterion(result, "signal_mode").Status == "unknown"
    assert result.missing


def test_source_only_output_capability_does_not_confirm_requested_4k144():
    laptop = normalize_video_specs({"HDMI output": "2.1"})
    result = check_compatibility(laptop, None, VideoRequest(Width=3840, Height=2160, RefreshHz=144))
    assert result.status == "unknown"
    assert criterion(result, "connection").Status == "compatible"
    assert criterion(result, "signal_mode").Status == "unknown"


@pytest.mark.parametrize("specs", [None, {}, {"Cổng kết nối": "USB-C 3.2 Gen 2"},
                                    {"Cổng kết nối": "HDMI 2.1, USB Type-C, Thunderbolt 4"},
                                    {"Loại card đồ họa": "RTX 5090, HDMI 2.1 output"}])
def test_unknown_and_generic_connector_or_gpu_marketing_does_not_prove_video(specs):
    source = normalize_video_specs(specs)
    target = normalize_video_specs({"HDMI input": "2.1"})
    assert check_compatibility(source, target, VideoRequest()).status == "unknown"


def test_missing_data_never_becomes_incompatible():
    source, target = profiles([], [], complete=False)
    assert check_compatibility(source, target, VideoRequest()).status == "unknown"


def test_complete_explicit_absence_of_video_outputs_is_incompatible():
    source, target = profiles([], [port()])
    assert check_compatibility(source, target, VideoRequest()).status == "incompatible"


def test_data_only_usb_c_in_complete_inventory_is_incompatible_with_native_video():
    source, target = profiles([port("USB-C", Video=False, DPAltMode=False)], [port()])
    assert check_compatibility(source, target, VideoRequest()).status == "incompatible"


def test_usb_c_video_without_confirmed_alt_mode_does_not_prove_a_dp_adapter_path():
    source, target = profiles([port("USB-C", Video=True)], [port("DisplayPort")])
    assert check_compatibility(source, target, VideoRequest()).status == "unknown"


@pytest.mark.parametrize("target_connector", ["DisplayPort", "HDMI"])
def test_confirmed_dp_alt_mode_has_a_directional_adapter_type(target_connector):
    source, target = profiles([port("USB-C", DPAltMode=True)], [port(target_connector)])
    result = check_compatibility(source, target, VideoRequest())
    assert result.status == "requires_adapter"
    assert "USB-C" in result.conditions[0] and "đúng chiều" in result.conditions[0]
    assert target_connector in result.conditions[0]


def test_dp_to_hdmi_adapter_is_not_silently_reversed():
    forward = profiles([port("DisplayPort")], [port("HDMI")])
    reverse = profiles([port("HDMI")], [port("DisplayPort")])
    assert check_compatibility(*forward, VideoRequest()).status == "requires_adapter"
    assert check_compatibility(*reverse, VideoRequest()).status == "unknown"


def test_direct_only_mismatch_is_negative_only_for_complete_unambiguous_inventories():
    source, target = profiles([port("DisplayPort")], [port("HDMI")])
    assert check_compatibility(source, target, VideoRequest(DirectOnly=True)).status == "incompatible"
    source.outputs_complete = False
    assert check_compatibility(source, target, VideoRequest(DirectOnly=True)).status == "unknown"


def test_usb_c_direction_and_alt_mode_are_checked_at_both_ends():
    source, target = profiles([port("USB-C", DPAltMode=True)], [port("USB-C", Video=True)])
    assert check_compatibility(source, target, VideoRequest()).status == "unknown"
    source, target = profiles([port("USB-C", DPAltMode=True)], [port("USB-C", DPAltMode=True)])
    assert check_compatibility(source, target, VideoRequest()).status == "compatible"


def test_monitor_144hz_is_not_laptop_output_or_input_timing():
    source = normalize_video_specs({"HDMI output": "2.1"})
    target = normalize_video_specs({"HDMI input": "2.1", "Tần số quét": "144Hz", "Độ phân giải màn hình": "4K"})
    result = check_compatibility(source, target, VideoRequest(Width=3840, Height=2160, RefreshHz=144))
    assert criterion(result, "refresh_rate").Status == result.status == "unknown"


def test_4k60_and_1080p144_cannot_be_combined_into_4k144():
    source, target = profiles([port(Modes=[mode(hz=60), mode(1920, 1080, 144)])],
                               [port(Modes=[mode(hz=60), mode(1920, 1080, 144)])])
    result = check_compatibility(source, target, VideoRequest(Width=3840, Height=2160, RefreshHz=144))
    assert criterion(result, "resolution").Status == "compatible"
    assert criterion(result, "refresh_rate").Status == criterion(result, "signal_mode").Status == "unknown"


def test_matching_timings_without_colour_dsc_and_cable_remain_unknown():
    source, target = profiles([port(Modes=[mode()])], [port(Modes=[mode()])])
    result = check_compatibility(source, target, VideoRequest(Width=3840, Height=2160, RefreshHz=144))
    assert criterion(result, "refresh_rate").Status == "compatible" and result.status == "unknown"
    assert any("DSC" in field for field in result.missing)
    assert any("Cáp" in field for field in result.missing)


def test_full_matching_signal_and_verified_cable_confirm_mode_under_explicit_conditions():
    signal = mode(ColorFormat="RGB", BitDepth=8, DSC=False)
    source, target = profiles([port(Modes=[signal])], [port(Modes=[signal])], VideoCables=[{
        "From": "HDMI", "To": "HDMI", "Verified": True, "Evidence": "Cáp thử nghiệm: 3840×2160 @ 144Hz, RGB 8 bit, DSC tắt",
        "Modes": [signal]}])
    result = check_compatibility(source, target, VideoRequest(Width=3840, Height=2160, RefreshHz=144))
    assert result.status == criterion(result, "signal_mode").Status == "compatible"
    assert any("8 bit" in line for line in result.conditions)
    assert result.missing == []


@pytest.mark.parametrize("change", [{"DSC": True}, {"BitDepth": 10}, {"ColorFormat": "4:2:0"}])
def test_different_colour_depth_or_dsc_cannot_be_merged(change):
    signal = mode(ColorFormat="RGB", BitDepth=8, DSC=False)
    source, target = profiles([port(Modes=[signal])], [port(Modes=[{**signal, **change}])])
    assert check_compatibility(source, target, VideoRequest(Width=3840, Height=2160, RefreshHz=144)).status == "unknown"


def test_explicit_limits_can_disprove_a_mode_but_not_without_complete_inventory():
    source, target = profiles([port(MaxResolution="3840x2160", MaxRefreshHz=60)], [port()])
    request = VideoRequest(Width=3840, Height=2160, RefreshHz=144)
    result = check_compatibility(source, target, request)
    assert result.status == "incompatible" and criterion(result, "connection").Status == "compatible"
    source.outputs_complete = False
    assert check_compatibility(source, target, request).status == "unknown"


@pytest.mark.parametrize("key,value", [("Cổng xuất hình", "HDMI 2.0"), ("HDMI output", "2.0"),
                                       ("Ports", "HDMI 2.0 output"), ("Cổng giao tiếp", "HDMI 2.0 video output")])
def test_directional_text_aliases_preserve_meaning(key, value):
    source = normalize_video_specs({"Thông số": {key: value}})
    target = normalize_video_specs({"Cổng nhận hình": "HDMI 2.0"})
    assert check_compatibility(source, target, VideoRequest()).status == "compatible"


def test_text_usb_c_alt_mode_does_not_create_a_physical_displayport_or_bleed_to_other_ports():
    source = normalize_video_specs({"Cổng kết nối": "USB-C output (DP Alt Mode); HDMI data only"})
    assert [p.connector for p in source.ports] == ["usb_c", "hdmi"]
    assert source.ports[0].alt_mode is True and source.ports[1].video is False


def test_input_and_output_are_not_inferred_from_product_role_or_port_name():
    source = normalize_video_specs({"HDMI input": "2.1"})
    target = normalize_video_specs({"HDMI output": "2.1"})
    assert check_compatibility(source, target, VideoRequest()).status == "unknown"


def test_variant_override_never_reads_another_sku_or_private_metadata():
    source = normalize_video_specs({"_private": {"HDMI output": "2.1"}, "VideoByVariant": {
        "sku-a": {"VideoOutputs": [port()]}, "sku-b": {"VideoOutputs": [port("USB-C", Video=False)]}}}, variant_id="sku-b")
    assert len(source.ports) == 1 and source.ports[0].connector == "usb_c" and source.ports[0].video is False


def test_malformed_or_truncated_inventory_cannot_be_used_as_proof_of_absence():
    source, target = profiles([{"Connector": "Unknown"}], [port()])
    assert source.outputs_complete is False
    assert check_compatibility(source, target, VideoRequest()).status == "unknown"


def test_only_explicit_laptop_output_capability_can_answer_a_single_port_question():
    source = normalize_video_specs({"Cổng kết nối": "USB-C 3.2 Gen 2"})
    request = VideoRequest(SourceConnector="usb_c")
    assert check_compatibility(source, None, request).status == "unknown"
    source = normalize_video_specs({"VideoOutputs": [port("USB-C", DPAltMode=True)]})
    result = check_compatibility(source, None, request)
    assert result.status == "compatible" and any("màn hình" in m for m in result.missing)


@pytest.mark.parametrize("text", ["Không có HDMI output", "Không hỗ trợ HDMI output", "No HDMI output",
                                  "USB-C output không hỗ trợ xuất hình", "USB-C (no video) output"])
def test_negation_before_or_after_connector_does_not_become_positive(text):
    source = normalize_video_specs({"Cổng kết nối": text})
    target = normalize_video_specs({"HDMI input": "2.1"})
    assert check_compatibility(source, target, VideoRequest()).status == "unknown"
    assert not any(p.usable("output") for p in source.ports)


def test_conflicting_mode_and_maximum_do_not_confirm_the_mode():
    signal = mode(ColorFormat="RGB", BitDepth=8, DSC=False)
    source, target = profiles([port(Modes=[signal], MaxRefreshHz=60)], [port(Modes=[signal])], VideoCables=[{
        "From": "HDMI", "To": "HDMI", "Verified": True, "Evidence": "Test-only verified cable", "Modes": [signal]}])
    assert source.warnings
    assert check_compatibility(source, target, VideoRequest(Width=3840, Height=2160, RefreshHz=144)).status == "unknown"


def test_complete_flag_alone_without_an_actual_inventory_is_not_proof_of_absence():
    source = normalize_video_specs({"VideoOutputsComplete": True})
    target = normalize_video_specs({"VideoInputs": [port()]})
    assert check_compatibility(source, target, VideoRequest()).status == "unknown"


def test_dp_protocol_in_a_usb_c_field_does_not_invent_a_physical_dp_port():
    source = normalize_video_specs({"USB Type-C": "Hỗ trợ DisplayPort 1.4 xuất hình"})
    assert [p.connector for p in source.ports] == ["usb_c"]
    target = normalize_video_specs({"HDMI input": "2.1"})
    # A USB-C entry naming DisplayPort carries DP Alt Mode (project decision, 29/10/2026): an adapter, not a DP cable.
    result = check_compatibility(source, target, VideoRequest())
    assert result.status == "requires_adapter" and "DP Alt Mode" in result.conditions[0]


@pytest.mark.parametrize("value", [0, "0", "Không", "No", "0 x HDMI output"])
def test_zero_or_absent_port_is_not_a_positive_output(value):
    source = normalize_video_specs({"HDMI output": value})
    assert not any(p.usable("output") for p in source.ports)


# --- Review regressions: a DP signal of a USB-C port is not a DisplayPort socket; negations and unknown ports.

DP_MONITOR = {"VideoInputs": [port("DisplayPort")], "VideoInputsComplete": True}


@pytest.mark.parametrize("value", ["USB-C, DP Alt Mode: Có", "USB-C, hỗ trợ DP Alt Mode", "Type-C (DP Alt Mode)",
                                   "Thunderbolt 4 (DP Alt Mode)", "1x USB-C 10Gbps, DP over USB-C"])
def test_alt_mode_wording_needs_a_usb_c_cable_not_a_native_displayport_cable(value):
    source = normalize_video_specs({"Cổng xuất hình": value})
    assert "displayport" not in [p.connector for p in source.ports]
    result = check_compatibility(source, normalize_video_specs(DP_MONITOR), VideoRequest())
    assert result.status == "requires_adapter"
    assert "DP Alt Mode" in result.conditions[0] and "Cáp DisplayPort" not in result.conditions[0]


@pytest.mark.parametrize("value", [
    "1x USB-C 5Gbps (USB 3.2 Gen 1, USB PD 45–65W, DisplayPort 1.2); 1x HDMI 1.4",  # Catalog wording.
    "Type-C (USB3.2 Gen1 / DisplayPort); 1x HDMI 2.1 (4K @ 60Hz)",
    "1 x USB-C 3.2 Gen 1 (hỗ trợ Power Delivery 3.0, DisplayPort 1.4); 1 x HDMI 2.1",
    "1x USB-C (10Gbps), với USB PD 65-100W và DisplayPort 2.1; 1x HDMI 2.1, lên đến 8K/60Hz",
])
def test_displayport_signal_of_a_usb_c_port_is_not_a_second_physical_port(value):
    source = normalize_video_specs({"Cổng xuất hình": value})
    assert sorted(p.connector for p in source.ports) == ["hdmi", "usb_c"]
    # The USB-C entry names DisplayPort itself, so it is a DP source over DP Alt Mode (project decision, 29/10/2026):
    # the path needs a USB-C → DisplayPort cable, never a native DisplayPort cable.
    result = check_compatibility(source, normalize_video_specs(DP_MONITOR), VideoRequest())
    assert result.status == "requires_adapter" and "DP Alt Mode" in result.conditions[0]


def test_a_real_mini_displayport_socket_is_still_read():
    source = normalize_video_specs({"Cổng xuất hình": "1x USB-C 3.2 Gen 2 (Hỗ trợ DisplayPort 2.1 qua dGPU và sạc USB); "
                                                      "1x Mini DisplayPort 1.4"})
    assert sorted(p.connector for p in source.ports) == ["displayport", "usb_c"]
    assert check_compatibility(source, normalize_video_specs(DP_MONITOR), VideoRequest()).status == "compatible"


@pytest.mark.parametrize("value", ["USB-C output (no DP Alt Mode)", "USB-C output không hỗ trợ DP Alt Mode",
                                   "USB-C output, DP Alt Mode: Không", "USB-C output (DisplayPort: không)"])
def test_negated_alt_mode_never_becomes_a_video_path(value):
    source = normalize_video_specs({"Cổng kết nối": value})
    assert not any(p.alt_mode for p in source.ports)
    target = normalize_video_specs({"VideoInputs": [port("USB-C", DPAltMode=True), port("HDMI")],
                                    "VideoInputsComplete": True})
    assert check_compatibility(source, target, VideoRequest()).status == "unknown"


def test_usb_c_video_of_unknown_protocol_blocks_a_negative_mode_conclusion():
    request = VideoRequest(Width=3840, Height=2160, RefreshHz=144)
    target = normalize_video_specs({"VideoInputs": [port(), port("USB-C", DPAltMode=True)], "VideoInputsComplete": True})
    unclear = normalize_video_specs({"VideoOutputs": [port(MaxRefreshHz=60), port("USB-C", Video=True)],
                                     "VideoOutputsComplete": True})
    result = check_compatibility(unclear, target, request)
    assert result.status == "unknown" and criterion(result, "refresh_rate").Status == "unknown"
    data_only = normalize_video_specs({"VideoOutputs": [port(MaxRefreshHz=60), port("USB-C", Video=False)],
                                       "VideoOutputsComplete": True})
    assert check_compatibility(data_only, target, request).status == "incompatible"


def test_thunderbolt_is_read_but_needs_an_explicit_alt_mode():
    usb_monitor = normalize_video_specs({"VideoInputs": [port("USB-C", DPAltMode=True)], "VideoInputsComplete": True})
    plain = normalize_video_specs({"VideoOutputs": [port("Thunderbolt 4")], "VideoOutputsComplete": True})
    assert plain.outputs_complete and not plain.warnings  # A readable entry, not a parse failure.
    assert check_compatibility(plain, usb_monitor, VideoRequest()).status == "unknown"
    explicit = normalize_video_specs({"VideoOutputs": [port("Thunderbolt 4", DPAltMode=True)], "VideoOutputsComplete": True})
    assert check_compatibility(explicit, usb_monitor, VideoRequest()).status == "compatible"
    hdmi_monitor = normalize_video_specs({"VideoInputs": [port()], "VideoInputsComplete": True})
    assert check_compatibility(explicit, hdmi_monitor, VideoRequest()).status == "requires_adapter"


def test_a_thunderbolt_only_inventory_does_not_disprove_usb_c_video():
    source = normalize_video_specs({"VideoOutputs": [port("Thunderbolt 4", DPAltMode=True)], "VideoOutputsComplete": True})
    assert check_compatibility(source, None, VideoRequest(SourceConnector="usb_c")).status == "unknown"


def test_structured_direction_is_case_insensitive():
    source = normalize_video_specs({"VideoPorts": [port(Direction="Output")]})
    assert not source.warnings and source.ports[0].usable("output")


def test_power_input_wording_does_not_turn_a_laptop_usb_c_into_a_video_input():
    source = normalize_video_specs({"Cổng xuất hình": "2x USB-C (1x USB 3.2 hỗ trợ DisplayPort 1.4, sạc USB và DC-in 65W; "
                                                      "1x USB 2.0 hỗ trợ sạc và DC-in 65W); 1x HDMI 1.4 (hỗ trợ HDCP)"})
    assert {(p.connector, p.direction) for p in source.ports} == {("usb_c", "output"), ("hdmi", "output")}


def test_vietnamese_alt_mode_wording_on_a_monitor_usb_c_input():
    target = normalize_video_specs({"Cổng nhận hình": "1x HDMI 2.0b (FHD@60Hz); 2x Type-C (tín hiệu DP 1.2a với chế độ Alt "
                                                      "& Nguồn điện 15W/Đầu vào nguồn)"})
    usb = next(p for p in target.ports if p.connector == "usb_c")
    assert usb.direction == "input" and usb.alt_mode is True and "displayport" not in [p.connector for p in target.ports]
    source = normalize_video_specs({"VideoOutputs": [port("USB-C", DPAltMode=True)], "VideoOutputsComplete": True})
    assert check_compatibility(source, target, VideoRequest(DirectOnly=True)).status == "compatible"
