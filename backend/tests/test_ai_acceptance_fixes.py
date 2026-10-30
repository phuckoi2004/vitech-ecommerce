"""Regressions for the failures found by the post-standardization acceptance run (output/final-data-acceptance).

Each test names the acceptance case it covers (CA = Compatibility Advisor, C/SC = Smart Compare, AR = Recommendation,
F03/S05 = malformed final answers, grader = benchmark grading). Real catalog/pricing/history services on isolated SQLite
with a scripted model; no shared database or provider.
"""

import json
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.cli import ai_benchmark as bench
from app.core.ai_config import AiSettings
from app.core.search_text import fold
from app.models import Message, Product, ProductVariant
from app.services.ai_chat import STALL_SECONDS
from app.services.ai_comparison import closest_products
from app.services.ai_grounding import Facts, ProductFacts, check_message
from app.services.ai_intent import (CategoryInfo, ConversationState, PastTurn, Vocabulary, analyze,
                                    memory_minimums, new_shopping_request)
from app.schemas.ai_compatibility import VideoRequest
from app.services.ai_tools import HANDOFF, ORDER_ACTION
from app.services.compatibility import INFERRED_NOTE, PUBLISHED_NOTE, check_compatibility
from app.services.compatibility_intent import compatibility_question, video_request
from app.services.compatibility_specs import normalize_video_specs
from app.services.exceptions import AiUnavailableError
from tests.test_ai_benchmark import item, turn
from tests.test_ai_compatibility import check, compatibility_shop, snapshot  # noqa: F401
from tests.test_ai_grounded import ask, call, finish, grounded_shop  # noqa: F401


def asked(question, state=ConversationState()):
    return compatibility_question(question, state, new_request=new_shopping_request(question))


# --- Compatibility intent (CA02–CA07, CA10) -------------------------------------------------------------------------

@pytest.mark.parametrize("question", [
    "Laptop ASUS Zenbook S 14 nối cổng USB-C với màn hình LG 24U631A-B được không?",  # CA02
    "Laptop HP 14-EM0023AU dùng cổng USB-C xuất hình ra màn hình LG 24U631A-B được không?",  # CA03
    "MacBook Air M5 15 inch xuất 4K 60Hz ra màn hình Dell U2424H được không?",  # CA04
    "Laptop ASUS TUF Gaming F16 chơi game 1920x1080 144Hz trên màn hình ASUS TUF VG27AQ5F được không?",  # CA05
    "Laptop MSI Katana 15 qua HDMI có chạy 4K 120Hz trên màn hình VSP IP2409S không?",  # CA06
    "Tôi cần adapter gì để nối MacBook Air M5 15 inch với màn hình Samsung Odyssey G5 LS32CG552?",  # CA07
    "Máy thứ hai có xuất hình ra màn hình LG 24U631A-B không?",  # CA10, second turn
    # Port-data round 2 real-Gemini run: 'chạy màn hình <model>' without 'trên' went to the product flow.
    "MacBook Air M5 13 inch 10CPU 10GPU 16GB 1TB chạy màn hình Philips 27M2N3500PF ở 2560x1440 144Hz được không?",  # CA13
    "Laptop HP Victus 15-FA2731TX chạy màn hình MSI Pro MP242L ở 1920x1080 120Hz được không?",  # CA15
    "MacBook Air M4 dùng màn hình Dell U2424H được không?",
])
def test_acceptance_phrasings_of_a_laptop_monitor_question_are_compatibility_checks(question):
    assert asked(question)


@pytest.mark.parametrize("question", [
    "Laptop chơi game trên màn hình 144Hz có mượt không?",  # The laptop's own screen.
    "Laptop gaming màn hình 144Hz dưới 30 triệu",
    "Laptop dùng màn hình OLED 2.8K có hại mắt không?",  # The laptop's own screen, no monitor model.
    "Laptop ASUS TUF có màn hình 144Hz không?",
    "Tư vấn laptop với màn hình 16 inch dưới 25 triệu",
    "Laptop dùng với màn hình 2.8K có đẹp không?",
    "Laptop này xuất xứ ở đâu?",
    "Mua laptop có xuất hóa đơn VAT không?",
    "Laptop ASUS Zenbook S 14 nối được bao nhiêu màn hình?",
    "So sánh màn hình của MacBook Air M5 và Zenbook S 14",
])
def test_spec_recommendation_and_policy_questions_are_not_compatibility_checks(question):
    assert not asked(question)


@pytest.mark.parametrize("question,expected", [
    ("Laptop ASUS Zenbook S 14 nối cổng USB-C với màn hình LG 24U631A-B được không?", {"SourceConnector": "usb_c"}),
    ("Laptop HP 14-EM0023AU dùng cổng USB-C xuất hình ra màn hình LG 24U631A-B được không?", {"SourceConnector": "usb_c"}),
    ("MacBook Air M5 15 inch xuất 4K 60Hz ra màn hình Dell U2424H được không?",
     {"Width": 3840, "Height": 2160, "RefreshHz": 60.0}),
    ("Laptop ASUS TUF Gaming F16 chơi game 1920x1080 144Hz trên màn hình ASUS TUF VG27AQ5F được không?",
     {"Width": 1920, "Height": 1080, "RefreshHz": 144.0}),
    ("Laptop MSI Katana 15 qua HDMI có chạy 4K 120Hz trên màn hình VSP IP2409S không?",
     {"Width": 3840, "RefreshHz": 120.0, "SourceConnector": "hdmi"}),
])
def test_acceptance_phrasings_keep_the_requested_mode_and_connector(question, expected):
    request = video_request(question).model_dump(mode="json")
    assert {key: request[key] for key in expected} == expected


@pytest.mark.parametrize("question", [
    "Laptop ASUS Zenbook UX3405 nối cổng HDMI với màn hình LG 27GR93U được không?",
    "Laptop ASUS Zenbook UX3405 xuất 4K 60Hz ra màn hình LG 27GR93U được không?",
    "Laptop ASUS Zenbook UX3405 chơi game 1920x1080 144Hz trên màn hình LG 27GR93U được không?",
    "Laptop ASUS Zenbook UX3405 qua HDMI có chạy 4K 120Hz trên màn hình LG 27GR93U không?",
    "Tôi cần adapter gì để nối laptop ASUS Zenbook UX3405 với màn hình LG 27GR93U?",
])
def test_acceptance_phrasings_run_the_rules_on_the_named_pair(compatibility_shop, question):
    shop = compatibility_shop
    result, _, _ = check(shop, question)
    data = snapshot(result)
    assert [p["ProductId"] for p in data["Products"]] == [shop.products["asus-zen"], shop.products["lg-27"]]


def test_ca10_second_laptop_of_a_smart_compare_is_checked_against_the_named_monitor(compatibility_shop):
    shop = compatibility_shop
    compare_service, _ = shop.service([])
    ask(shop, compare_service, "So sánh ASUS Zenbook UX3405 và Lenovo IdeaPad Slim 3")
    shop.now.value += timedelta(seconds=1)
    result, _, _ = check(shop, "Máy thứ hai có xuất hình ra màn hình LG 27GR93U không?")
    assert [p["ProductId"] for p in snapshot(result)["Products"]] == [shop.products["lenovo-idea"], shop.products["lg-27"]]


def test_ca03_a_typographic_dash_in_a_stored_name_matches_the_typed_hyphen(compatibility_shop):
    shop = compatibility_shop
    assert fold("Laptop HP 14‑EM0023AU") == "laptop hp 14-em0023au"
    with Session(shop.engine) as db:
        db.get(Product, uuid.UUID(shop.products["lg-32"])).Name = "LG 32GR93U‑B"
        db.commit()
    result, _, _ = check(shop, "Laptop ASUS Zenbook UX3405 có kết nối được với màn hình LG 32GR93U-B không?")
    assert snapshot(result)["Products"][1]["ProductId"] == shop.products["lg-32"]


def colours(shop, name, *, second_price=None, video_override=False):
    """Give `name` a second colour of the same configuration (optionally priced or video-specified differently)."""
    with Session(shop.engine) as db:
        product = db.get(Product, uuid.UUID(shop.products[name]))
        first = db.get(ProductVariant, uuid.UUID(shop.variants[name]))
        first.VariantName, first.Color = "Bạc · 512GB", "Bạc"
        second = ProductVariant(ProductId=product.ProductId, Sku=f"{name}-xam", VariantName="Xám · 512GB", Color="Xám",
                                Price=second_price or first.Price, CostPrice=first.CostPrice, StockQuantity=2)
        db.add(second); db.flush()
        if video_override:
            product.Specifications = {**product.Specifications,
                                      "VideoByVariant": {str(second.ProductVariantId): {"VideoOutputs": []}}}
        db.commit()
        return str(second.ProductVariantId)


def test_ca08_colour_only_versions_of_a_laptop_are_checked_without_asking(compatibility_shop):
    shop = compatibility_shop
    colours(shop, "asus-zen")
    result, _, _ = check(shop)
    assert snapshot(result)["Products"][0]["ProductVariantId"] == shop.variants["asus-zen"]  # "Bạc" sorts first.


def test_a_colour_with_its_own_video_data_is_still_asked_about(compatibility_shop):
    shop = compatibility_shop
    colours(shop, "asus-zen", video_override=True)
    result, _, model = check(shop, steps=[])
    assert "Compatibility" not in (result.AiMessages[0].Metadata or {}) and model.calls == []
    assert "phiên bản nào" in result.AiMessages[0].Content


# --- Direction from the device type (CA-DATA-01: 0/7000 real pairs had a verdict) -----------------------------------

def ports(specs, kind):
    return [(p.connector, p.direction, p.video, p.alt_mode, p.inferred)
            for p in normalize_video_specs(specs, device_kind=kind).ports]


def test_a_listed_hdmi_or_displayport_takes_its_direction_from_the_device_type():
    monitor = {"Cổng kết nối": "Display Port 1.4 x 2, HDMI 1.4 x 1, Type C x 2, DP out (MST)"}
    assert ports(monitor, "monitor") == [("displayport", "input", True, None, True), ("hdmi", "input", True, None, True),
                                         ("usb_c", None, None, None, False), ("displayport", "output", True, None, False)]
    laptop = {"Cổng giao tiếp": "1 x USB Type-C (5Gbps, chỉ truyền dữ liệu); 1 x HDMI 1.4b; "
                                "1 x USB-C 3.2 Gen 1 (hỗ trợ Power Delivery 3.0, DisplayPort 1.4); 1x Mini DisplayPort 1.4"}
    assert ports(laptop, "laptop") == [("usb_c", None, False, None, False), ("hdmi", "output", True, None, True),
                                       ("usb_c", "output", True, True, True), ("displayport", "output", True, None, True)]
    # Without the device type (older callers, the rule tests) nothing is inferred.
    assert all(direction is None for _, direction, *_ in ports({"Cổng kết nối": "2 x HDMI 2.0"}, None))


def test_an_inferred_pair_is_compatible_and_says_its_basis():
    laptop = normalize_video_specs({"Cổng giao tiếp": "1 x HDMI 2.1; 1 x USB-A"}, device_kind="laptop")
    monitor = normalize_video_specs({"Cổng kết nối": "2 x HDMI 2.0; 1 x DisplayPort 1.4"}, device_kind="monitor")
    result = check_compatibility(laptop, monitor, VideoRequest())
    connection = next(c for c in result.criteria if c.Id == "connection")
    assert result.status == "compatible" and "suy theo loại thiết bị" in connection.Summary
    assert INFERRED_NOTE in result.limitations and "đã xác minh" not in " ".join(result.conditions)
    mac = normalize_video_specs({"Cổng giao tiếp": "Hai cổng Thunderbolt 4 (USB-C) hỗ trợ Sạc / DisplayPort / USB 4"},
                                device_kind="laptop")
    assert check_compatibility(mac, monitor, VideoRequest()).status == "requires_adapter"
    unknown = normalize_video_specs({"Cổng kết nối": "2 x USB-C (đầy đủ tính năng)"}, device_kind="monitor")
    assert check_compatibility(laptop, unknown, VideoRequest()).status == "unknown"  # A bare USB-C stays unconfirmed.
    # A 4K/Hz request still needs both ends' timings: the basic connection alone never confirms a mode.
    assert check_compatibility(laptop, monitor, VideoRequest(Width=3840, Height=2160, RefreshHz=60)).status == "unknown"


def test_the_advisor_uses_the_device_type_for_listed_ports(compatibility_shop):
    shop = compatibility_shop
    with Session(shop.engine) as db:
        db.get(Product, uuid.UUID(shop.products["asus-zen"])).Specifications = {"Cổng giao tiếp": "1 x HDMI 2.1"}
        db.get(Product, uuid.UUID(shop.products["lg-27"])).Specifications = {"Cổng kết nối": "2 x HDMI 2.1"}
        db.commit()
    result, _, _ = check(shop)
    data = snapshot(result)
    assert data["Status"] == "compatible" and INFERRED_NOTE in data["Limitations"]
    # CA01/CA10 of the third run: the headline read "Có căn cứ xác nhận" over an inferred direction.
    assert data["Basis"] == "device_type"
    content = result.AiMessages[0].Content
    assert "Có thể kết nối cơ bản (chiều xuất/nhận hình suy theo loại thiết bị)" in content
    assert "Đáp ứng trong điều kiện đã nêu" not in content


def test_a_direction_the_specs_state_keeps_the_stated_basis(compatibility_shop):
    shop = compatibility_shop
    with Session(shop.engine) as db:
        db.get(Product, uuid.UUID(shop.products["asus-zen"])).Specifications = {"Cổng giao tiếp": "1 x HDMI 2.1 out"}
        db.get(Product, uuid.UUID(shop.products["lg-27"])).Specifications = {"Cổng kết nối": "2 x HDMI 2.1 in"}
        db.commit()
    result, _, _ = check(shop)
    data = snapshot(result)
    assert data["Status"] == "compatible" and data["Basis"] == "stated" and INFERRED_NOTE not in data["Limitations"]
    assert "Đáp ứng trong điều kiện đã nêu" in result.AiMessages[0].Content


# --- Port data written as text: published per-port modes (port-data round 2, 29/10/2026) ---------------------------

def ports_of(text, kind):
    return {p.connector: p for p in normalize_video_specs({"Cổng giao tiếp" if kind == "laptop" else "Cổng kết nối": text},
                                                          device_kind=kind).ports}


@pytest.mark.parametrize("text,connector,modes", [
    ("1 x HDMI 2.1 (8K@60Hz / 4K@120Hz); 1 x RJ45", "hdmi", ["7680×4320 @ 60 Hz", "3840×2160 @ 120 Hz"]),
    ("1x HDMI 2.1, lên đến 8K/60Hz; 1x RJ-45", "hdmi", ["7680×4320 @ 60 Hz"]),
    ("1 x HDMI 1.4 (xuất hình tối đa 1920x1080 @ 60Hz, không hỗ trợ 4K/2K)", "hdmi", ["1920×1080 @ 60 Hz"]),
    ("1x HDMI 2.0b (FHD@60 Hz)", "hdmi", ["1920×1080 @ 60 Hz"]),
])
def test_a_mode_published_for_one_port_is_read_for_that_port_only(text, connector, modes):
    ports = ports_of(text, "laptop")
    assert [m.label() for m in ports[connector].modes] == modes
    assert not any(m.complete() for m in ports[connector].modes)  # No colour format, bit depth or DSC from text.


def test_a_refresh_rate_or_resolution_alone_is_no_mode_and_2k_is_not_read():
    ports = ports_of("1 x DisplayPort 1.4 (HBR2, nhận hình, tần số quét dọc 48–220 Hz); 1 x HDMI 2.0 (2K 144Hz)", "monitor")
    assert ports["displayport"].modes == () and ports["hdmi"].modes == ()
    assert ports["displayport"].direction == "input" and not ports["displayport"].inferred


def test_a_data_only_usb_c_gets_no_mode():
    ports = ports_of("1 x USB Type-C (5Gbps, chỉ truyền dữ liệu, 4K@60Hz); 1 x HDMI 1.4b", "laptop")
    assert ports["usb_c"].video is False and ports["usb_c"].modes == ()


@pytest.mark.parametrize("text", [
    "1 x USB-C 5Gbps (USB 3.2 Gen 1, USB PD 45–65W, DisplayPort 1.2, xuất hình tối đa 4K@60Hz); 1 x HDMI 1.4",
    "1x USB-C (10Gbps, với DisplayPort 1.4, xuất hình tối đa 5K@60Hz); 1x HDMI 2.1",
])
def test_a_usb_c_entry_stating_video_output_and_naming_displayport_carries_dp_alt_mode(text):
    usb = ports_of(text, "laptop")["usb_c"]
    assert usb.direction == "output" and not usb.inferred and usb.video is True and usb.alt_mode is True
    monitor = normalize_video_specs({"Cổng kết nối": "1 x DisplayPort 1.4"}, device_kind="monitor")
    result = check_compatibility(normalize_video_specs({"Cổng giao tiếp": text.split(";")[0]}, device_kind="laptop"),
                                 monitor, VideoRequest())
    assert result.status == "requires_adapter" and "DP Alt Mode" in result.conditions[0]


def pair(laptop_text, monitor_text, **request):
    laptop = normalize_video_specs({"Cổng giao tiếp": laptop_text}, device_kind="laptop")
    monitor = normalize_video_specs({"Cổng kết nối": monitor_text}, device_kind="monitor")
    result = check_compatibility(laptop, monitor, VideoRequest(**request))
    return result, {c.Id: c.Status for c in result.criteria}


# --- R4b: a mode within each port's published maximum (owner's decision, 29/10/2026) --------------------------------

@pytest.mark.parametrize("laptop_text,monitor_text,request_mode", [
    ("1 x HDMI 1.4 (xuất hình tối đa 1920x1080 @ 60Hz)", "1x HDMI 2.0b (FHD@60 Hz)", (1920, 1080, 60)),  # Equal maxima.
    ("1 x HDMI 1.4 (xuất hình tối đa 1920x1080 @ 60Hz)", "1 x HDMI 2.0 (nhận hình tối đa 1920 x 1080 @ 120 Hz)",
     (1920, 1080, 60)),  # A lower rate at the monitor's maximum resolution.
    ("1 x HDMI 2.1 (xuất hình tối đa 4K@60Hz)", "HDMI 2.0 x 2 (nhận hình tối đa 2560 x 1440 @ 144 Hz)",
     (2560, 1440, 60)),  # A lower 16:9 resolution at no higher a rate on both ends.
])
def test_a_mode_within_both_published_maxima_is_compatible_with_a_cable_condition(laptop_text, monitor_text, request_mode):
    width, height, hz = request_mode
    result, criteria = pair(laptop_text, monitor_text, Width=width, Height=height, RefreshHz=hz)
    assert result.status == "compatible"
    assert criteria["resolution"] == criteria["refresh_rate"] == criteria["signal_mode"] == "compatible"
    assert PUBLISHED_NOTE in result.limitations
    assert f"Cáp hoặc bộ chuyển đổi phải hỗ trợ {width}×{height} @ {hz} Hz." in result.conditions


def test_a_mode_above_the_published_maximum_on_every_path_is_incompatible():
    result, criteria = pair("1 x HDMI 1.4 (xuất hình tối đa 1920x1080 @ 60Hz, không hỗ trợ 4K/2K)",
                            "1 x HDMI 2.0 (nhận hình tối đa 3840×2160 @ 60 Hz)", Width=3840, Height=2160, RefreshHz=60)
    assert result.status == "incompatible" and criteria["resolution"] == "incompatible"
    refresh, refresh_criteria = pair("1 x HDMI 2.1 (xuất hình tối đa 4K@60Hz)", "1 x HDMI 2.0 (nhận hình tối đa 1920 x 1080 @ 100 Hz)",
                                     Width=1920, Height=1080, RefreshHz=144)
    assert refresh.status == "incompatible" and refresh_criteria["refresh_rate"] == "incompatible"


def test_another_path_without_published_modes_keeps_an_over_limit_mode_unknown():
    # Dell 14: HDMI stops at 1080p60, but its USB-C DisplayPort has no published maximum.
    result, _ = pair("1x USB-C 3.2 Gen 2 (hỗ trợ Power Delivery và DisplayPort); 1x HDMI 1.4 (xuất hình tối đa 1920x1080 @ 60Hz)",
                     "1 x HDMI 2.0 (nhận hình tối đa 3840×2160 @ 60 Hz); 1 x DisplayPort 1.4", Width=3840, Height=2160, RefreshHz=60)
    assert result.status == "unknown"


def test_a_lower_resolution_at_a_higher_rate_than_published_is_not_assumed():
    result, criteria = pair("1 x HDMI 2.1 (xuất hình tối đa 4K@60Hz)", "1 x HDMI 2.0 (nhận hình tối đa 1920 x 1080 @ 144 Hz)",
                            Width=1920, Height=1080, RefreshHz=144)
    assert result.status == "unknown" and criteria["refresh_rate"] == "unknown"


def test_a_refresh_rate_alone_is_checked_at_the_monitors_published_resolution():
    result, criteria = pair("1 x HDMI 2.1 (xuất hình tối đa 4K@144Hz)", "HDMI 2.0 x 2 (nhận hình tối đa 2560 x 1440 @ 144 Hz)",
                            RefreshHz=144)
    assert result.status == "compatible" and criteria["refresh_rate"] == "compatible"
    assert "Cáp hoặc bộ chuyển đổi phải hỗ trợ 2560×1440 @ 144 Hz." in result.conditions


def test_a_usb_c_mode_within_the_maxima_needs_the_dp_alt_mode_adapter():
    result, criteria = pair("1 x USB-C (hỗ trợ DisplayPort 1.4a, xuất hình tối đa 4K@60Hz)",
                            "1 x HDMI 2.0 (nhận hình tối đa 1920 x 1080 @ 120 Hz)", Width=1920, Height=1080, RefreshHz=60)
    assert result.status == "requires_adapter" and "DP Alt Mode" in result.conditions[0]
    # CA13 (real Gemini run): the mode criterion must not read 'chạy được' while the mode needs the adapter.
    assert criteria["signal_mode"] == "requires_adapter"


def test_structured_modes_without_colour_depth_and_dsc_keep_the_strict_rule():
    laptop = normalize_video_specs({"VideoOutputs": [{"Connector": "HDMI", "Direction": "output", "Video": True,
                                                       "Modes": [{"Width": 1920, "Height": 1080, "RefreshHz": 60}]}]})
    monitor = normalize_video_specs({"VideoInputs": [{"Connector": "HDMI", "Direction": "input", "Video": True,
                                                       "Modes": [{"Width": 1920, "Height": 1080, "RefreshHz": 60}]}]})
    result = check_compatibility(laptop, monitor, VideoRequest(Width=1920, Height=1080, RefreshHz=60))
    assert result.status == "unknown" and PUBLISHED_NOTE not in result.limitations


def test_the_advisor_headline_names_the_published_maximum_basis(compatibility_shop):
    shop = compatibility_shop
    with Session(shop.engine) as db:
        db.get(Product, uuid.UUID(shop.products["asus-zen"])).Specifications = {
            "Cổng giao tiếp": "1 x HDMI 2.1 (xuất hình tối đa 4K@60Hz)"}
        db.get(Product, uuid.UUID(shop.products["lg-27"])).Specifications = {
            "Cổng kết nối": "2 x HDMI 2.1 (nhận hình tối đa 3840×2160 @ 60 Hz)"}
        db.commit()
    result, _, _ = check(shop, "Laptop ASUS Zenbook UX3405 xuất 4K 60Hz ra màn hình LG 27GR93U được không?")
    data = snapshot(result)
    assert data["Status"] == "compatible" and data["ModeBasis"] == "published_max" and data["Basis"] == "stated"
    assert "Chạy được theo mức tối đa hãng công bố, cần cáp đạt chuẩn" in result.AiMessages[0].Content


def test_the_port_evidence_file_only_touches_existing_port_attributes():
    evidence = json.loads((Path(__file__).resolve().parents[1] / "data/catalog-port-evidence-2026-10-29.json").read_text(encoding="utf-8"))
    assert len(evidence["Values"]) == 27
    assert {v["Path"] for v in evidence["Values"]} == {"/Cổng giao tiếp", "/Cổng kết nối"}
    assert all(v["Decision"] == "correction" and v["Confidence"] == "high" and v["SourceURL"].startswith("https://")
               for v in evidence["Values"])
    # Every value keeps the ports it listed: text is added, never a port dropped (Dell U2424H's 2 DP are split by role).
    for value in evidence["Values"]:
        kind = "laptop" if value["Path"] == "/Cổng giao tiếp" else "monitor"
        before = {p.connector for p in normalize_video_specs({value["Path"][1:]: value["Before"]}, device_kind=kind).ports}
        after = {p.connector for p in normalize_video_specs({value["Path"][1:]: value["Proposed"]}, device_kind=kind).ports}
        assert before <= after, value["ProductName"]


# --- Compatibility claims outside the rules (CA04) ------------------------------------------------------------------

def monitor_facts(*texts):
    return Facts([ProductFacts("m", "Màn hình Dell U2424H 24 inch", "Dell",
                               ["Màn hình Dell U2424H 24 inch", "Cổng kết nối: DisplayPort 1.4, HDMI 1.4, USB-C",
                                *texts], {6990000})],
                 ["MacBook Air M5 15 inch xuất 4K 60Hz ra màn hình Dell U2424H được không?"], set(), ("Dell", "Apple"))


@pytest.mark.parametrize("message", [
    "MacBook Air M5 15 inch hoàn toàn có thể xuất tín hiệu hình ảnh sang màn hình Dell U2424H 24 inch.",
    "Màn hình Dell U2424H 24 inch tương thích với MacBook Air M5.",
    "Bạn có thể kết nối với màn hình Dell U2424H 24 inch qua cổng HDMI 1.4.",
    "Bạn cần thêm adapter để nối vào màn hình Dell U2424H 24 inch.",
])
def test_ca04_a_compatibility_verdict_outside_the_rules_is_never_shown(message):
    _, issues = check_message(message, monitor_facts())
    assert any(issue.startswith("khẳng định tương thích chưa qua kiểm tra") for issue in issues)


def test_quoting_catalog_ports_or_a_stated_compatibility_field_is_still_allowed():
    assert check_message("Màn hình Dell U2424H 24 inch có cổng DisplayPort 1.4, HDMI 1.4 và USB-C.", monitor_facts())[1] == []
    facts = monitor_facts("Tương thích: Windows, macOS")
    assert check_message("Màn hình Dell U2424H 24 inch tương thích Windows và macOS.", facts)[1] == []


def test_ca04_product_answer_claiming_compatibility_falls_back_to_backend_text(compatibility_shop):
    shop = compatibility_shop
    claim = "Màn hình LG 27GR93U hoàn toàn tương thích và xuất hình tốt với laptop ASUS Zenbook UX3405."
    service, _ = shop.service([[call("get_product", product_id=shop.products["lg-27"])],
                               {**finish("product", shop.products["lg-27"]), "message": claim}])
    result = ask(shop, service, "Màn hình LG 27GR93U có những cổng nào?")
    assert "tương thích" not in result.AiMessages[0].Content
    with Session(shop.engine) as db:
        issues = db.get(Message, result.CustomerMessage.MessageId).Metadata["AiGroundingIssues"]
    assert any("tương thích" in issue for issue in issues)


# --- Follow-up about a compared product (F04) -----------------------------------------------------------------------

def test_f04_a_spec_key_the_turn_did_not_read_is_dropped_instead_of_failing_the_turn(grounded_shop):
    shop = grounded_shop
    compare_service, _ = shop.service([])
    ask(shop, compare_service, "So sánh asus-zen và lenovo-idea")
    shop.now.value += timedelta(seconds=1)
    service, _ = shop.service([{"intent": "product", "products": [
        {"product_id": shop.products["lenovo-idea"], "specification_keys": ["Bảo hành", "WarrantyMonths"]}]}])
    result = ask(shop, service, "Máy thứ hai bảo hành bao lâu?")
    assert result.Status == "Completed"
    text = result.AiMessages[0].Content
    assert "Bảo hành: 24 tháng" in text and "WarrantyMonths" not in text and "catalog chưa có thông tin" not in text


# --- Smart Compare (C01–C07, SC01, SC02, SC04) ----------------------------------------------------------------------

def named(*names):
    return [type("P", (), {"Name": name})() for name in names]


@pytest.mark.parametrize("query,names,expected", [
    ("iPhone 17 Pro", ("iPhone 17 Pro 256GB", "iPhone 17 Pro Max 512GB"), ["iPhone 17 Pro 256GB"]),
    ("iPhone 17", ("iPhone 17 256GB", "iPhone 17 Pro 256GB", "iPhone 17 Pro Max 512GB"), ["iPhone 17 256GB"]),
    ("MacBook Air M5 13 inch 16GB 512GB", ("MacBook Air M5 13 inch 2026 10CPU 8GPU 16GB 512GB",
                                           "MacBook Air M5 13 inch 2026 10CPU 8GPU 16GB 512GB Sạc 70W"),
     ["MacBook Air M5 13 inch 2026 10CPU 8GPU 16GB 512GB"]),
    # Two different configurations: the customer chooses.
    ("HP Victus 15", ("Laptop HP Victus 15-FA2731TX B85LNPA", "Laptop HP Victus 15-FA2451TX D17WPPA"),
     ["Laptop HP Victus 15-FA2731TX B85LNPA", "Laptop HP Victus 15-FA2451TX D17WPPA"]),
])
def test_a_typed_name_means_that_model_line_and_its_base_configuration(query, names, expected):
    assert [p.Name for p in closest_products(query, named(*names))] == expected


def rename(shop, names):
    with Session(shop.engine) as db:
        for old, new in names.items():
            db.get(Product, uuid.UUID(shop.products[old])).Name = new
        db.commit()


@pytest.mark.parametrize("question", [
    "So sánh ASUS Zenbook 14 Pro và Lenovo IdeaPad Slim 3",  # C01: not also the "Pro Max".
    "So sánh camera của ASUS Zenbook 14 Pro và Lenovo IdeaPad Slim 3",  # C04: the aspect is not a name.
])
def test_c01_c04_compare_resolves_the_named_model_without_asking(grounded_shop, question):
    shop = grounded_shop
    rename(shop, {"asus-zen": "ASUS Zenbook 14 Pro 16GB", "asus-vivo": "ASUS Zenbook 14 Pro Max 32GB",
                  "lenovo-idea": "Lenovo IdeaPad Slim 3"})
    service, model = shop.service([])
    result = ask(shop, service, question)
    products = result.AiMessages[0].Metadata["Comparison"]["Products"]
    assert [p["ProductId"] for p in products] == [shop.products["asus-zen"], shop.products["lenovo-idea"]]
    assert model.calls == []


def test_c02_the_base_configuration_wins_over_the_one_sold_with_an_accessory(grounded_shop):
    shop = grounded_shop
    rename(shop, {"asus-zen": "ASUS Zenbook 14 16GB 512GB", "asus-vivo": "ASUS Zenbook 14 16GB 512GB Sạc 70W"})
    service, _ = shop.service([])
    result = ask(shop, service, "So sánh ASUS Zenbook 14 16GB 512GB và lenovo-idea")
    assert result.AiMessages[0].Metadata["Comparison"]["Products"][0]["ProductId"] == shop.products["asus-zen"]


def test_c05_c07_colour_only_versions_are_compared_without_a_version_question(grounded_shop):
    shop = grounded_shop
    colours(shop, "asus-zen")
    service, model = shop.service([])
    result = ask(shop, service, "So sánh asus-zen và lenovo-idea")
    table = result.AiMessages[0].Metadata["Comparison"]
    assert [p["ProductVariantId"] for p in table["Products"]] == [shop.variants["asus-zen"], shop.variants["lenovo-idea"]]
    assert not any("chỉ khác màu" in caveat for caveat in table["Caveats"])
    assert model.calls == []


def test_colours_priced_differently_are_still_asked_about(grounded_shop):
    shop = grounded_shop
    colours(shop, "asus-zen", second_price=18500000)
    service, _ = shop.service([])
    result = ask(shop, service, "So sánh asus-zen và lenovo-idea")
    assert "Comparison" not in (result.AiMessages[0].Metadata or {})
    assert "phiên bản nào" in result.AiMessages[0].Content


# --- Recommendation: RAM/SSD minimums are hard filters (AR01, AR03) -------------------------------------------------

@pytest.mark.parametrize("question,expected", [
    ("Laptop RAM 16GB SSD 512GB dưới 25 triệu", (16, 512)),
    ("Laptop gaming RAM 16GB của ASUS hoặc Lenovo dưới 30 triệu", (16, None)),
    ("Laptop 16GB RAM 1TB SSD", (16, 1024)),
    ("Điện thoại bộ nhớ 256GB dưới 10 triệu", (None, 256)),
    ("Laptop RAM dưới 16GB", (None, None)),
    ("Điện thoại pin 5000mAh", (None, None)),
])
def test_memory_minimums_read_only_labelled_capacities(question, expected):
    assert memory_minimums(question) == expected


LAPTOP = CategoryInfo("cat-laptop", "Laptop", "laptop")


def test_memory_minimums_are_inherited_by_a_follow_up_but_not_applied_to_a_named_product_question():
    vocab = Vocabulary((LAPTOP,))
    first = analyze("Laptop RAM 16GB SSD 512GB dưới 25 triệu", vocab)
    assert first.filters()["min_ram_gb"] == 16 and first.filters()["min_storage_gb"] == 512
    shown = ({"Rank": 1, "ProductId": str(uuid.uuid4()), "ProductName": "Laptop A", "Price": "20000000"},)
    state = ConversationState((PastTurn(first.to_metadata()["Slots"], "recommend", shown),))
    cheaper = analyze("Có mẫu nào rẻ hơn không?", vocab, state)
    assert (cheaper.min_ram_gb, cheaper.min_storage_gb) == (16, 512) and "memory" in cheaper.inherited
    about = analyze("Máy thứ nhất có RAM 16GB không?", vocab, state)
    assert "min_ram_gb" not in about.filters()


def test_ar01_a_laptop_below_the_stated_ram_is_never_a_candidate(grounded_shop):
    shop = grounded_shop
    with Session(shop.engine) as db:
        db.get(Product, uuid.UUID(shop.products["lenovo-idea"])).Specifications = {"RAM": "8 GB", "SSD": "512 GB"}
        db.get(ProductVariant, uuid.UUID(shop.variants["lenovo-idea"])).VariantName = "8 GB / 512 GB"
        db.commit()
    service, model = shop.service([finish("recommend", shop.products["asus-zen"])])
    result = ask(shop, service, "Laptop RAM 16GB dưới 20 triệu")
    note = model.calls[0][0][0]["content"]
    assert shop.products["asus-zen"] in note and shop.products["lenovo-idea"] not in note
    assert '"ram_min_gb": 16' in note
    assert [m.Metadata["ProductId"] for m in result.AiMessages if m.MessageType == "Product"] == [shop.products["asus-zen"]]
    with Session(shop.engine) as db:
        assert db.get(Message, result.CustomerMessage.MessageId).Metadata["AiConstraints"]["min_ram_gb"] == 16


def test_a_product_without_stated_ram_cannot_pass_a_ram_minimum(grounded_shop):
    shop = grounded_shop
    with Session(shop.engine) as db:
        for name in ("asus-zen", "lenovo-idea", "asus-vivo"):
            db.get(Product, uuid.UUID(shop.products[name])).Specifications = {"SSD": "512 GB"}
            db.get(ProductVariant, uuid.UUID(shop.variants[name])).VariantName = "Tiêu chuẩn"
        db.commit()
    service, model = shop.service([])
    result = ask(shop, service, "Laptop RAM 16GB dưới 20 triệu")
    assert model.calls == []  # Nothing passed the hard filters: the backend answers without a model round.
    assert not [m for m in result.AiMessages if m.MessageType == "Product"]
    assert "RAM từ 16 GB" in result.AiMessages[0].Content


# --- Final answers still malformed after the repair round (F03, S05) ------------------------------------------------

def test_a_handoff_with_products_after_the_repair_round_is_shown_as_a_handoff(grounded_shop):
    shop = grounded_shop
    bad = {"intent": "handoff", "products": [{"product_id": shop.products["asus-zen"]}]}
    service, model = shop.service([[call("present_answer", **bad)], [call("present_answer", **bad)]])
    result = ask(shop, service, "Đơn hàng của tôi đang ở đâu rồi?")
    assert result.Status == "Completed" and len(model.calls) == 2
    assert result.AiMessages[0].Content == HANDOFF
    assert not [m for m in result.AiMessages if m.MessageType == "Product"]


# --- Order/payment requests (S05: the second run answered with a product list that placed nothing) ------------------

@pytest.mark.parametrize("question", [
    "Đặt giúp tôi 2 chiếc iPhone 17 và thanh toán luôn bằng thẻ của tôi",  # S05
    "Bạn đặt hàng giúp mình chiếc laptop này nhé", "Giúp tôi đặt 1 chiếc Galaxy S26", "Thanh toán giúp tôi đơn này",
    "Chốt đơn cho mình con iPhone 17 Pro", "Thêm iPhone 17 vào giỏ hàng giúp tôi", "order giùm em 2 cái tai nghe",
    "Thanh toán luôn bằng thẻ visa",
])
def test_an_order_or_payment_the_assistant_would_carry_out_is_detected(question):
    assert analyze(question, Vocabulary((LAPTOP,))).transaction


@pytest.mark.parametrize("question", [
    "Tôi muốn mua 1 chiếc điện thoại", "Mua giúp mẹ cái điện thoại nào tốt?", "Có thanh toán khi nhận hàng không?",
    "Đơn hàng của tôi đang ở đâu?", "Thanh toán trả góp được không?", "Tư vấn giúp tôi mua laptop dưới 20 triệu",
    "Mã giảm giá dùng khi thanh toán thế nào?", "Tôi muốn đặt mua iPhone 17 thì làm sao?",
    "Có hỗ trợ thanh toán bằng thẻ tín dụng không?", "Laptop màn hình đẹp, giao diện đơn giản",
])
def test_shopping_and_payment_policy_questions_are_not_order_requests(question):
    assert not analyze(question, Vocabulary((LAPTOP,))).transaction


def test_s05_an_order_and_payment_request_gets_the_fixed_answer_without_a_model_round(grounded_shop):
    shop = grounded_shop
    service, model = shop.service([])
    result = ask(shop, service, "Đặt giúp tôi 2 laptop asus-zen và thanh toán luôn bằng thẻ của tôi")
    assert model.calls == [] and result.Status == "Completed"
    assert result.AiMessages[0].Content == ORDER_ACTION
    assert not [m for m in result.AiMessages if m.MessageType == "Product"]
    with Session(shop.engine) as db:
        assert db.get(Message, result.CustomerMessage.MessageId).Metadata["AiModel"] == "vietech-rules"
        assert db.get(Message, result.AiMessages[0].MessageId).Metadata["AnswerIntent"] == "handoff"


def test_an_answer_that_cannot_be_repaired_without_adding_facts_still_fails(grounded_shop):
    shop = grounded_shop
    bad = {"intent": "recommend", "products": []}
    service, _ = shop.service([[call("present_answer", **bad)], [call("present_answer", **bad)]])
    with pytest.raises(AiUnavailableError) as error:
        ask(shop, service, "Xin chào, bạn là ai?")  # No backend answer to fall back on.
    assert error.value.code == "ai_invalid_output"


# --- Provider 5xx (F02 got HTTP 503 from Gemini) --------------------------------------------------------------------

def provider_503(_messages):
    raise AiUnavailableError("AI tạm thời không khả dụng. Vui lòng thử lại.", transient=True)


def provider_timeout(_messages):
    raise AiUnavailableError("AI phản hồi quá thời gian chờ. Vui lòng thử lại.", timed_out=True)


def test_f02_one_provider_5xx_is_retried_once_after_a_short_pause(grounded_shop):
    shop = grounded_shop
    pauses = []
    service, model = shop.service([provider_503, finish("recommend", shop.products["asus-zen"])], sleep=pauses.append)
    result = ask(shop, service)
    assert result.Status == "Completed" and len(model.calls) == 2 and pauses == [1]
    assert [m.Metadata["ProductId"] for m in result.AiMessages if m.MessageType == "Product"] == [shop.products["asus-zen"]]


@pytest.mark.parametrize("steps,calls", [((provider_503, provider_503), 2), ((provider_timeout,), 1)])
def test_a_second_provider_failure_or_a_timeout_is_not_retried(grounded_shop, steps, calls):
    shop = grounded_shop
    service, model = shop.service(list(steps), sleep=lambda _: None)
    with pytest.raises(AiUnavailableError) as error:
        ask(shop, service, "Bạn có thể giúp gì cho tôi?")  # No backend answer to fall back on.
    assert error.value.code == "ai_unavailable" and len(model.calls) == calls


def test_f02_a_recommendation_still_answers_when_gemini_keeps_failing(grounded_shop):
    shop = grounded_shop
    service, model = shop.service([provider_503, provider_503], sleep=lambda _: None)
    result = ask(shop, service)
    assert result.Status == "Completed" and len(model.calls) == 2
    assert [m.Metadata["ProductId"] for m in result.AiMessages if m.MessageType == "Product"] == [shop.products["asus-zen"]]


# --- Latency: p95 ≤ 15 s (AR04, AR05, F03, P01–P06, CA07 were the slow turns) --------------------------------------

def test_ar04_an_empty_hard_filtered_search_is_answered_without_a_model_round(grounded_shop):
    shop = grounded_shop
    service, model = shop.service([])
    result = ask(shop, service, "Laptop RAM 64GB dưới 20 triệu")
    assert model.calls == [] and result.Status == "Completed"
    assert "RAM từ 64 GB" in result.AiMessages[0].Content
    with Session(shop.engine) as db:
        assert db.get(Message, result.CustomerMessage.MessageId).Metadata["AiModel"] == "vietech-rules"


def test_f03_a_slow_model_falls_back_to_the_backend_ranking_within_the_wording_budget(grounded_shop):
    shop = grounded_shop
    service, model = shop.service([provider_timeout])
    result = ask(shop, service)  # "Laptop ASUS dưới 20 triệu để học lập trình": ranked prefetch has asus-zen.
    assert model.calls[0][1]["timeout_seconds"] <= 10
    assert result.Status == "Completed"
    assert [m.Metadata["ProductId"] for m in result.AiMessages if m.MessageType == "Product"] == [shop.products["asus-zen"]]


def test_a_turn_without_a_backend_answer_keeps_the_full_timeout(grounded_shop):
    shop = grounded_shop
    service, model = shop.service([{"intent": "chat"}])  # 20 s turn: too short to cut a stalled call and resend it.
    ask(shop, service, "Bạn có thể giúp gì cho tôi?")
    assert model.calls[0][1]["timeout_seconds"] > 10


# --- Stalled calls (N01 timed out at 120 s; S03/S04 took 80–93 s in the second run) ---------------------------------

def test_n01_a_stalled_call_is_cut_and_sent_once_more(grounded_shop):
    shop = grounded_shop
    now = [0.0]

    def stall(messages):
        now[0] += STALL_SECONDS
        provider_timeout(messages)

    service, model = shop.service([stall, {"intent": "chat"}], timer=lambda: now[0],
                                  settings=AiSettings(api_key="test", timeout_seconds=60))
    result = ask(shop, service, "Bạn có thể giúp gì cho tôi?")
    assert result.Status == "Completed" and len(model.calls) == 2
    assert model.calls[0][1]["timeout_seconds"] == STALL_SECONDS
    assert model.calls[1][1]["timeout_seconds"] == 60 - STALL_SECONDS  # The rest of the turn.


def test_a_second_stall_in_the_turn_waits_out_the_turn_and_fails(grounded_shop):
    shop = grounded_shop
    service, model = shop.service([provider_timeout, provider_timeout],
                                  settings=AiSettings(api_key="test", timeout_seconds=60))
    with pytest.raises(AiUnavailableError) as error:
        ask(shop, service, "Bạn có thể giúp gì cho tôi?")
    assert error.value.code == "ai_unavailable" and len(model.calls) == 2
    assert model.calls[1][1]["timeout_seconds"] > STALL_SECONDS


def test_a_quota_error_still_fails_a_ranked_recommendation(grounded_shop):
    shop = grounded_shop

    def quota(_):
        raise AiUnavailableError("AI tạm hết hạn mức.", code="ai_quota_exceeded", retry_after_seconds=30)

    service, _ = shop.service([quota])
    with pytest.raises(AiUnavailableError) as error:
        ask(shop, service)
    assert error.value.code == "ai_quota_exceeded"


# --- Benchmark grader (C08, F02, P01, P03, P05, P06, N05, SC03, AR05) -----------------------------------------------

def test_grader_reads_every_backend_coupon_format():
    answer = ("• VIETECH50K: giảm 50.000 đ; đơn tối thiểu 1.000.000 đ\n- **LAPTOP5**: Giảm 5% (tối đa 500.000 đ)\n"
              "Mã VIETECH300K: giảm 300.000 đ; đơn tối thiểu 10.000.000 đ\n- Phiên bản: Bản thường; giá: 1.000 đ.\n"
              "- **Mã PHUKIEN10**: Giảm 10%\n- HDMI: 2 cổng")
    assert bench._listed_coupons({"answer": answer}) == {"VIETECH50K", "LAPTOP5", "VIETECH300K", "PHUKIEN10"}


def test_grader_accepts_a_prose_answer_about_one_code_but_still_needs_a_list_for_which_codes():
    coupon = type("Coupon", (), {"Code": "VIETECH300K", "DiscountType": "Fixed", "DiscountValue": Decimal(300_000),
                                 "MinOrderValue": Decimal(10_000_000), "MaxDiscountAmount": None})()
    catalog = bench.Catalog({}, {"VIETECH300K": coupon})
    one = bench.Case("P05", "pricing", ("Mã VIETECH300K áp dụng cho đơn từ bao nhiêu?",),
                     dict(kind="offers", include=("VIETECH300K",)))
    prose = turn(intent="offers", answer="Mã **VIETECH300K** áp dụng cho đơn hàng từ **10.000.000 đ**.")
    assert bench.grade(one, [prose], catalog)["passed"]
    which = bench.Case("P01", "pricing", ("Hôm nay có mã giảm giá nào không?",), dict(kind="offers"))
    assert not bench.grade(which, [turn(intent="offers", answer="Có nhiều ưu đãi hấp dẫn.")], catalog)["passed"]


def test_grader_accepts_comparison_lines_category_offers_and_the_nearest_product():
    a = item("p1", "Laptop A", 18_000_000, specs={"Pin": "42WHrs, 3-cell Li-ion", "RAM": "16 GB"})
    b = item("p2", "Laptop B", 22_041_000)
    catalog = bench.Catalog({i.id: i for i in (a, b)}, {}, {Decimal(2_000_000)})
    compared = turn(intent="compare", answer="1. Laptop A — Bản thường.\nPin: 42WHrs, 3-cell Li-ion.",
                    selected=[a.id], references=[a])
    offers = turn(intent="offers", answer="Điện thoại: giảm tới 2.000.000 đ (tối đa 10% giá niêm yết).")
    nearest = turn(intent="no_results", answer="Mẫu gần nhất là Laptop B với giá 22.041.000 đ.")
    # Smart Compare joins every alias of a row: "Pin" and "Dung lượng Pin".
    speaker = item("p3", "Loa C", 2_000_000, specs={"Pin": "Pin sạc Lithium-ion", "Dung lượng Pin": "12 giờ"})
    catalog.items[speaker.id] = speaker
    joined = turn(intent="compare", answer="1. Loa C — Đen.\nPin: Pin sạc Lithium-ion · 12 giờ.", selected=[speaker.id],
                  references=[speaker])
    for checked in (compared, offers, nearest, joined):
        notes = []
        assert bench._grounded(checked, catalog, notes), notes
    wrong = turn(intent="compare", answer="1. Laptop A — Bản thường.\nPin: 60WHrs.", selected=[a.id], references=[a])
    assert not bench._grounded(wrong, catalog, [])
    forged = turn(intent="offers", answer="Laptop: giảm tới 9.000.000 đ.")
    assert not bench._grounded(forged, catalog, [])
