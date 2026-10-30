"""Conservative readers of technical JSONB, independent of product names and Gemini.

Explicit video direction/capability is the evidence. One inference is made, only when the caller passes the device
type (normalize_video_specs(device_kind=...)): an HDMI/DisplayPort socket listed without a direction is an output on a
laptop and an input on a monitor, and so is a USB-C/Thunderbolt port whose own entry names DisplayPort or DP Alt Mode.
Such ports carry `inferred=True` and the rules say so. A bare USB-C stays unconfirmed. Structured video lists allow
exact signal modes without a database migration. A port list written as text may name the modes the manufacturer
publishes for that one port ("1 x HDMI 2.0 (tối đa 3840×2160 @ 60 Hz)"); they are read without colour format, bit
depth or DSC, so they never complete a signal mode on their own.
"""

import re
from dataclasses import dataclass, field, replace

from app.core.search_text import fold


CONNECTORS = {"hdmi": "HDMI", "displayport": "DisplayPort", "usb_c": "USB-C", "thunderbolt": "Thunderbolt"}
_CONNECTOR = re.compile(r"\b(?:usb[ -]*(?:type[ -]*)?c|type[ -]*c|thunderbolt(?:\s*[1-5])?|mini[ -]*displayport"
                        r"|display[ -]*port|hdmi|dp)\b")
_OUT = re.compile(r"\b(?:output|outputs|out|dau ra|cong ra|xuat hinh|xuat video|video out)\b")
# Power and wording ('DC-in 65W', 'built-in', 'đầu vào nguồn') never make a port a video input.
_IN = re.compile(r"\b(?:input|inputs|(?<!dc-)(?<!dc )(?<!built-)(?<!plug-)in|(?:dau|cong) vao(?! nguon)|nhan hinh"
                 r"|nhan video|video in)\b")
_NEGATIVE = re.compile(r"\b(?:khong|no|not|without)\b|data only|chi (?:truyen )?du lieu|chi sac")
# Negation before ('không hỗ trợ DP Alt Mode', 'no DP') or after ('DP Alt Mode: Không') a video capability.
_NO_VIDEO = re.compile(r"\b(?:khong|no|not|without)\s+(?:(?:co|ho tro|support|supports|video)\s+)*"
                       r"(?:hdmi|displayport|dp|video|xuat hinh|nhan hinh|alt(?:ernate)?[ -]*mode)\b"
                       r"|\b(?:displayport|dp|alt(?:ernate)?[ -]*mode|video|xuat hinh|nhan hinh)\s*[:=]\s*"
                       r"(?:khong|no|none)\b"
                       r"|data only|chi (?:truyen )?du lieu|chi sac")
_ALT = re.compile(r"(?:displayport|\bdp\b)\s*(?:[12](?:\.\d)?\s*)?(?:alt(?:ernate)?[ -]*mode)"
                  r"|(?:displayport|\bdp\b) over usb"  # VESA's name for DP Alt Mode.
                  r"|(?:displayport|\bdp\b)[^;()]{0,30}?\bche do alt\b")  # 'tín hiệu DP 1.2a với chế độ Alt'.
# Wording that makes a DisplayPort mention after USB-C/Thunderbolt a signal of that port, not another physical port.
_CARRIES = re.compile(r"/|\b(?:ho tro|support|supports|tin hieu|signal|qua)\b")
# '1x USB-C (10Gbps), với DisplayPort 1.4': a clause continuing the port listed just before it.
_CONTINUES = re.compile(r"\s*(?:voi|ho tro|support|supports|with|kem theo)\b")


def connector(value):
    value = fold(str(value)).strip().replace("_", " ")
    if re.fullmatch(r"usb[ -]*(?:type[ -]*)?c|type[ -]*c", value):
        return "usb_c"
    if re.fullmatch(r"(?:mini[ -]*)?(?:display[ -]*port|dp)", value):
        return "displayport"
    if re.fullmatch(r"thunderbolt(?:\s*[1-5])?", value):
        return "thunderbolt"  # Thunderbolt alone never proves video; only an explicit DP Alt Mode does.
    return value if value == "hdmi" else None


def _clauses(text):
    """Split a port list on ';', new lines and top-level commas: '(USB 3.2, DisplayPort 1.2)' stays one port."""
    clauses, depth, start = [], 0, 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char in ";\n" or (char == "," and depth == 0 and not text[index + 1:index + 2].isdigit()):
            clauses.append(text[start:index])
            start = index + 1
    return [*clauses, text[start:]]


def _signal_of_usb(clause, tokens, dp):
    """True when a DP mention describes a preceding USB-C/Thunderbolt port's signal, not a separate connector."""
    if any(m.start() <= dp.start() < m.end() for m in _ALT.finditer(clause)):
        return True
    for usb in tokens:
        if usb.start() >= dp.start() or connector(usb[0]) not in ("usb_c", "thunderbolt"):
            continue
        between = clause[usb.end():dp.start()]
        if between.count("(") > between.count(")") or _CARRIES.search(between):
            return True
    return False


def _fields(value):
    return {re.sub(r"[^a-z0-9]", "", fold(str(k))): v for k, v in value.items()} if isinstance(value, dict) else {}


def _number(value, maximum):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if 0 < number <= maximum else None
    except (ValueError, TypeError, OverflowError):
        return None


def resolution(value):
    text = fold(str(value or ""))
    explicit = re.search(r"(?<!\d)(\d{3,5})\s*[x×*]\s*(\d{3,5})(?!\d)", text)
    if explicit:
        width, height = int(explicit[1]), int(explicit[2])
        return (width, height) if max(width, height) <= 16384 else None
    for pattern, dimensions in ((r"\b8k(?![a-z])|\b4320p\b", (7680, 4320)), (r"\b4k(?![a-z])|\buhd\b|\b2160p\b", (3840, 2160)),
                                 (r"\bqhd\b|\b1440p\b", (2560, 1440)),
                                 (r"\bfhd\b|\b1080p\b", (1920, 1080))):
        if re.search(pattern, text):
            return dimensions
    return None


@dataclass(frozen=True)
class SignalMode:
    width: int
    height: int
    hz: float
    color: str | None = None
    bits: int | None = None
    dsc: bool | None = None

    def label(self):
        return f"{self.width}×{self.height} @ {self.hz:g} Hz"

    def signature(self):
        return self.width, self.height, self.hz, self.color, self.bits, self.dsc

    def complete(self):
        return self.color is not None and self.bits is not None and self.dsc is not None


def _modes(value):
    modes = []
    for item in (value if isinstance(value, list) else [value])[:24]:
        fields = _fields(item)
        if fields:
            width, height = _number(fields.get("width"), 16384), _number(fields.get("height"), 16384)
            hz = _number(fields.get("refreshhz", fields.get("refreshrate")), 1000)
            color = str(fields.get("colorformat", "")).upper()
            color = color if color in ("RGB", "4:4:4", "4:2:2", "4:2:0") else None
            bits = fields.get("bitdepth")
            bits = bits if type(bits) is int and bits in (8, 10, 12, 16) else None
            dsc = fields.get("dsc") if type(fields.get("dsc")) is bool else None
        else:
            text = str(item)
            size = resolution(text)
            hz_match = re.search(r"(?:@|\bat\b)\s*(\d+(?:[.,]\d+)?)\s*hz", fold(text))
            width, height = size or (None, None)
            hz = _number(hz_match[1].replace(",", "."), 1000) if hz_match else None
            color = bits = dsc = None
        if width and height and hz and int(width) == width and int(height) == height:
            modes.append(SignalMode(int(width), int(height), hz, color, bits, dsc))
    return tuple(dict.fromkeys(modes))


# A mode named in one port's text: "3840×2160 @ 60 Hz", "4K@60Hz", "8K/60Hz", "FHD@60 Hz". A resolution or a refresh
# rate alone is no mode, and "2K" is not read (2048×1080 or 2560×1440).
_TEXT_MODE = re.compile(r"(?<![\d.])((?:\d{3,5}\s*[x×*]\s*\d{3,5})|8k|4k|uhd|qhd|fhd|4320p|2160p|1440p|1080p)"
                        r"\s*(?:@|/|\bat\b)?\s*(\d{2,3}(?:[.,]\d+)?)\s*hz\b")


_UP_TO = re.compile(r"\s*(?:len den|toi da|ho tro|up to|supports?|max(?:imum)?)\b")


def _text_modes(piece):
    return _modes([f"{m[1]} @ {m[2]}hz" for m in _TEXT_MODE.finditer(piece)])


@dataclass(frozen=True)
class VideoPort:
    connector: str
    direction: str | None
    video: bool | None
    alt_mode: bool | None
    version: str | None
    evidence: str
    modes: tuple[SignalMode, ...] = ()
    max_resolution: tuple[int, int] | None = None
    max_hz: float | None = None
    inferred: bool = False  # Direction taken from the device type, not stated for this port.
    # A listed port whose direction may be taken from the device type: an HDMI/DisplayPort socket, or a USB-C/Thunderbolt
    # entry naming DisplayPort/DP Alt Mode; never a negated or ambiguous entry (text ports only).
    inferable: bool = False
    # The modes are a manufacturer's published maximum for the port, read from text ("tối đa 1920 x 1080 @ 120 Hz"),
    # not an exact list with colour format, bit depth and DSC (compatibility._published).
    limits: bool = False

    def usable(self, direction):
        return self.direction in (direction, "both") and self.video is True


@dataclass(frozen=True)
class VideoCable:
    source: str
    target: str
    modes: tuple[SignalMode, ...]
    evidence: str


@dataclass
class VideoProfile:
    ports: list[VideoPort] = field(default_factory=list)
    cables: list[VideoCable] = field(default_factory=list)
    outputs_complete: bool = False
    inputs_complete: bool = False
    facts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _direction(text):
    out, in_ = bool(_OUT.search(text)), bool(_IN.search(text))
    return "output" if out and not in_ else "input" if in_ and not out else None


def _structured_port(value, default_direction, path):
    fields = _fields(value)
    kind = connector(fields.get("connector", fields.get("type", "")))
    if not kind:
        return None
    raw_direction = fields.get("direction")
    raw_direction = raw_direction.strip().lower() if isinstance(raw_direction, str) else raw_direction
    direction = raw_direction if raw_direction in ("input", "output", "both") else default_direction
    if raw_direction is not None and raw_direction not in ("input", "output", "both"):
        direction = None
    video = fields.get("video") if type(fields.get("video")) is bool else None
    alt = fields.get("dpaltmode") if type(fields.get("dpaltmode")) is bool else None
    # HDMI/DP with an explicit video direction is a video interface; USB-C still needs its capability stated.
    if video is None and (kind in ("hdmi", "displayport") and direction or alt is True):
        video = True
    version = str(fields["version"])[:20] if isinstance(fields.get("version"), (str, int, float)) else None
    modes = _modes(fields.get("modes", []))
    label = re.sub(r"VideoOutputs$", "Cổng xuất hình", path, flags=re.I)
    label = re.sub(r"VideoInputs$", "Cổng nhận hình", label, flags=re.I)
    label = re.sub(r"VideoPorts$", "Cổng video", label, flags=re.I)
    flow = {"output": "đầu ra", "input": "đầu vào", "both": "hai chiều"}.get(direction, "chưa rõ chiều")
    details = f"{label}: {CONNECTORS[kind]} {version or ''}, {flow}"
    details += ", truyền hình ảnh: " + {True: "có", False: "không", None: "chưa xác nhận"}[video]
    if alt is not None:
        details += f", DP Alt Mode: {'có' if alt else 'không'}"
    if modes:
        details += ", " + ", ".join(m.label() for m in modes[:4])
    if fields.get("maxresolution"):
        details += f", độ phân giải tối đa {str(fields['maxresolution'])[:50]}"
    if _number(fields.get("maxrefreshhz"), 1000):
        details += f", tần số tối đa {fields['maxrefreshhz']} Hz"
    return VideoPort(kind, direction, video, alt, version, details[:600], modes,
                     resolution(fields.get("maxresolution")), _number(fields.get("maxrefreshhz"), 1000))


def _text_ports(key, value):
    text = fold(str(value))
    key_folded = fold(key)
    key_direction = _direction(key_folded)
    if text.strip() in ("0", "none", "khong", "khong co", "no", "n/a", "-"):
        return []
    key_usb = any(connector(m[0]) == "usb_c" for m in _CONNECTOR.finditer(key_folded))
    if key_usb:
        text = key_folded + ": " + text
    matches = list(_CONNECTOR.finditer(text))
    if not matches:
        matches = list(_CONNECTOR.finditer(key_folded))
        text = key_folded + ": " + text
    found = []
    # Do not attribute a neighbouring connector's Alt Mode, direction or maximum to a different port.
    for clause in _clauses(text):
        tokens = list(_CONNECTOR.finditer(clause))
        continues_usb = bool(found and found[-1].connector in ("usb_c", "thunderbolt") and _CONTINUES.match(clause))
        # 'USB-C (USB 3.2, DisplayPort 1.2)', 'Type-C hỗ trợ DisplayPort', 'Thunderbolt 4 (DP Alt Mode)' and a
        # USB-C field's 'DP Alt Mode' name a signal of that USB-C port; an Alt Mode phrase is never a DP socket.
        tokens = [m for m in tokens if connector(m[0]) != "displayport"
                  or not (key_usb or continues_usb or _signal_of_usb(clause, tokens, m))]
        if not tokens and found and found[-1].connector in ("usb_c", "thunderbolt") and _ALT.search(clause):
            # 'USB-C 3.2, hỗ trợ DP Alt Mode': the Alt Mode clause continues the USB-C port listed just before it.
            previous = found[-1]
            if previous.video is not False and previous.alt_mode is None:
                negative = bool(_NO_VIDEO.search(clause))
                found[-1] = replace(previous, alt_mode=not negative, video=previous.video if negative else True)
            continue
        if not tokens and found and _UP_TO.match(clause) and _TEXT_MODE.search(clause) and not _NO_VIDEO.search(clause):
            # '1x HDMI 2.1, lên đến 8K/60Hz': the modes of the port listed just before it.
            if found[-1].video is not False:
                found[-1] = replace(found[-1], modes=tuple(dict.fromkeys(found[-1].modes + _text_modes(clause))), limits=True)
            continue
        if not tokens and continues_usb and _DP_SIGNAL.search(clause) and not _NO_VIDEO.search(clause):
            # '1x USB-C (10Gbps), với DisplayPort 1.4': the USB-C port just listed carries DisplayPort, over DP Alt Mode
            # when its direction is stated (as in its own entry above).
            previous = found[-1]
            stated = previous.direction is not None and previous.video is not False
            found[-1] = replace(previous, inferable=previous.video is not False, alt_mode=True if stated else previous.alt_mode,
                                video=True if stated else previous.video)
            continue
        ambiguous_negative = len(tokens) > 1 and bool(_NEGATIVE.search(clause))
        for index, match in enumerate(tokens):
            kind = connector(match[0])
            if kind is None:
                continue
            end = tokens[index + 1].start() if index + 1 < len(tokens) else len(clause)
            piece = clause[:end] if index == 0 else clause[match.start():end]
            direction = _direction(piece) or key_direction
            negative = bool(_NO_VIDEO.search(piece) or _NO_VIDEO.search(key_folded)
                            or re.search(r"(?<!\d)0\s*[x×]\s*(?:hdmi|displayport|usb)", piece))
            # A USB-C/Thunderbolt entry stating its video direction and naming DisplayPort ('USB-C hỗ trợ DisplayPort
            # 1.4a, xuất hình tối đa 4K@60Hz') carries DP Alt Mode, as the device-type reading already assumes.
            alt_mode = (not negative) if kind in ("usb_c", "thunderbolt") and (
                _ALT.search(piece) or (direction and _DP_SIGNAL.search(piece))) else None
            if negative:
                video = False
            else:
                video = True if (kind in ("hdmi", "displayport") and direction or alt_mode is True
                                      or re.search(r"video|xuat hinh|nhan hinh", piece)) else None
            if ambiguous_negative:
                video = alt_mode = direction = None
            inferable = not (negative or ambiguous_negative) and (
                kind in ("hdmi", "displayport") or alt_mode is True or bool(_DP_SIGNAL.search(piece)))
            ver = re.match(r"\s*(\d(?:\.\d[a-z]?)?)\b", clause[match.end():end])
            evidence = f"{key}: {str(value)[:400]}"
            modes = () if video is False else _text_modes(piece)
            found.append(VideoPort(kind, direction, video, alt_mode, ver[1] if ver else None, evidence,
                                   modes=modes, inferable=inferable, limits=bool(modes)))
    return found


_DP_SIGNAL = re.compile(r"display[ -]*port|\bdp\b")
_INFERRED_DIRECTION = {"laptop": "output", "monitor": "input"}


def _inferred(port, device_kind):
    """The port's direction from the device type when the port itself states none (module docstring)."""
    if port.direction is not None or not port.inferable or port.video is False:
        return port
    direction = _INFERRED_DIRECTION[device_kind]
    note = (" (chiều " + ("xuất hình" if direction == "output" else "nhận hình")
            + " suy theo loại thiết bị, hãng không ghi rõ chiều cho cổng này)")
    usb = port.connector in ("usb_c", "thunderbolt")
    return replace(port, direction=direction, video=True, alt_mode=True if usb else port.alt_mode, inferred=True,
                   evidence=(port.evidence[:540] + note)[:600])


def normalize_video_specs(specifications, *, variant_id=None, device_kind=None):
    """Read public technical fields only; never reads a product name, GPU marketing text or another SKU.

    `device_kind` ("laptop"/"monitor") enables the one direction inference described in the module docstring."""
    profile = VideoProfile()
    source = specifications if isinstance(specifications, dict) else {}
    source = {k: v for k, v in source.items() if not str(k).startswith("_")}
    variants = source.get("VideoByVariant")
    source = {k: v for k, v in source.items() if k != "VideoByVariant"}
    if isinstance(variants, dict) and variant_id:
        override = variants.get(str(variant_id))
        if isinstance(override, dict):
            source.update({k: v for k, v in override.items() if not str(k).startswith("_")})

    visited = 0
    declared_outputs = declared_inputs = False
    def collect(data, path="", depth=0):
        nonlocal visited, declared_outputs, declared_inputs
        if not isinstance(data, dict) or depth > 4:
            return
        for key, value in data.items():
            visited += 1
            if visited > 150 or len(profile.ports) >= 32:
                profile.warnings.append("Thông số vượt giới hạn đọc, danh sách cổng chưa được xác nhận đầy đủ.")
                profile.outputs_complete = profile.inputs_complete = False
                return
            if str(key).startswith("_"):
                continue
            label = f"{path} / {key}" if path else str(key)
            folded = re.sub(r"[^a-z0-9]", "", fold(str(key)))
            if folded in ("videooutputscomplete", "danhsachcongxuathinhdaydu"):
                profile.outputs_complete = value is True
            elif folded in ("videoinputscomplete", "danhsachcongnhanhinhdaydu"):
                profile.inputs_complete = value is True
            elif folded in ("videooutputs", "videoinputs", "videoports") and isinstance(value, list):
                direction = "output" if folded == "videooutputs" else "input" if folded == "videoinputs" else None
                declared_outputs = declared_outputs or folded == "videooutputs"
                declared_inputs = declared_inputs or folded == "videoinputs"
                for item in value[:24]:
                    port = _structured_port(item, direction, label)
                    if port:
                        profile.ports.append(port)
                        if (direction and port.direction not in (direction, "both")) or (port.video is False and port.alt_mode is True):
                            profile.warnings.append(f"{label}: chiều hoặc chức năng video mâu thuẫn, cần xác minh lại.")
                        if any((port.max_hz and m.hz > port.max_hz) or (port.max_resolution and (
                                m.width > port.max_resolution[0] or m.height > port.max_resolution[1])) for m in port.modes):
                            profile.warnings.append(f"{label}: giới hạn và chế độ tín hiệu mâu thuẫn, cần xác minh lại.")
                    else:
                        profile.warnings.append(f"{label}: có mục cổng chưa đọc được.")
                        profile.outputs_complete = profile.inputs_complete = False
                if len(value) > 24:
                    profile.warnings.append(f"{label}: danh sách bị giới hạn khi đọc.")
            elif folded == "videocables" and isinstance(value, list):
                for item in value[:12]:
                    fields = _fields(item)
                    from_, to = connector(fields.get("from", "")), connector(fields.get("to", ""))
                    evidence = fields.get("evidence")
                    if fields.get("verified") is True and from_ and to and isinstance(evidence, str) and evidence.strip():
                        profile.cables.append(VideoCable(from_, to, _modes(fields.get("modes", [])), evidence[:400]))
            elif isinstance(value, dict):
                collect(value, label, depth + 1)
            elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
                relevant = (re.search(r"cong|hdmi|displayport|usb.?c|thunderbolt|video|ports|interfaces|connections", fold(str(key)))
                            or _CONNECTOR.search(fold(str(key))))
                if relevant:
                    profile.ports.extend(_text_ports(label, value))
                if relevant or re.search(r"do phan giai|tan so quet|resolution|refresh", fold(str(key))):
                    profile.facts.append(f"{label}: {str(value)[:400]}")
    collect(source)
    profile.outputs_complete = profile.outputs_complete and declared_outputs
    profile.inputs_complete = profile.inputs_complete and declared_inputs
    if profile.warnings:
        profile.outputs_complete = profile.inputs_complete = False
    profile.ports = list(dict.fromkeys(profile.ports))[:32]
    if device_kind in _INFERRED_DIRECTION:
        profile.ports = list(dict.fromkeys(_inferred(port, device_kind) for port in profile.ports))
    profile.facts = list(dict.fromkeys([*profile.facts, *(p.evidence for p in profile.ports)]))[:24]
    return profile
