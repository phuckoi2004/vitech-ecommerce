"""Catalog/history adapter for compatibility rules; runs inside the existing short read phases."""

import json
import re
import unicodedata
import uuid

from pydantic import ValidationError

from app.core.search_text import fold
from app.schemas.ai_compatibility import CompatibilitySnapshot

from .ai_comparison import closest_products, colour_only_default
from .compatibility import INFERRED_NOTE, PUBLISHED_NOTE, check_compatibility
from .compatibility_intent import (OUT_OF_SCOPE, device_name_reply, explicit_compatibility, previous_compatibility, single_output_question,
                                   video_request)
from .compatibility_specs import normalize_video_specs

_ROLES = re.compile(r"\b(laptop|macbook|may tinh xach tay|man hinh)\b")
# Only an ordinal right after the role ('màn hình thứ hai') is typed; 'màn hình LG … với máy thứ hai' is not.
_ORDINAL = re.compile(r"\s*(?:(?:thu|so)\s+(nhat|hai|ba|bon|1|2|3|4)|dau tien)\b")
_GENERIC_ORDINAL = re.compile(r"\bmay\s+(?:(?:thu|so)\s+(nhat|hai|ba|bon|1|2|3|4)|dau tien)\b")
_RANKS = {"nhat": 1, "hai": 2, "ba": 3, "bon": 4, "1": 1, "2": 2, "3": 3, "4": 4}


def device_kind(vocab, category_id):
    category = vocab.root(str(category_id))
    name = fold(category.name) if category else ""
    return "laptop" if "laptop" in name or "may tinh xach tay" in name else "monitor" if "man hinh" in name else "unsupported"


class AiCompatibility:
    def __init__(self, catalog, context, *, clock, variant_match):
        self.catalog, self.context, self.clock, self.variant_match = catalog, context, clock, variant_match
        self.details = {}

    def _kind(self, ref, fallback=None):
        detail = self.details.get(uuid.UUID(ref["ProductId"]))
        return device_kind(self.context.vocab, detail.CategoryId) if detail else ref.get("Kind") or fallback

    def _typed_list(self, kind):
        for turn in reversed(self.context.state.turns):
            if turn.answer_intent in ("compatibility", "explain", "describe", "offers", "policy", "clarify"):
                continue
            fallback = device_kind(self.context.vocab, turn.slots.get("CategoryId"))
            refs = [dict(ref) for ref in turn.references if self._kind(ref, fallback) == kind]
            if refs:
                return refs
        return []

    def _focus(self, kind):
        return [dict(ref) for ref in self.context.state.last_focus() if self._kind(ref) == kind]

    def _clarify(self, text):
        self.context.intent.clarification = text

    def _typed(self, query):
        """The customer's own spelling of a folded query ('Màn hình LG UltraGear', not 'man hinh lg ultragear')."""
        typed = re.sub(r"\s+", " ", unicodedata.normalize("NFC", self.context.question)).strip()
        folded = fold(typed)  # Same length: fold only lowercases and removes marks once spaces are squeezed.
        start = folded.find(query)
        return typed[start:start + len(query)] if start >= 0 and len(folded) == len(typed) else query

    def _search(self, query, kind):
        roots = [c for c in self.context.vocab.categories if not c.parent_id
                 and device_kind(self.context.vocab, c.id) == kind]
        found = self.catalog.search_products(keyword=query[:100],
            category_id=uuid.UUID(roots[0].id) if len(roots) == 1 else None,
            include_descendants=True, page_size=6, sort="relevance", in_stock=False)
        matches = [p for p in found.Items if device_kind(self.context.vocab, p.CategoryId) == kind]
        exact = [p for p in matches if fold(p.Name) == query or fold(p.Slug) == query]
        if len(exact) == 1 and found.Total <= len(found.Items):
            matches = exact
        elif len(matches) > 1 and found.Total <= len(found.Items):
            # 'MacBook Air M5 13 inch 16GB 512GB' is the base model, not also the one sold with a 70W charger.
            closest = closest_products(query, matches)
            matches = closest if len(closest) == 1 else matches
        label = "laptop" if kind == "laptop" else "màn hình"
        if not matches:
            self._clarify(f"Mình chưa tìm thấy {label} “{self._typed(query)}” đang bán tại VieTech. "
                          "Bạn gửi tên/model chính xác nhé.")
        elif len(matches) > 1 or found.Total > len(found.Items):
            self._clarify(f"Có nhiều {label} khớp với “{self._typed(query)}”: " + ", ".join(p.Name for p in matches[:4])
                          + ". Bạn chọn mẫu cụ thể nhé.")
        else:
            product = matches[0]
            return {"ProductId": str(product.ProductId), "ProductName": product.Name, "Slug": product.Slug, "Kind": kind}
        return None

    def _matches(self, ref, query):
        detail = self.details.get(uuid.UUID(ref["ProductId"]))
        text = fold(f"{ref.get('ProductName', '')} {ref.get('Slug', '')} {detail.Brand.Name if detail else ''}")
        tokens = re.findall(r"[a-z0-9]+", query)
        return bool(tokens and all(re.search(r"\b" + re.escape(token) + r"\b", text) for token in tokens))

    def _resolve_role(self, kind, segment, current, *, fallback_query=None):
        label = "laptop" if kind == "laptop" else "màn hình"
        listed = self._typed_list(kind)
        if segment is not None:
            ordinal = _ORDINAL.match(segment)
            if ordinal:
                rank = _RANKS.get(ordinal[1], 1)
                if rank <= len(listed):
                    return listed[rank - 1]
                self._clarify(f"Mình chưa xác định được {label} thứ {rank}. Bạn gửi tên/model {label} muốn kiểm tra nhé.")
                return None
            owned = bool(re.search(r"\bcua (?:toi|minh)\b", segment))
            query = re.split(r"\b(?:nay|do|kia|tren|vua|da|co|khong|ket noi|dung|ho tro|xuat|can|thi|voi|va|vao|o|tai|duoc|de"
                             r"|qua|bang|noi|cam|cong|chay|choi|ra|len|sang|hien thi|su dung|adapter|bo chuyen"
                             r"|dang|ban|trong|shop|vietech)\b",
                             segment, maxsplit=1)[0].strip(" .?!,:;")
            query = re.sub(r"\b(?:4k|uhd|qhd|fhd|\d+\s*hz|\d{3,4}\s*[x×]\s*\d{3,4})(?![a-z0-9])", "", query).strip()
            if re.match(r"nao\b", query):
                # 'Laptop nào kết nối được màn hình LG?': the rules check one named pair, they do not search.
                self._clarify(f"Mình kiểm tra từng cặp laptop và màn hình cụ thể, chưa tìm được mọi {label} tương thích. "
                              f"Bạn gửi tên/model {label} cần kiểm tra nhé.")
                return None
            contextual = bool(re.search(r"\b(?:nay|do|kia|tren|vua|da so sanh)\b", segment))
            if query and not owned:
                if contextual:
                    focus = self._focus(kind)
                    matched = [ref for ref in (focus if len(focus) == 1 else listed) if self._matches(ref, query)]
                    if len(matched) == 1:
                        return matched[0]
                    if len(matched) > 1:
                        self._clarify(f"Bạn đang nhắc {label} nào: " + ", ".join(r.get("ProductName", "") for r in matched[:4]) + "?")
                        return None
                return self._search(query, kind)
            if owned:
                self._clarify(f"Bạn cho mình biết tên hoặc mã {label} để kiểm tra nhé.")
                return None
        if fallback_query:
            return self._search(fallback_query, kind)
        if current:
            return dict(current)
        focus = self._focus(kind)
        choices = focus if len(focus) == 1 else listed
        if len(choices) == 1:
            return choices[0]
        if len(choices) > 1:
            self._clarify(f"Bạn chọn {label} nào trong các mẫu vừa giới thiệu: "
                          + ", ".join(r.get("ProductName", "") for r in choices[:4]) + "?")
        else:
            self._clarify(f"Bạn gửi tên/model {label} cần kiểm tra nhé.")
        return None

    def prepare(self):
        context, intent = self.context, self.context.intent
        text = fold(context.question)
        # A new device chain must never inherit a previous laptop/monitor result.
        if OUT_OF_SCOPE.search(text):
            self._clarify("Hiện mình kiểm tra đường truyền hình ảnh giữa một laptop và một màn hình. Chưa đủ quy tắc để xác nhận điện thoại, bộ sạc hoặc đường truyền qua hub/dock. Bạn gửi cặp laptop và màn hình muốn kiểm tra trực tiếp nhé.")
            return
        role_text = re.sub(r"\blaptop\s+macbook\b", "macbook", text)
        roles = ["monitor" if m[1] == "man hinh" else "laptop" for m in _ROLES.finditer(role_text)]
        if (any(roles.count(kind) > 1 for kind in ("laptop", "monitor"))
                or re.search(r"\b(?:hai|ba|bon|nhieu|[2-9])\s+man hinh\b", text)):
            self._clarify("Mình kiểm tra từng cặp một laptop và một màn hình. Bạn chọn một cặp cụ thể trước nhé.")
            return
        text = role_text
        saved = previous_compatibility(context.state)
        only_output = single_output_question(context.question)
        # A complete new question ('Laptop A có kết nối được màn hình B không?') states its own conditions; only a
        # follow-up ('Nếu muốn 4K 144Hz thì sao?', 'Còn laptop thứ nhất?') or a pending reply keeps the earlier
        # resolution/Hz, connector and direct-only choice, which would otherwise be applied without being asked.
        inherited = None if only_output or explicit_compatibility(text) else saved.get("CompatibilityRequest")
        try:
            request = video_request(context.question, inherited)
        except (ValidationError, ValueError):
            self._clarify("Bạn gửi độ phân giải cụ thể (ví dụ 3840×2160) và tần số quét hợp lệ cần kiểm tra nhé.")
            return
        intent.compatibility_request = request.model_dump(mode="json")
        history = [ref for turn in reversed(context.state.turns) for ref in turn.references][:60]
        history += saved.get("CompatibilitySubjects", [])
        ids = list(dict.fromkeys(uuid.UUID(ref["ProductId"]) for ref in history))
        self.details = self.catalog.get_product_details(ids) if ids else {}
        subjects = {r["Kind"]: dict(r) for r in saved.get("CompatibilitySubjects", []) if r.get("Kind") in ("laptop", "monitor")}
        heads = list(_ROLES.finditer(text))
        segments = {}
        for index, match in enumerate(heads):
            kind = "monitor" if match[1] == "man hinh" else "laptop"
            end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
            # MacBook is part of a model name; laptop/màn hình are generic category labels.
            start = match.start() if match[1] == "macbook" else match.end()
            segments.setdefault(kind, text[start:end].strip())
        # Generic ordinals ('máy thứ hai') retain the existing list's meaning, also beside a named monitor ('Máy thứ
        # hai có kết nối được màn hình LG này không?'); typed ordinals use their own list.
        generic = _GENERIC_ORDINAL.search(text)
        if generic:
            rank = _RANKS.get(generic[1], 1)
            ref = next((r for r in context.state.last_list() if r.get("Rank") == rank), None)
            kind = self._kind(ref) if ref else None
            if kind not in ("laptop", "monitor"):
                self._clarify("Bạn đang nhắc thiết bị nào? Bạn gửi tên/model để mình kiểm tra đúng nhé.")
                return
            if kind not in segments:
                subjects[kind] = dict(ref)
        pending = (saved.get("PendingCompatibility") and not heads and device_name_reply(text)
                   and not re.search(r"\b(?:tuong thich|xuat hinh|ket noi)\b", text))
        version_reply = bool(re.search(r"\b(?:phien ban|ram)\b|\d+\s*[gt]b\b", text) or re.search(r"\bbản\b", context.question, re.I))
        target_kinds = ("laptop",) if only_output else ("laptop", "monitor")
        missing_kind = next((kind for kind in target_kinds if kind not in subjects), None)
        first_clarification = None
        for kind in target_kinds:
            intent.clarification = None
            fallback = text.strip(" .?!") if pending and not version_reply and kind == missing_kind else None
            ref = self._resolve_role(kind, segments.get(kind), subjects.get(kind), fallback_query=fallback)
            if ref:
                ref["Kind"] = kind
                subjects[kind] = ref
            first_clarification = first_clarification or intent.clarification
        intent.clarification = first_clarification
        intent.references = tuple(subjects[k] for k in target_kinds if k in subjects)
        if intent.clarification:
            return
        self.build()

    def build(self):
        context, intent = self.context, self.context.intent
        refs = [dict(ref) for ref in intent.references]
        self.details = self.catalog.get_product_details([uuid.UUID(r["ProductId"]) for r in refs])
        products, profiles = [], {}
        pending = next((r for r in refs if not r.get("ProductVariantId")), None)
        for index, ref in enumerate(refs, 1):
            detail = self.details.get(uuid.UUID(ref["ProductId"]))
            if detail is None:
                self._clarify("Một thiết bị không còn được hiển thị hoặc đã ngừng bán. Bạn chọn lại thiết bị để kiểm tra nhé.")
                return None
            kind = device_kind(context.vocab, detail.CategoryId)
            if kind not in ("laptop", "monitor") or kind != ref.get("Kind"):
                self._clarify("Hiện mình kiểm tra laptop với màn hình máy tính. Bạn chọn đúng hai loại thiết bị này nhé.")
                return None
            variants = [v for v in detail.Variants if v.IsActive]
            if ref.get("ProductVariantId"):
                variants = [v for v in variants if str(v.ProductVariantId) == ref["ProductVariantId"]]
            elif len(variants) > 1 and (ref is pending or fold(detail.Name) in fold(context.question)):
                matches = [v for v in variants if self.variant_match(v.VariantName, context.question)]
                if not matches:
                    matches = [v for v in variants if v.Storage and self.variant_match(v.Storage, context.question)]
                if len(matches) == 1:
                    variants = matches
            if len(variants) > 1:
                # Colours of one model share its ports unless the catalog gives a version its own video data.
                overrides = (detail.Specifications or {}).get("VideoByVariant")
                overrides = overrides if isinstance(overrides, dict) else {}
                default = colour_only_default(variants, lambda v: json.dumps(
                    overrides.get(str(v.ProductVariantId)), sort_keys=True, default=str))
                if default is not None:
                    variants = [default]
            if len(variants) != 1:
                self._clarify(f"Bạn chọn phiên bản nào của {detail.Name}? " + ", ".join(v.VariantName for v in variants[:6])
                              if variants else f"Phiên bản của {detail.Name} không còn hiển thị. Bạn chọn lại nhé.")
                intent.references = tuple(refs)
                return None
            variant = variants[0]
            ref.update(ProductVariantId=str(variant.ProductVariantId), ProductName=detail.Name, Slug=detail.Slug, Rank=index, Kind=kind)
            # The device type lets a listed HDMI/DisplayPort count as the laptop's output / the monitor's input.
            profile = normalize_video_specs(detail.Specifications, variant_id=variant.ProductVariantId, device_kind=kind)
            profiles[kind] = profile
            images = detail.VariantImages.get(variant.ProductVariantId) or detail.Images
            image = next((i for i in images if i.IsDefault), images[0] if images else None)
            products.append({"ProductId": ref["ProductId"], "ProductVariantId": ref["ProductVariantId"],
                "ProductName": detail.Name, "VariantName": variant.VariantName, "Kind": kind, "Slug": detail.Slug,
                "ImageUrl": image.ImageUrl if image else None, "InStock": variant.StockQuantity > 0, "Facts": profile.facts})
        intent.references = tuple(refs)
        if "laptop" not in profiles or len(products) not in (1, 2):
            self._clarify("Bạn chọn một laptop và một màn hình để mình kiểm tra nhé.")
            return None
        request = video_request("", intent.compatibility_request)
        result = check_compatibility(profiles["laptop"], profiles.get("monitor"), request)
        options = result.explanation_options()
        explanation = self._explanation(options)
        context.compatibility_options = options
        context.compatibility = CompatibilitySnapshot.model_validate({
            "Products": products, "CheckType": "laptop_monitor" if "monitor" in profiles else "laptop_video_output",
            "Request": request, "Status": result.status, "Criteria": result.criteria, "Conditions": result.conditions,
            "Missing": result.missing, "Limitations": result.limitations, "Explanation": explanation,
            "Basis": "device_type" if INFERRED_NOTE in result.limitations else "stated",
            "ModeBasis": "published_max" if PUBLISHED_NOTE in result.limitations else None,
            "SnapshotAt": self.clock().isoformat()}).model_dump(mode="json")
        return context.compatibility

    @staticmethod
    def _explanation(options, selected=()):
        # A model may focus/reorder the narrative, but cannot omit the uncertainty or required conditions.
        texts = {o["Id"]: o["Text"] for o in options}
        required = [key for key in ("connection", "signal_mode", "conditions", "missing") if key in texts]
        order = list(dict.fromkeys([*selected, *required]))
        return " ".join(texts[key] for key in order if key in texts)[:3000]

    def finish(self, decision, notes):
        context = self.context
        snapshot = self.build()  # Current visibility, SKU, facts and rules, rechecked after provider I/O.
        if snapshot is None:
            return context.intent.clarification, [], [], {**notes, "AnswerIntent": "clarify"}
        options = {o["Id"]: o["Text"] for o in context.compatibility_options}
        selected = list(dict.fromkeys(decision.compatibility_explanation_ids))
        if selected and all(key in options for key in selected) and not context.compatibility_fallback:
            snapshot["Explanation"] = self._explanation(context.compatibility_options, selected)
            snapshot["ExplanationSource"] = "gemini"
        elif selected:
            notes["GroundingIssues"] = ["AI chọn giải thích ngoài kết quả quy tắc đã xác minh"]
        if context.compatibility_fallback:
            snapshot["AnalysisStatus"] = "fallback"
            # Stay within the schema's 12 items, or the saved result would be dropped when history is loaded.
            snapshot["Limitations"] = [*snapshot["Limitations"][:11], "Phần diễn giải AI tạm thời chưa hoàn tất, "
                                       "bạn vẫn có thể xem kết quả kiểm tra và các điều kiện kết nối."]
        snapshot = CompatibilitySnapshot.model_validate(snapshot).model_dump(mode="json")
        notes.update(AnswerIntent="compatibility", Compatibility=snapshot,
                     AnswerSource="model" if snapshot["ExplanationSource"] == "gemini" else "backend")
        labels = {"compatible": "Có căn cứ xác nhận trong điều kiện đã nêu", "incompatible": "Không đáp ứng trong điều kiện đang xét",
                  "requires_adapter": "Cần cáp hoặc bộ chuyển đổi phù hợp", "unknown": "Chưa đủ dữ liệu để xác nhận"}
        if snapshot["Basis"] == "device_type":  # Never reads as a direction the manufacturer stated.
            inferred = "chiều xuất/nhận hình suy theo loại thiết bị"
            labels = {**labels, "compatible": f"Có thể kết nối cơ bản ({inferred})",
                      "requires_adapter": f"Cần cáp hoặc bộ chuyển đổi phù hợp ({inferred})"}
        # A mode checked against each port's published maximum (R4b) says so, with the cable it still needs.
        mode_labels = labels
        if snapshot["ModeBasis"] == "published_max":
            tail = " (chiều xuất/nhận hình suy theo loại thiết bị)" if snapshot["Basis"] == "device_type" else ""
            mode_labels = {**labels, "compatible": f"Chạy được theo mức tối đa hãng công bố, cần cáp đạt chuẩn{tail}",
                           "requires_adapter": f"Cần cáp hoặc bộ chuyển đổi đạt chuẩn, chế độ nằm trong mức tối đa hãng "
                                               f"công bố{tail}"}
        names = " và ".join(p["ProductName"] for p in snapshot["Products"])
        text = f"Kiểm tra {names}: {mode_labels[snapshot['Status']]}."
        criteria = {c["Id"]: c for c in snapshot["Criteria"]}
        basic, mode = criteria.get("connection"), criteria.get("signal_mode")
        if basic and mode and basic["Status"] != mode["Status"]:
            # 'Connects via HDMI, 4K 144Hz unconfirmed' must not read as a single 'unknown' for both questions.
            text += f" {basic['Label']}: {labels[basic['Status']]}, {mode['Label'].lower()}: {mode_labels[mode['Status']]}."
        return f"{text} Xem các tiêu chí và điều kiện bên dưới.", [], list(context.intent.references), notes
