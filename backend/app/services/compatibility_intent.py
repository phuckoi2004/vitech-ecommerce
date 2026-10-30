"""Compatibility intent/requirements only; never infers a device capability from customer text."""

import re

from app.core.search_text import fold
from app.schemas.ai_compatibility import VideoRequest

from .compatibility_specs import connector, resolution

_NEW_TASK = re.compile(r"\b(?:so sanh|tu van|goi y|de xuat|tim giup|muon mua|nen mua|khuyen mai|bao hanh|doi tra)\b")
_MODE = re.compile(r"\b(?:4k|uhd|qhd|fhd|1080p|1440p)\b|\d+\s*(?:hz|[x×]\s*\d+)")
_LINK = re.compile(r"\b(?:hdmi|displayport|dp|usb[ -]*(?:type[ -]*)?c|type[ -]*c|thunderbolt)\b")
# 'Máy thứ hai' names a shown laptop (resolved from the list); 'máy' alone is too vague.
_LAPTOP = re.compile(r"\b(?:laptop|macbook|may tinh xach tay)\b|\bmay\s+(?:thu|so)\s+\w+|\bmay dau tien\b")
# Devices outside the laptop -> monitor rules; prepare() answers them with the supported scope, not a guess.
OUT_OF_SCOPE = re.compile(r"\b(?:dien thoai|iphone|ipad|tablet|may tinh bang|bo sac|cu sac|hub|dock|docking)\b")
_FOLLOW_UP = re.compile(r"^(?:the|vay|con|neu)\b|\bthi sao\b|\bthi the nao\b")
# 'Vậy laptop này giá bao nhiêu?' / 'pin bao lâu?' after a check asks about the product, not the connection.
_OTHER_QUESTION = re.compile(r"\b(?:gia|bao nhieu tien|pin|ram|rom|bo nho|dung luong|o cung|ssd|chip|cpu|gpu|card"
                             r"|camera|trong luong|nang|kich thuoc|bao hanh|cau hinh|mau sac|he dieu hanh|con hang)\b")
_WHICH = re.compile(r"\b(?:laptop|macbook|man hinh|may|mau)\s+nao\b")
# Small talk is never the device name a pending check asked for ('Xin chào' is not a monitor model).
_SMALL_TALK = re.compile(r"^(?:xin\s+)?(?:chao|hello|hi|hey|alo)\b|\bcam on\b|\bthank|\btam biet\b|\bbye\b"
                         r"|\bban (?:la ai|lam duoc gi|giup duoc gi)\b")
_DEVICE_REFERENCE = re.compile(r"\b(?:laptop|macbook|man hinh)\b|\bmay\s+(?:thu|so)\s+\w+|\bmay dau tien\b")
# 'xuất 4K 60Hz ra màn hình', 'xuất tín hiệu sang màn hình'; never 'xuất xứ' or 'xuất hóa đơn'.
_OUTPUT = re.compile(r"\bxuat\s+(?:duoc\s+)?(?:hinh|video|tin hieu|man hinh|4k|8k|uhd|qhd|fhd|\d+\s*hz"
                     r"|\d{3,4}\s*[x×]\s*\d{3,4})(?![a-z0-9])"
                     r"|\bxuat\b(?:\s+\S+){0,6}?\s+(?:ra|sang|len|toi)\s+man hinh\b")
# 'nối … với màn hình', 'chạy 4K 120Hz trên màn hình', 'cắm vào màn hình': a monitor as the other device.
_CONNECT = re.compile(r"\b(?:noi|ket noi|cam|xuat|chay|choi|dung|su dung|hien thi|truyen)\b")
_TARGET = re.compile(r"\b(?:ra|voi|tren|vao|sang|len|toi)\s+(?:(?:mot|1|cai|chiec)\s+)?man hinh\b")
_ADAPTER = re.compile(r"\b(?:adapter|bo chuyen|dau chuyen|cap chuyen)\b")
_RUNS_MONITOR = re.compile(r"\b(?:chay|dung|su dung|noi|ket noi|cam)\s+(?:duoc\s+)?man hinh\b")
_UNIT = re.compile(r"\d+(?:[.,]\d+)?(?:hz|k|p|inch|in|gb|tb|mp|mah|w|wh|nits|ms|cm|mm)")


def _named_monitor(text):
    """'màn hình LG 24U631A-B', 'màn hình này/thứ hai/rời': another device. A laptop's own 'màn hình 144Hz' or
    'màn hình 2.8K' is not; a brand without a model is left to the existing rules."""
    for match in re.finditer(r"\bman hinh\b", text):
        rest = [word.strip("?.,!:;\"'") for word in text[match.end():].split()[:4]]
        if rest and re.fullmatch(r"nay|do|kia|thu|so|cua|roi|ngoai", rest[0]):
            return True
        if any(re.search(r"[a-z]", word) and re.search(r"\d", word) and not _UNIT.fullmatch(word) for word in rest):
            return True
    return False


def previous_compatibility(state):
    for turn in reversed(state.turns):
        if turn.slots.get("CompatibilitySubjects") or turn.slots.get("PendingCompatibility"):
            return turn.slots
        if turn.references and turn.answer_intent in ("recommend", "compare", "product", "describe"):
            break  # A newer product focus must not silently reuse an old device pair.
    return {}


def device_name_reply(question):
    """A pending device can receive a name; a new timing/connector question is not its model."""
    text = fold(question).strip(" .?!")
    return bool(text and not (_MODE.search(text) or _LINK.search(text) or _FOLLOW_UP.search(text)
                             or _OTHER_QUESTION.search(text) or _SMALL_TALK.search(text)))


def explicit_compatibility(text):
    """A display-connection question on its own. 'Tương thích Windows 11', 'kết nối Wi-Fi/Bluetooth', 'cổng kết nối
    gì' or 'màn hình này đạt 144Hz không' stay in the existing product flow. `text` is folded."""
    display = re.search(r"\b(?:man hinh|xuat (?:hinh|video)|thiet bi|adapter|bo chuyen)\b", text) or _LINK.search(text)
    return bool(
        re.search(r"\btuong thich\b", text) and (display or _MODE.search(text) or OUT_OF_SCOPE.search(text))
        or re.search(r"\bxuat (?:hinh|video)\b", text)
        or re.search(r"\bket noi\b", text) and (
            re.search(r"\bthiet bi\b", text)
            or "man hinh" in text and (_LAPTOP.search(text) or _LINK.search(text) or OUT_OF_SCOPE.search(text))
            or _LAPTOP.search(text) and _LINK.search(text) and not re.search(r"\bcong ket noi\b", text))
        or re.search(r"\bdung duoc\b", text) and "man hinh" in text and _LAPTOP.search(text)
        or "man hinh" in text and _MODE.search(text) and re.search(r"\b(?:chay dung|dat|cam)\b", text)
        and _LAPTOP.search(text)
        or re.search(r"\bcap (?:gi|nao)\b", text) and re.search(r"\b(?:laptop|macbook|man hinh)\b", text)
        or _OUTPUT.search(text)
        # 'Laptop A nối cổng USB-C với màn hình B', 'Laptop A chơi game 144Hz trên màn hình B', 'cần adapter gì để
        # nối MacBook với màn hình B': the pair is named, so the rules answer, never a product description.
        or _LAPTOP.search(text) and _TARGET.search(text) and _CONNECT.search(text)
        and (_named_monitor(text) or _LINK.search(text))
        # 'Laptop A chạy màn hình B ở 2560x1440 144Hz', 'MacBook dùng màn hình B được không' (CA13, CA15).
        or _LAPTOP.search(text) and _RUNS_MONITOR.search(text) and _named_monitor(text)
        or _ADAPTER.search(text) and "man hinh" in text and _LAPTOP.search(text))


def compatibility_question(question, state, *, new_request=False):
    """`new_request`: the analyzer saw a budget, need, promotion, policy, comparison or 'cheaper/more' request, so a
    previous or pending compatibility check must not capture it."""
    text = fold(question)
    if (re.search(r"^\s*(?:so sanh|tu van|goi y|de xuat|tim giup)\b", text)
            and not re.search(r"\btuong thich\b|\bket noi\b", text)):
        return False  # Comparing output specifications or asking for a new laptop stays in the existing flow.
    if new_request and _WHICH.search(text) and not re.search(r"\btuong thich\b|\bket noi\b", text):
        return False  # 'Laptop nào dưới 20 triệu xuất hình 4K?' asks for recommendations, not one pair's check.
    if explicit_compatibility(text):
        return True
    saved = previous_compatibility(state)
    if not saved or new_request or _NEW_TASK.search(re.sub(r"\b(?:vua|da) so sanh\b", "", text)):
        return False
    if saved.get("PendingCompatibility"):
        # A name/version reply fills the pending device, unless a new task or small talk follows.
        return bool(text) and not _SMALL_TALK.search(text)
    if _OTHER_QUESTION.search(text):
        return False
    # 'Nếu muốn 4K 144Hz thì sao?', 'Còn laptop thứ nhất thì sao?', 'Còn qua USB-C thì sao?' continue the last check.
    return bool(_MODE.search(text) and re.search(r"\b(?:neu|vay|con|thi|muon|duoc|ho tro|dat)\b", text)
                or _FOLLOW_UP.search(text) and (_LINK.search(text) or _DEVICE_REFERENCE.search(text)))


def video_request(question, previous=None):
    data = dict(previous or {})
    text = fold(question)
    size = resolution(text)
    if re.search(r"\b\d+k(?![a-z])", text) and size is None:
        raise ValueError("Cần độ phân giải cụ thể thay cho tên viết tắt mơ hồ/chưa hỗ trợ")
    if size:
        data["Width"], data["Height"] = size
    hz = re.search(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*hz\b", text)
    if hz:
        data["RefreshHz"] = float(hz[1].replace(",", "."))
    if re.search(r"\b(?:chi ket noi|chi can ket noi|ket noi co ban|khong can 4k|khong can tan so)\b", text):
        data.update(Width=None, Height=None, RefreshHz=None)
    # 'qua USB-C', 'bằng cáp HDMI', 'nối/dùng cổng USB-C': the laptop side the customer asked about, with or without
    # 'xuất hình'.
    source = re.search(r"\b(?:qua|bang|noi|dung|su dung|cam|tu)\s+(?:(?:cap|cong|day)\s+)?(hdmi|displayport|dp"
                       r"|usb[ -]*(?:type[ -]*)?c"
                       r"|type[ -]*c|thunderbolt)\b", text)
    if source is None and single_output_question(question):
        source = _LINK.search(text)
    if source:
        data["SourceConnector"] = connector(source[1] if source.lastindex else source[0])
    if re.search(r"\btruc tiep\b|\bkhong (?:dung|qua|can) (?:adapter|bo chuyen)\b", text):
        data["DirectOnly"] = True
    elif re.search(r"\b(?:dung|qua|co) (?:adapter|bo chuyen)\b", text):
        data["DirectOnly"] = False
    return VideoRequest.model_validate(data)


def single_output_question(question):
    text = fold(question)
    return bool(re.search(r"\bxuat (?:hinh|video)\b", text) and "man hinh" not in text and _LINK.search(text))
