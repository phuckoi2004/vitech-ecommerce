"""Laptop/display rules. Pure functions: no provider, database, product names or price heuristics.

R1: video output -> matching video input establishes basic connectivity, conditional on a suitable cable. A direction
taken from the device type (compatibility_specs: a laptop's listed HDMI is an output, a monitor's an input) is used
too, and the result says so (INFERRED_NOTE). R2: only documented, directional DP/DP Alt Mode conversions may suggest an adapter. R3: advertised panel Hz
and interface versions never establish a signal mode. R4: full mode confirmation needs matching per-port timings,
colour/depth/DSC and a verified cable/adapter mode. R4b (owner's decision, 29/10/2026): a mode a manufacturer publishes
as one port's maximum, in text and without colour/depth/DSC ("HDMI 2.0, tối đa 1920 x 1080 @ 120 Hz"), covers the same
aspect ratio at a resolution and a refresh rate no higher than it; a mode covered at both ends of one path is
compatible, conditional on a cable/adapter rated for it, and says so (PUBLISHED_NOTE). A request above the published
maximum at either end of every path is incompatible. R5: absence of evidence is unknown; negatives need explicit limits
or a complete, unambiguous inventory and an explicitly scoped direct-only request.
"""

from dataclasses import dataclass

from app.schemas.ai_compatibility import CompatibilityCriterion, VideoRequest

from .compatibility_specs import CONNECTORS, VideoPort, VideoProfile

INFERRED_NOTE = ("Chiều xuất/nhận hình của cổng được suy theo loại thiết bị (laptop xuất hình, màn hình nhận hình) vì "
                 "thông số chỉ liệt kê tên cổng, hãng không ghi rõ chiều cho cổng này.")
PUBLISHED_NOTE = ("Chế độ hình được đối chiếu với mức tối đa hãng công bố cho từng cổng, định dạng màu, độ sâu màu và "
                  "DSC chưa được hãng xác nhận, và cần cáp hoặc bộ chuyển đổi đạt chuẩn cho chế độ này.")


@dataclass(frozen=True)
class ConnectionPath:
    source: VideoPort
    target: VideoPort
    adapter: str | None = None

    @property
    def inferred(self):
        return self.source.inferred or self.target.inferred

    def cable_label(self):
        if self.adapter:
            return self.adapter
        return (f"Cáp {CONNECTORS[self.source.connector]} truyền video phù hợp giữa hai cổng"
                + (" trong danh sách cổng." if self.inferred else " đã xác minh."))


@dataclass
class CompatibilityResult:
    status: str
    criteria: list[CompatibilityCriterion]
    conditions: list[str]
    missing: list[str]
    limitations: list[str]

    def explanation_options(self):
        options = [{"Id": c.Id, "Text": c.Summary} for c in self.criteria if c.Requested]
        if self.conditions:
            options.append({"Id": "conditions", "Text": "Kết luận chỉ áp dụng khi đáp ứng các điều kiện cáp và kết nối đã liệt kê."})
        if self.missing:
            options.append({"Id": "missing", "Text": "Cần kiểm tra thêm các thông số còn thiếu đã liệt kê trước khi xác nhận phần đó."})
        return options


def _unique(values, limit=24):
    return list(dict.fromkeys(value for value in values if value))[:limit]


def _criterion(id_, label, status, summary, evidence=(), missing=(), requested=True):
    return CompatibilityCriterion(Id=id_, Label=label, Status=status, Summary=summary,
                                  Evidence=_unique(evidence, 12), Missing=_unique(missing, 12), Requested=requested)


def _video_ports(profile, direction, requested_connector=None):
    return [p for p in profile.ports if p.usable(direction)
            and (requested_connector is None or p.connector == requested_connector)]


def _alt_mode(port):
    # Thunderbolt 3+ ports are USB-C; only an explicitly documented DP Alt Mode makes either one a DP source/sink.
    return port.connector in ("usb_c", "thunderbolt") and port.alt_mode is True


def _paths(source, target, request):
    paths = []
    for output in _video_ports(source, "output", request.SourceConnector):
        for input_ in _video_ports(target, "input"):
            if output.connector == input_.connector and output.connector in ("hdmi", "displayport"):
                paths.append(ConnectionPath(output, input_))
            elif _alt_mode(output) and _alt_mode(input_):
                paths.append(ConnectionPath(output, input_))
            elif not request.DirectOnly:
                if _alt_mode(output) and input_.connector in ("displayport", "hdmi"):
                    label = (f"Cáp chuyển {CONNECTORS[output.connector]} có DP Alt Mode (laptop) → "
                             f"{CONNECTORS[input_.connector]} (màn hình), đúng chiều tín hiệu.")
                    paths.append(ConnectionPath(output, input_, label))
                elif output.connector == "displayport" and input_.connector == "hdmi":
                    paths.append(ConnectionPath(output, input_, "Bộ chuyển đổi chủ động DisplayPort (laptop) → HDMI (màn hình), đúng chiều tín hiệu."))
    return sorted(paths, key=lambda p: p.adapter is not None)


def _known_absent(profile, direction, selected=None):
    if not (profile.outputs_complete if direction == "output" else profile.inputs_complete):
        return False
    # Thunderbolt 3+ uses the USB-C connector and a USB-C entry may be Thunderbolt: neither proves the other absent.
    usb_family = {"usb_c", "thunderbolt"}
    candidates = [p for p in profile.ports if selected is None or p.connector == selected
                  or {selected, p.connector} <= usb_family]
    if any(p.direction is None for p in candidates):
        return False
    return all(p.video is False for p in candidates if p.direction in (direction, "both"))


def _unambiguous(profile, direction):
    ports = [p for p in profile.ports if p.direction in (direction, "both", None)]
    return all(p.direction is not None and p.video is not None and (
        p.video is False or p.connector in ("hdmi", "displayport") or _alt_mode(p)) for p in ports)


def _limited(port, request, dimension):
    if dimension == "resolution" and request.Width and port.max_resolution:
        return request.Width > port.max_resolution[0] or request.Height > port.max_resolution[1]
    return bool(dimension == "refresh_rate" and request.RefreshHz and port.max_hz and request.RefreshHz > port.max_hz)


def _requested(mode, request):
    return (request.Width is None or (mode.width, mode.height) == (request.Width, request.Height)) and (
        request.RefreshHz is None or mode.hz == request.RefreshHz)


def _covers(port, width, height, hz):
    """The port's published maxima that carry width×height (same aspect ratio) at hz, or at some rate when hz is None."""
    return [m for m in port.modes if port.limits and m.width >= width and m.height >= height
            and m.width * height == m.height * width and (hz is None or m.hz >= hz)]


def _sizes(path, request):
    """The resolutions to check: the requested one or, when only a refresh rate is asked, the monitor's published ones."""
    if request.Width:
        return [(request.Width, request.Height)]
    return sorted({(m.width, m.height) for m in path.target.modes} if path.target.limits else (), reverse=True)


def _published(paths, request):
    """(path, mode label, laptop maximum, monitor maximum) of the first path whose two ends cover the request (R4b)."""
    for path in paths:
        for width, height in _sizes(path, request):
            source = _covers(path.source, width, height, request.RefreshHz)
            target = _covers(path.target, width, height, request.RefreshHz)
            if source and target:
                top_source, top_target = max(source, key=lambda m: m.hz), max(target, key=lambda m: m.hz)
                hz = request.RefreshHz or min(top_source.hz, top_target.hz)
                return path, f"{width}×{height} @ {hz:g} Hz", top_source, top_target
    return None


def _beyond(port, width, height, hz):
    """Every published maximum of the port is below the request: a smaller resolution, or a lower rate at it."""
    return port.limits and bool(port.modes) and all(
        width > m.width or height > m.height or ((m.width, m.height) == (width, height) and hz is not None and hz > m.hz)
        for m in port.modes)


def _published_limit(paths, request, dimension=None):
    """Every path has an end whose published maximum is below the request (by resolution, refresh rate, or either)."""
    def beyond(port, width, height):
        if dimension == "resolution":
            return _beyond(port, width, height, None)
        if dimension == "refresh_rate":
            return _beyond(port, width, height, request.RefreshHz) and not _beyond(port, width, height, None)
        return _beyond(port, width, height, request.RefreshHz)
    return bool(paths) and all(
        bool(sizes) and all(beyond(path.source, w, h) or beyond(path.target, w, h) for w, h in sizes)
        for path in paths for sizes in [_sizes(path, request)])


def _mode_check(paths, source, target, request):
    # A limit disproves a mode only if no other video port (e.g. USB-C video of unknown protocol) could carry it.
    complete_inventory = (source.outputs_complete and target.inputs_complete
                          and _unambiguous(source, "output") and _unambiguous(target, "input"))
    evidence = [p.evidence for path in paths for p in (path.source, path.target)]
    modes = [(path, a) for path in paths for a in path.source.modes if _requested(a, request)
             and any(a.signature() == b.signature() for b in path.target.modes)]
    verified = [(path, mode, cable) for path, mode in modes if mode.complete() and not source.warnings and not target.warnings
                for cable in [*source.cables, *target.cables]
                if cable.source == path.source.connector and cable.target == path.target.connector
                and any(m.signature() == mode.signature() for m in cable.modes)]
    missing = []
    if not paths:
        missing.append("Đường xuất hình từ laptop đến đầu vào màn hình")
    if paths and not any(path.source.modes for path in paths):
        missing.append("Laptop: các chế độ tín hiệu đầu ra của cổng đang xét")
    if paths and not any(path.target.modes for path in paths):
        missing.append("Màn hình: các chế độ tín hiệu đầu vào của cổng đang xét")
    if not modes:
        missing.append("Chế độ chung có cùng độ phân giải và tần số quét ở cả hai đầu")
    elif not any(mode.complete() for _, mode in modes):
        missing.append("Định dạng màu, độ sâu màu và điều kiện DSC khớp nhau ở hai đầu")
    if not verified:
        missing.append("Cáp/bộ chuyển đổi được xác minh cho đúng chế độ tín hiệu và chiều kết nối")
    if source.warnings or target.warnings:
        missing.append("Xác minh lại các thông số thiếu nhất quán hoặc chưa đọc đủ")
    over_resolution = paths and all(_limited(p.source, request, "resolution") or _limited(p.target, request, "resolution") for p in paths)
    over_refresh = paths and all(_limited(p.source, request, "refresh_rate") or _limited(p.target, request, "refresh_rate") for p in paths)
    published = None if verified else _published(paths, request)
    published_negative = not verified and not published and _published_limit(paths, request)
    negative = bool(complete_inventory and (over_resolution or over_refresh)) or published_negative
    status = "compatible" if verified or published else "incompatible" if negative else "unknown"
    notes = []
    if verified:
        path, mode, cable = verified[0]
        summary = (f"Chế độ {mode.label()} đã có căn cứ ở hai cổng và cáp/bộ chuyển đổi: "
                   f"{mode.color}, {mode.bits} bit, DSC {'bật' if mode.dsc else 'tắt'}.")
        evidence.append(cable.evidence)
        conditions = [path.cable_label(), f"Dùng đúng cấu hình {mode.label()}, {mode.color}, {mode.bits} bit, DSC {'bật' if mode.dsc else 'tắt'} đã ghi trong thông số."]
        missing = []
    elif published:
        path, label, top_source, top_target = published
        evidence = [path.source.evidence, path.target.evidence]
        summary = (f"Theo mức tối đa hãng công bố, cổng {CONNECTORS[path.source.connector]} của laptop xuất tối đa "
                   f"{top_source.label()} và cổng {CONNECTORS[path.target.connector]} của màn hình nhận tối đa "
                   f"{top_target.label()}, chế độ {label} nằm trong giới hạn của cả hai đầu.")
        conditions = [path.cable_label(), f"Cáp hoặc bộ chuyển đổi phải hỗ trợ {label}."]
        missing, notes = [], [PUBLISHED_NOTE]
    else:
        summary = ("Chế độ yêu cầu vượt mức tối đa hãng công bố cho cổng của laptop hoặc màn hình trên mọi đường kết nối."
                   if published_negative else
                   "Chế độ yêu cầu vượt giới hạn đầu ra/đầu vào đã ghi rõ trong danh sách cổng đầy đủ." if negative else
                   "Chưa đủ dữ liệu để xác nhận chế độ độ phân giải và tần số quét yêu cầu trên toàn bộ đường truyền.")
        conditions = []
        if published_negative:
            missing = []
    resolution_known = bool(request.Width and any(
        (a.width, a.height) == (b.width, b.height) == (request.Width, request.Height) and a.hz == b.hz
        for p in paths for a in p.source.modes for b in p.target.modes))
    refresh_known = bool(request.RefreshHz and any(
        a.hz == b.hz == request.RefreshHz and (a.width, a.height) == (b.width, b.height)
        and (request.Width is None or (a.width, a.height) == (request.Width, request.Height))
        for p in paths for a in p.source.modes for b in p.target.modes))
    mode_path = verified[0][0] if verified else published[0] if published else None
    if status == "compatible" and mode_path is not None and mode_path.adapter:
        status = "requires_adapter"  # The mode is reached only through that path's adapter (CA13), as in the verdict.
    resolution_published = bool(request.Width and any(
        _covers(p.source, request.Width, request.Height, None) and _covers(p.target, request.Width, request.Height, None)
        for p in paths))
    refresh_published = bool(request.RefreshHz and published)
    resolution_status = ("compatible" if resolution_known or resolution_published else "incompatible" if (
        complete_inventory and over_resolution or request.Width and _published_limit(paths, request, "resolution")) else "unknown")
    refresh_status = ("compatible" if refresh_known or refresh_published else "incompatible" if (
        complete_inventory and over_refresh or request.RefreshHz and _published_limit(paths, request, "refresh_rate")) else "unknown")
    criteria = [
        _criterion("resolution", "Độ phân giải theo thông số hai cổng", resolution_status,
            "Hai cổng có ghi cùng một độ phân giải ở ít nhất một tần số, điều này chưa xác nhận chế độ đầy đủ với cáp hiện tại." if resolution_known else
            "Độ phân giải này nằm trong mức tối đa hãng công bố cho cổng ở cả hai đầu." if resolution_published else
            "Độ phân giải yêu cầu vượt giới hạn được ghi rõ." if resolution_status == "incompatible" else
            "Chưa đủ dữ liệu đầu ra và đầu vào để xác nhận độ phân giải này." if request.Width else "Bạn chưa yêu cầu độ phân giải cụ thể.",
            evidence, requested=request.Width is not None),
        _criterion("refresh_rate", "Tần số quét tại độ phân giải đang xét", refresh_status,
            "Hai cổng có ghi cùng một chế độ với tần số yêu cầu, vẫn cần xác minh cáp và các điều kiện tín hiệu." if refresh_known else
            "Tần số này ở độ phân giải đang xét nằm trong mức tối đa hãng công bố cho cổng ở cả hai đầu." if refresh_published else
            "Tần số yêu cầu vượt giới hạn được ghi rõ." if refresh_status == "incompatible" else
            "Chưa đủ dữ liệu để xác nhận tần số này ở độ phân giải đang xét." if request.RefreshHz else "Bạn chưa yêu cầu tần số quét cụ thể.",
            evidence, requested=request.RefreshHz is not None),
        _criterion("signal_mode", "Chế độ tín hiệu trên toàn bộ đường truyền", status, summary, evidence, missing),
    ]
    return criteria, status, conditions, missing, mode_path, notes


def check_compatibility(source: VideoProfile, target: VideoProfile | None, request: VideoRequest):
    """Check laptop -> monitor (or only a laptop's explicitly requested video output capability)."""
    limitations = ["Kết quả dựa trên thông số đã ghi, không phải kết quả cắm thử thiết bị.",
                   "Phiên bản cổng, GPU và tần số quét quảng cáo của màn hình không tự chứng minh chế độ xuất hình."]
    if target is None:
        outputs = _video_ports(source, "output", request.SourceConnector)
        status = "compatible" if outputs else "incompatible" if _known_absent(source, "output", request.SourceConnector) else "unknown"
        stated = [p for p in outputs if not p.inferred]
        summary = ("Thông số xác nhận cổng laptop có chức năng xuất hình, cần chọn màn hình để kiểm tra cả đường truyền." if stated else
                   "Laptop có cổng video trong danh sách cổng, được hiểu là cổng xuất hình theo loại thiết bị, cần chọn màn hình để kiểm tra cả đường truyền." if outputs else
                   "Danh sách cổng đầy đủ xác nhận không có đầu ra video phù hợp trong điều kiện này." if status == "incompatible" else
                   "Chưa đủ dữ liệu để xác nhận cổng laptop hỗ trợ xuất hình.")
        if outputs and not stated:
            limitations.append(INFERRED_NOTE)
        missing = ["Thiết bị màn hình và các chế độ đầu vào nếu cần kiểm tra kết nối hoàn chỉnh"]
        if not outputs:
            missing.insert(0, "Chiều đầu ra video và khả năng xuất hình của cổng laptop")
        criteria = [_criterion("connection", "Khả năng xuất hình của laptop", status, summary, source.facts, missing)]
        if request.Width is not None or request.RefreshHz is not None:
            mode_criteria, _, _, mode_missing, _, _ = _mode_check([], source, VideoProfile(), request)
            criteria.extend(mode_criteria)
            missing += mode_missing
            if status != "incompatible":
                status = "unknown"  # A video-capable port alone cannot establish the requested display mode.
        return CompatibilityResult(status, criteria, [], _unique(missing), limitations)
    paths = _paths(source, target, request)
    if paths:
        # A path with both directions stated wins over one whose direction is only taken from the device type.
        path = next((p for p in paths if not p.inferred and p.adapter is None), None) or next(
            (p for p in paths if p.adapter is None), None) or next((p for p in paths if not p.inferred), paths[0])
        basic = "requires_adapter" if path.adapter else "compatible"
        if path.adapter:
            summary = "Có đường kết nối video có căn cứ qua cáp/bộ chuyển đổi đúng chiều."
        elif path.inferred:
            summary = (f"Laptop có cổng {CONNECTORS[path.source.connector]} và màn hình có cổng nhận phù hợp trong danh sách "
                       "cổng, có thể kết nối cơ bản với cáp phù hợp (chiều tín hiệu suy theo loại thiết bị).")
        else:
            summary = (f"Có đầu ra {CONNECTORS[path.source.connector]} và đầu vào phù hợp đã xác minh, có thể kết nối cơ bản "
                       "với cáp phù hợp.")
        if path.inferred:
            summary = summary.replace("có căn cứ qua", "theo danh sách cổng qua")
            limitations.append(INFERRED_NOTE)
        evidence, missing = [path.source.evidence, path.target.evidence], []
        conditions = [path.cable_label()]
    else:
        absent = _known_absent(source, "output", request.SourceConnector) or _known_absent(target, "input")
        direct_miss = request.DirectOnly and source.outputs_complete and target.inputs_complete and _unambiguous(source, "output") and _unambiguous(target, "input")
        basic = "incompatible" if absent or direct_miss else "unknown"
        summary = ("Dữ liệu đầy đủ xác nhận không có đường xuất/nhận video phù hợp trong điều kiện đang xét." if absent else
                   "Không có cặp cổng video phù hợp để kết nối trực tiếp trong danh sách đầy đủ, kết luận này chỉ áp dụng khi không dùng adapter." if direct_miss else
                   "Chưa đủ dữ liệu để xác nhận kết nối giữa hai thiết bị, không suy ra từ hình dạng đầu cắm.")
        evidence = [*source.facts[:4], *target.facts[:4]]
        missing = [] if basic == "incompatible" else ["Laptop: đầu ra video và màn hình: đầu vào video có chiều, chức năng được xác nhận",
                                                     "Đường chuyển đổi tín hiệu được xác minh nếu hai đầu khác chuẩn"]
        conditions = []
    criteria = [_criterion("connection", "Kết nối cơ bản", basic, summary, evidence, missing)]
    mode_requested = request.Width is not None or request.RefreshHz is not None
    status = basic
    if mode_requested:
        mode_criteria, mode_status, mode_conditions, mode_missing, mode_path, mode_notes = _mode_check(
            paths, source, target, request)
        criteria.extend(mode_criteria)
        conditions += mode_conditions
        missing += mode_missing
        limitations += mode_notes
        status = "incompatible" if basic == "incompatible" else mode_status
        if status == "compatible" and mode_path and mode_path.adapter:
            status = "requires_adapter"
    cable_status = ("unknown" if mode_requested and missing else "requires_adapter" if any(p.adapter for p in paths) and not any(p.adapter is None for p in paths)
                    else "compatible" if paths else "unknown")
    criteria.append(_criterion("cable", "Cáp hoặc bộ chuyển đổi", cable_status,
        " ".join(_unique(conditions, 4)) if conditions else "Chưa xác minh được loại cáp/bộ chuyển đổi phù hợp với đường truyền này.",
        [c.evidence for c in [*source.cables, *target.cables]][:6]))
    limitations += [*source.warnings, *target.warnings]
    return CompatibilityResult(status, criteria, _unique(conditions, 12), _unique(missing), _unique(limitations, 12))
