"""Comparison facts and analysis. No provider data, writes or alternative ranking engine."""

import re
from decimal import Decimal

from app.core.search_text import fold
from app.schemas.ai_comparison import ComparisonSnapshot

from .recommendation import Candidate, NEEDS, RankingCriteria, assess, evaluate
from .ai_comparison_details import comparison_details, format_spec, narrative_ram, product_insights, split_processor

MISSING = "Chưa có dữ liệu"
# First alias is the key understood by the existing recommendation engine.
SPEC_GROUPS = (
    ("cpu", "CPU", ("Loại CPU", "CPU", "Chip xử lý", "Chipset", "Processor", "Bộ xử lý")),
    ("ram", "RAM", ("Dung lượng RAM", "RAM", "Memory RAM")),
    ("ram_slots", "Khe RAM", ("Số khe ram", "Khe RAM")),
    ("storage", "Bộ nhớ / SSD", ("Ổ cứng", "SSD", "Bộ nhớ trong", "Bộ nhớ", "ROM", "Storage", "Dung lượng lưu trữ")),
    ("gpu", "GPU", ("Loại card đồ họa", "Card đồ họa", "GPU", "VGA", "Graphics")),
    ("imaging", "Bộ xử lý hình ảnh", ("Bộ xử lý hình ảnh", "Imaging NPU")),
    ("screen", "Màn hình", ("Màn hình", "Kích thước màn hình", "Công nghệ màn hình", "Độ phân giải màn hình", "Display")),
    ("refresh", "Tần số quét", ("Tần số quét", "Tính năng màn hình", "Refresh rate")),
    ("battery", "Pin", ("Pin", "Dung lượng pin", "Battery")),
    ("charging", "Sạc", ("Công nghệ sạc", "Sạc", "Công suất sạc", "Charging")),
    ("camera", "Camera sau", ("Camera sau", "Camera", "Rear camera")),
    ("front_camera", "Camera trước", ("Camera trước", "Front camera")),
    ("weight", "Khối lượng", ("Trọng lượng", "Khối lượng", "Weight")),
    ("os", "Hệ điều hành khi ra mắt", ("Hệ điều hành khi ra mắt", "Hệ điều hành", "OS")),
    ("color", "Màu sắc", ("Màu sắc", "Màu", "Color", "Colour")),
    ("connection", "Kết nối", ("Kết nối", "Kiểu kết nối", "Connectivity", "Connection")),
    ("ports", "Cổng kết nối", ("Cổng kết nối", "Cổng sạc", "Ports")),
    ("compatibility", "Tương thích", ("Tương thích", "Compatibility")),
    ("power", "Công suất", ("Công suất", "Power")),
    ("dimensions", "Kích thước", ("Kích thước", "Dimensions")),
)
DEFAULT_KEYS = {
    "laptop": ("cpu", "ram", "storage", "gpu", "screen", "battery", "weight"),
    "phone": ("cpu", "ram", "storage", "screen", "battery", "camera", "front_camera"),
    "tablet": ("cpu", "ram", "storage", "screen", "battery", "camera"),
}


def normalized_specs(source, variant, kind, *, description=None):
    """Flatten nested public specs and overlay the selected SKU's explicit memory/color only.

    Combined '8GB / 256GB' and labelled 'RAM 8GB, SSD 256GB' describe memory explicitly.
    An unlabelled single capacity is storage. Never infer CPU/GPU from a variant name.
    """
    leaves = {}

    def collect(data, depth=0):
        if not isinstance(data, dict) or depth > 3:
            return
        for key, value in list(data.items())[:100]:
            if str(key).startswith('_'):
                continue
            if isinstance(value, dict):
                collect(value, depth + 1)
            elif isinstance(value, (str, int, float)) and not isinstance(value, bool) and str(value).strip():
                label = re.sub(r"\s*\([^)]*\)", "", fold(str(key))).strip()
                limit = 800 if label in {'camera sau', 'camera truoc', 'rear camera', 'front camera', 'camera'} else 200
                leaves.setdefault(label, str(value).strip()[:limit])
            elif isinstance(value, list):
                text = ", ".join(str(v) for v in value[:8] if isinstance(v, (str, int, float)))
                if text:
                    leaves.setdefault(fold(str(key)).strip(), text[:200])
    collect(source)
    specs = {}
    for key, _, aliases in SPEC_GROUPS:
        values = list(dict.fromkeys(leaves[fold(alias)] for alias in aliases if fold(alias) in leaves))
        if key == "refresh":
            # 'Tính năng màn hình' lists Dynamic Island, HDR, ppi…: only a stated Hz value is a refresh rate.
            values = list(dict.fromkeys(re.sub(r"\s*hz$", " Hz", hz, flags=re.I) for value in values
                                        for hz in re.findall(r"\b\d{2,3}\s*hz\b", value, flags=re.I)))
        if values:
            specs[key] = " · ".join(values)[:800 if key in ('camera', 'front_camera') else 400]
    split_processor(specs)
    if 'ram' not in specs and (ram := narrative_ram(description)):
        specs['ram'] = ram
    storage = (variant.Storage or "").strip()
    # Read the name as well as Storage: Storage='256GB', VariantName='8GB / 256GB' must not keep common RAM=16GB.
    for text in (fold(variant.VariantName), fold(storage)):
        ram = re.search(r"(?:\bram\s*[:=]?\s*(\d+\s*gb)\b|\b(\d+\s*gb)\s*ram\b)", text)
        disk = re.search(r"(?:\b(?:ssd|rom|storage)\s*[:=]?\s*(\d+\s*[gt]b)\b|\b(\d+\s*[gt]b)\s*(?:ssd|rom)\b)", text)
        combined = re.search(r"\b(\d+\s*gb)\s*(?:[/+]\s*|\s+)(\d+\s*[gt]b)\b", text)
        if combined:
            specs["ram"], specs["storage"] = combined[1].upper(), combined[2].upper()
        else:
            if ram:
                specs["ram"] = (ram[1] or ram[2]).upper()
            if disk:
                specs["storage"] = (disk[1] or disk[2]).upper()
    if storage and re.fullmatch(r"\d+(?:[.,]\d+)?\s*[gt]b", fold(storage)):
        specs["storage"] = storage[:200]
    if variant.Color:
        specs["color"] = variant.Color
    # Shared memory specs can describe a different SKU. Without a per-SKU value, omit conflicting capacities.
    for key in ("ram", "storage"):
        if key in specs and re.search(r"\d+\s*[gt]b\s*(?:/|hoac|or)\s*\d+", fold(specs[key])):
            specs.pop(key)
    return specs


# Words that start another model line right after a typed name: "iPhone 17 Pro" is not "iPhone 17 Pro Max".
MODEL_LINE_WORDS = frozenset({"pro", "max", "plus", "ultra", "mini", "lite", "air", "fe", "neo", "prime", "edge",
                              "fold", "flip", "se", "xl", "slim"})


def _name_words(text):
    return re.findall(r"[a-z0-9]+", re.sub(r"(\d)\s+(gb|tb)\b", r"\1\2", fold(text)))


def closest_products(query, products):
    """The products a typed name means when a search returns several: every typed word is in the name, no
    model-line word follows a typed word, and of names that only add words to another candidate (an accessory
    such as "Sạc 70W"), the shorter one. Several left means the customer must choose."""
    typed = _name_words(query)
    kept = []
    for product in products:
        words = _name_words(product.Name)
        following = {words[i + 1] for i, word in enumerate(words[:-1]) if word in typed}
        if typed and set(typed) <= set(words) and not (following & MODEL_LINE_WORDS) - set(typed):
            kept.append((product, set(words)))
    base = [product for product, words in kept if all(words <= other for _, other in kept)]
    return base if len(base) == 1 else [product for product, _ in kept]


def colour_only_default(variants, signature):
    """The SKU to use when the active versions differ only in colour: the same facts (`signature`), the same name
    once the colour is removed and the same price. In stock first, then by name, so the choice is stable. None when
    any version differs in something a comparison or a compatibility check reads."""
    if len(variants) < 2:
        return None

    def shape(variant):
        name = fold(variant.VariantName)
        if variant.Color:
            name = name.replace(fold(variant.Color), "")
        price = variant.SalePrice if variant.SalePrice is not None else variant.Price
        return re.sub(r"[\s·•,/-]+", " ", name).strip(), Decimal(str(price)), signature(variant)

    if not all(variant.Color for variant in variants) or len({shape(variant) for variant in variants}) != 1:
        return None
    return min(variants, key=lambda v: (v.StockQuantity <= 0, fold(v.VariantName), str(v.ProductVariantId)))


def spec_signature(source, kind):
    """What normalized_specs reads from a SKU, colour excluded: equal signatures compare the same."""
    def signature(variant):
        specs = normalized_specs(source, variant, kind)
        return tuple(sorted((key, re.sub(r"\s+", "", fold(value))) for key, value in specs.items() if key != "color"))
    return signature


def ranking_specs(specs, kind):
    result = {aliases[0]: specs[key] for key, _, aliases in SPEC_GROUPS if key in specs}
    if "storage" in specs:
        result["Ổ cứng" if kind == "laptop" else "Bộ nhớ trong"] = specs["storage"]
    if "screen" in specs:
        result["Kích thước màn hình"] = specs["screen"]
    return result


def _money(value):
    return f"{int(Decimal(value)):,}".replace(",", ".") + " đ"


def _chip_generation_answer(question, products, specs):
    """Compare explicit generations within Apple's M family, never infer performance from a model number."""
    text = fold(question)
    if not re.search(r"\b(?:chip|cpu|bo xu ly)\b.*\b(?:moi hon|the he moi|doi moi)\b", text):
        return None
    chips = [set(re.findall(r"\bapple\s+m(\d+)\b", fold(s.get("cpu", "")))) for s in specs]
    if not all(len(chip) == 1 for chip in chips):
        return "Chưa có đủ thông tin về thế hệ chip để xác định mẫu nào dùng chip mới hơn."
    generations = [int(next(iter(chip))) for chip in chips]
    newest = max(generations)
    if len(set(generations)) == 1:
        return f"Các mẫu đều dùng chip thuộc thế hệ Apple M{newest}, chưa có mẫu thuộc thế hệ M mới hơn trong bảng này."
    names = ", ".join(p["ProductName"] for p, generation in zip(products, generations) if generation == newest)
    older = ", ".join(f"M{g}" for g in sorted(set(generations) - {newest}))
    return (f"{names} dùng Apple M{newest}, thuộc thế hệ chip mới hơn {older}. "
            "Thế hệ mới hơn không tự xác định máy phù hợp hơn với mọi nhu cầu hoặc nhanh hơn trong mọi tác vụ.")


def _ahead(rows, others):
    """Evidence of the criteria where `rows` score higher than every row set in `others`, most important first.
    A shared fact ("RAM 16 GB" on both) is never a reason to prefer one product."""
    best = {}
    for other in others:
        for id_, _, result in other:
            best[id_] = max(best.get(id_, 0.0), result.score)
    ahead = {}
    for id_, weight, result in rows:
        if result.evidence and result.score > best.get(id_, 0.0):
            ahead[result.evidence] = max(weight, ahead.get(result.evidence, 0.0))
    return [evidence for evidence, _ in sorted(ahead.items(), key=lambda item: -item[1])]


def build_comparison(items, context, snapshot_at):
    """items are (public detail, exact active variant); never reorders the customer's columns."""
    criteria = RankingCriteria(context.intent.needs, context.intent.soft_brands())
    budget = context.intent.max_budget
    products, all_specs, kinds, analysis = [], [], [], []
    for detail, variant in items:
        kind = context.vocab.kind(str(detail.CategoryId))
        kinds.append(kind)
        specs = normalized_specs(detail.Specifications, variant, kind, description=getattr(detail, 'Description', None))
        all_specs.append(specs)
        price = variant.SalePrice if variant.SalePrice is not None else variant.Price
        candidate = Candidate(str(variant.ProductVariantId), str(detail.BrandId), detail.Name, detail.Category.Name,
                              kind, ranking_specs(specs, kind), price)
        # Keep every missing criterion visible, including ones missing from all compared products.
        assessed = assess(criteria, candidate)
        evaluation = evaluate(criteria, candidate, budget_max=budget, rows=assessed)
        analysis.append((assessed, evaluation))
        images = detail.VariantImages.get(variant.ProductVariantId) or detail.Images
        image = next((i for i in images if i.IsDefault), images[0] if images else None)
        products.append({"ProductId": str(detail.ProductId), "ProductVariantId": str(variant.ProductVariantId),
                         "ProductName": detail.Name, "VariantName": variant.VariantName,
                         "Brand": detail.Brand.Name, "Category": detail.Category.Name, "Slug": detail.Slug,
                         "ImageUrl": image.ImageUrl if image else None, "Price": str(price),
                         "InStock": variant.StockQuantity > 0,
                         "Score": round(evaluation.score, 4) if evaluation.score is not None else None,
                         "Completeness": evaluation.completeness, "Strengths": product_insights(specs, kind) or evaluation.matched[:8],
                         "Limitations": evaluation.gaps[:12]})
    keys = set().union(*(DEFAULT_KEYS.get(kind, ()) for kind in kinds), *all_specs)
    show_color = bool(re.search(r'\bmàu\b', context.question, re.I) or re.search(r'\b(?:mau sac|colou?r)\b', fold(context.question)))
    if re.search(r'\b(?:khong (?:can|muon|so sanh|quan tam|hien thi|xet)|bo qua)(?:\s+\w+){0,4}\s+mau\b', fold(context.question)):
        show_color = False
    if not show_color:
        keys.discard('color')
    rows = [{"Key": key, "Label": label, "Values": [format_spec(key, specs.get(key, MISSING)) for specs in all_specs]}
            for key, label, _ in SPEC_GROUPS if key in keys]
    recommendation = ""
    winner = None
    comparable = len(set(kinds)) == 1 and kinds[0] is not None
    differences, usage_options = comparison_details(products, all_specs, rows, comparable)
    eligible = [p for p in products if p["Score"] is not None and p["Completeness"] >= .7 and p["InStock"]]
    eligible.sort(key=lambda p: (-p["Score"], -p["Completeness"]))
    if context.intent.needs and comparable and len(eligible) == len(products):
        recommendation = "Các mẫu có mức phù hợp gần nhau theo dữ liệu hiện có, chưa đủ căn cứ chọn một mẫu vượt trội."
        if eligible[0]["Score"] - eligible[1]["Score"] >= .02:
            best = products.index(eligible[0])
            others = [i for i in range(len(products)) if i != best]
            best_rows, evaluation = analysis[best]
            # The reasons are what decided the score: criteria this product leads on, a lower price in the budget
            # and the preferred brand. Each other product's leads are stated too, so the advice stays checkable.
            reasons = _ahead(best_rows, [analysis[i][0] for i in others])[:3]
            if all(evaluation.parts.get("B", 0) > analysis[i][1].parts.get("B", 0) for i in others):
                within = budget and Decimal(products[best]["Price"]) <= Decimal(budget)
                reasons.append("giá thấp hơn" + (f", trong ngân sách {_money(budget)}" if within else ""))
            if evaluation.soft_brand and not any(analysis[i][1].soft_brand for i in others):
                reasons.append("đúng hãng bạn ưu tiên")
            if reasons:
                winner = products[best]["ProductVariantId"]
                lines = [f"{products[best]['ProductName']} ({products[best]['VariantName']}) phù hợp hơn theo tiêu chí "
                         f"của VieTech nhờ: {', '.join(reasons)}."]
                for i in others:
                    leads = _ahead(analysis[i][0], [best_rows])[:3]
                    if leads:
                        lines.append(f"{products[i]['ProductName']} mạnh hơn về: {', '.join(leads)}.")
                recommendation = " ".join(lines)
    if usage_options:
        recommendation = recommendation + '\n' + usage_options if winner else usage_options
    generation_answer = _chip_generation_answer(context.question, products, all_specs)
    if generation_answer:
        recommendation, winner = generation_answer, None
    # Missing specifications already appear in the table and each product's limitations. Add a note only
    # when the customer explicitly asks for a result the published configuration cannot establish.
    caveats = []
    question = fold(context.question)
    software = re.search(r"\b(?:Android Studio|AutoCAD|SolidWorks|Premiere Pro|Photoshop)\b", context.question, re.I)
    if software:
        caveats.append(f"Chưa có kết quả chạy thử {software[0]} trên các mẫu này để xác nhận mức đáp ứng bạn hỏi.")
    elif re.search(r"\b(?:chay muot|fps|benchmark|do hieu nang)\b", question):
        caveats.append("Chưa có kết quả chạy thử để xác nhận hiệu năng thực tế bạn hỏi.")
    if re.search(r"\b(?:pin|sac)\b.*\b(?:bao lau|may gio|bao nhieu gio)\b|\bthoi luong pin\b", question):
        caveats.append("Chưa có kết quả đo thời lượng pin với cách sử dụng bạn hỏi.")
    if re.search(r"\b(?:chup (?:anh )?dep|chat luong anh|anh chup thuc te)\b", question):
        caveats.append("Chưa có ảnh chụp thử để so sánh chất lượng ảnh giữa các mẫu này.")
    if not comparable:
        caveats.append("Các sản phẩm khác loại hoặc chưa xác định nhóm, không xếp hạng chung.")
    return ComparisonSnapshot.model_validate({"Products": products, "Rows": rows,
        "Needs": [NEEDS[n].label for n in context.intent.needs] + (["màu sắc"] if show_color else []), "Differences": differences,
        "Recommendation": recommendation, "RecommendedProductVariantId": winner,
        "Caveats": caveats, "SnapshotAt": snapshot_at}).model_dump(mode="json")
