"""Tiêu chí lọc của trang danh mục khách hàng (docs/customer-category-listing.md).

Products.Specifications là văn bản tự do, mỗi danh mục một bộ khóa ("Chipset", "Dung lượng RAM", "Tần số quét"...).
Vì vậy mỗi lựa chọn là một quy tắc khớp chữ hoặc số trên thông số, tên sản phẩm và dung lượng của biến thể đang bán.
Bộ tiêu chí chọn theo slug của danh mục gốc; danh mục con dùng bộ của danh mục gốc. Cùng một tiêu chí, các lựa chọn
được OR; giữa các tiêu chí là AND. API ẩn lựa chọn không khớp sản phẩm nào, nên quy tắc cho dữ liệu chưa có không
làm khách thấy bộ lọc rỗng.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal


def _clean(value) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(value))).strip().lower()


@dataclass(frozen=True)
class ProductFacts:
    """What a rule may read: the name, specifications (keys and values lowercased) and visible variants' storage."""

    name: str
    specs: dict[str, str]
    storages: tuple[str, ...] = ()

    @classmethod
    def of(cls, name: str, specifications, storages: Iterable[str | None] = ()) -> ProductFacts:
        specs = {}
        if isinstance(specifications, dict):
            for key, value in specifications.items():
                if value not in (None, ""):
                    specs[_clean(key)] = _clean("; ".join(map(str, value)) if isinstance(value, list) else value)
        return cls(_clean(name), specs, tuple(_clean(item) for item in storages if item))

    def text(self, keys: tuple[str, ...] = (), *, name: bool = False) -> str:
        """Values of `keys` (lowercase names), plus the product name when asked; no keys reads everything."""
        if not keys:
            return " ; ".join([self.name, *self.specs.values()])
        values = [self.specs[key] for key in keys if key in self.specs]
        return " ; ".join([self.name, *values] if name else values)


Rule = Callable[[ProductFacts], bool]


@dataclass(frozen=True)
class FacetOption:
    value: str
    label: str
    matches: Rule


@dataclass(frozen=True)
class Facet:
    key: str
    label: str
    options: tuple[FacetOption, ...]

    def option(self, value: str) -> FacetOption | None:
        return next((option for option in self.options if option.value == value), None)


@dataclass(frozen=True)
class PriceRange:
    value: str
    label: str
    min_price: Decimal | None
    max_price: Decimal | None


@dataclass(frozen=True)
class FacetGroup:
    facets: tuple[Facet, ...]
    price_ranges: tuple[PriceRange, ...]

    def facet(self, key: str) -> Facet | None:
        return next((facet for facet in self.facets if facet.key == key), None)


# ------------------------------------------------------------------ rule helpers

# "10.000 mAh" / "1,000 DPI" are thousands; "22.5 W" / "6,7 inch" are decimals.
_NUMBER = r"(\d{1,3}(?:[.,]\d{3})+(?!\d)|\d+(?:[.,]\d+)?)"


def _number(text: str) -> float:
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", text):
        return float(re.sub(r"[.,]", "", text))
    return float(text.replace(",", "."))


def _amounts(text: str, unit: str) -> list[float]:
    return [_number(match) for match in re.findall(_NUMBER + r"\s*(?:" + unit + r")(?![a-z])", text)]


def _sizes(text: str) -> list[float]:
    """Memory sizes in GB ("1 TB" is 1024 GB), in the order written."""
    return [_number(number) * (1024 if unit == "tb" else 1)
            for number, unit in re.findall(_NUMBER + r"\s*(gb|tb)(?![a-z])", text)]


def has(pattern: str, *keys: str, name: bool = False) -> Rule:
    """The pattern occurs in those specification values (and the name); no keys searches everything."""
    regex = re.compile(pattern)
    return lambda facts: bool(regex.search(facts.text(keys, name=name)))


def lacks(pattern: str, *keys: str) -> Rule:
    """The specification is filled in and the pattern does not occur in it."""
    regex = re.compile(pattern)

    def rule(facts: ProductFacts) -> bool:
        text = facts.text(keys)
        return bool(text) and not regex.search(text)
    return rule


def named(pattern: str) -> Rule:
    regex = re.compile(pattern)
    return lambda facts: bool(regex.search(facts.name))


def every(*rules: Rule) -> Rule:
    return lambda facts: all(rule(facts) for rule in rules)


def any_of(*rules: Rule) -> Rule:
    return lambda facts: any(rule(facts) for rule in rules)


def but_not(pattern: str, *keys: str, name: bool = False) -> Rule:
    regex = re.compile(pattern)
    return lambda facts: not regex.search(facts.text(keys, name=name))


def between(read: Callable[[ProductFacts], Iterable[float]], low: float | None = None, high: float | None = None) -> Rule:
    """Some value read from the product lies in [low, high]."""
    return lambda facts: any((low is None or value >= low) and (high is None or value <= high) for value in read(facts))


def first_size(*keys: str) -> Callable[[ProductFacts], list[float]]:
    return lambda facts: _sizes(facts.text(keys))[:1]


def storage_sizes(*keys: str) -> Callable[[ProductFacts], list[float]]:
    """The storage of each visible variant, or the specification when variants do not say."""
    def read(facts: ProductFacts) -> list[float]:
        sizes = [size for storage in facts.storages for size in _sizes(storage)[:1]]
        return sizes or _sizes(facts.text(keys))[:1]
    return read


def largest(unit: str, *keys: str, name: bool = False) -> Callable[[ProductFacts], list[float]]:
    def read(facts: ProductFacts) -> list[float]:
        values = _amounts(facts.text(keys, name=name), unit)
        return [max(values)] if values else []
    return read


def screen_inches(*keys: str) -> Callable[[ProductFacts], list[float]]:
    """The first screen size in the specifications, else in the name ("Màn hình Dell 27 inch")."""
    def read(facts: ProductFacts) -> list[float]:
        values = _amounts(facts.text(keys), r"inch(?:es)?|\"|″|''") or _amounts(facts.name, r"inch(?:es)?|\"|″|''")
        return values[:1]
    return read


def refresh_rate(*keys: str) -> Callable[[ProductFacts], list[float]]:
    """The highest display refresh rate; touch sampling and PWM figures ("Cảm ứng 240Hz") are not refresh rates."""
    def read(facts: ProductFacts) -> list[float]:
        values = []
        for part in re.split(r"[;,\n]", facts.text(keys, name=True)):
            if not re.search(r"cảm ứng|touch|lấy mẫu|pwm|dimming", part):
                values += [value for value in _amounts(part, "hz") if 24 <= value <= 500]
        return [max(values)] if values else []
    return read


def option(value: str, label: str, rule: Rule) -> FacetOption:
    return FacetOption(value, label, rule)


def facet(key: str, label: str, *options: FacetOption) -> Facet:
    return Facet(key, label, options)


_MILLION = Decimal(1_000_000)
_CENT = Decimal("0.01")


def price(value: str, label: str, low: str | None, high: str | None) -> PriceRange:
    """`low`/`high` in millions of VND; the upper bound stops one cent before the next range starts."""
    return PriceRange(value, label, Decimal(low) * _MILLION if low else None,
                      Decimal(high) * _MILLION - _CENT if high else None)


# ------------------------------------------------------------------ shared criteria

_IOS = r"\bios\b|ipados"
_ANDROID = r"android|hyperos|coloros|magicos|one ?ui|flyme|myos|funtouch|originos|realme ui|harmonyos"
_PHONE_CHIP = ("chipset", "chip xử lý", "loại cpu", "cpu")
_SCREEN = ("tần số quét", "tính năng màn hình", "công nghệ màn hình", "màn hình")
_WATERPROOF = r"\bipx?[4-8]\d?\b|kháng nước|chống nước"

PHONE_RAM = facet("ram", "Dung lượng RAM",
                  option("under-3gb", "Dưới 3 GB", between(first_size("dung lượng ram", "ram"), high=3)),
                  option("4gb", "4 GB", between(first_size("dung lượng ram", "ram"), 4, 4)),
                  option("6gb", "6 GB", between(first_size("dung lượng ram", "ram"), 6, 6)),
                  option("8gb", "8 GB", between(first_size("dung lượng ram", "ram"), 8, 8)),
                  option("12gb", "12 GB", between(first_size("dung lượng ram", "ram"), 12, 12)),
                  option("16gb", "16 GB", between(first_size("dung lượng ram", "ram"), 16, 16)),
                  option("from-12gb", "12 GB trở lên", between(first_size("dung lượng ram", "ram"), low=12)))

PHONE_STORAGE = facet("storage", "Bộ nhớ trong",
                      *(option(value, label, between(storage_sizes("bộ nhớ trong"), low, high)) for value, label, low, high in (
                          ("under-64gb", "Dưới 64 GB", None, 63), ("64gb", "64 GB", 64, 64), ("128gb", "128 GB", 128, 128),
                          ("256gb", "256 GB", 256, 256), ("512gb", "512 GB", 512, 512), ("1tb", "1 TB", 1024, 1024),
                          ("2tb", "2 TB", 2048, 2048))))

ACCESSORY_PRICES = (
    price("under-500k", "Dưới 500 nghìn", None, "0.5"), price("500k-1", "500 nghìn – 1 triệu", "0.5", "1"),
    price("1-2", "1 – 2 triệu", "1", "2"), price("2-5", "2 – 5 triệu", "2", "5"), price("from-5", "Trên 5 triệu", "5", None),
)

# ------------------------------------------------------------------ groups by root category slug

PHONES = FacetGroup(
    facets=(
        facet("chip", "Chip xử lý",
              option("snapdragon", "Snapdragon", has(r"snapdragon", *_PHONE_CHIP)),
              option("apple-a", "Apple A", has(r"(?:^|[\s;(])(?:apple |chip )?a\d{2}\b", *_PHONE_CHIP)),
              option("dimensity", "MediaTek Dimensity", has(r"dimensity|mediatek d\d{4}", *_PHONE_CHIP)),
              option("helio", "MediaTek Helio", has(r"helio", *_PHONE_CHIP)),
              option("exynos", "Exynos", has(r"exynos", *_PHONE_CHIP)),
              option("unisoc", "Unisoc", has(r"unisoc|tiger t\d", *_PHONE_CHIP))),
        facet("os", "Loại điện thoại",
              option("ios", "iPhone (iOS)", has(r"iphone|" + _IOS, "hệ điều hành khi ra mắt", "hệ điều hành", name=True)),
              option("android", "Android", has(_ANDROID + r"|snapdragon|dimensity|helio|exynos|unisoc|tiger t\d",
                                               "hệ điều hành khi ra mắt", "hệ điều hành", *_PHONE_CHIP)),
              option("feature", "Điện thoại phổ thông", has(r"kaios|series 30|\bs30\+", "hệ điều hành khi ra mắt",
                                                             "hệ điều hành"))),
        PHONE_RAM,
        PHONE_STORAGE,
        facet("features", "Tính năng đặc biệt",
              option("wireless-charging", "Sạc không dây", has(r"sạc không dây|wireless charg|magsafe|\bqi\b")),
              option("fingerprint", "Bảo mật vân tay", has(r"vân tay|fingerprint")),
              option("face-unlock", "Nhận diện khuôn mặt", has(r"khuôn mặt|face ?id")),
              option("water-resistant", "Kháng nước, bụi", has(_WATERPROOF)),
              option("5g", "Hỗ trợ 5G", has(r"\b5g\b")),
              option("ai", "Điện thoại AI", has(r"galaxy ai|apple intelligence|\baios\b|gemini")),
              option("stylus", "Bút cảm ứng", has(r"s ?pen\b|bút cảm ứng"))),
        facet("camera", "Tính năng camera",
              option("portrait", "Xóa phông", has(r"xóa phông|chân dung|portrait|độ sâu|depth|bokeh", "camera sau", "camera trước", "quay phim", "tính năng camera")),
              option("wide", "Góc rộng", has(r"góc (?:siêu )?rộng|siêu rộng|ultra ?wide", "camera sau", "tính năng camera")),
              option("4k", "Video 4K", has(r"\b4k\b", "camera sau", "camera trước", "quay phim", "tính năng camera")),
              option("zoom", "Zoom xa", has(r"\btele|zoom|tiềm vọng|periscope", "camera sau", "tính năng camera")),
              option("macro", "Macro", has(r"macro", "camera sau", "tính năng camera")),
              option("stabilization", "Chống rung", has(r"\bois\b|chống rung", "camera sau", "camera trước", "quay phim", "tính năng camera")),
              option("8k", "Video 8K", has(r"\b8k\b", "camera sau", "quay phim", "tính năng camera")),
              option("ai", "Camera AI", has(r"\bai\b", "camera sau", "camera trước", "tính năng camera")),
              option("night", "Chụp đêm", has(r"chụp đêm|ban đêm|night", "camera sau", "tính năng camera"))),
        facet("refresh-rate", "Tần số quét",
              option("60hz", "60Hz", between(refresh_rate(*_SCREEN), high=60)),
              option("90hz", "90Hz", between(refresh_rate(*_SCREEN), 61, 90)),
              option("120hz", "120Hz", between(refresh_rate(*_SCREEN), 91, 120)),
              option("from-144hz", "144Hz trở lên", between(refresh_rate(*_SCREEN), low=144))),
        facet("screen", "Kiểu màn hình",
              option("notch", "Tai thỏ", has(r"tai thỏ|notch")),
              option("edge-to-edge", "Tràn viền", has(r"tràn viền|vô cực|infinity")),
              option("foldable", "Màn hình gập", has(r"màn hình phụ|\bz ?fold|\bz ?flip|find n\d|gập")),
              option("waterdrop", "Giọt nước", has(r"giọt nước|water ?drop")),
              option("punch-hole", "Đục lỗ", has(r"đục lỗ|punch")),
              option("dynamic-island", "Dynamic Island", has(r"dynamic island"))),
        facet("nfc", "Công nghệ NFC",
              option("yes", "Có NFC", any_of(has(r"^(?!không)\S", "công nghệ nfc", "nfc"), named(r"\bnfc\b"))),
              option("no", "Không NFC", has(r"^không", "công nghệ nfc", "nfc"))),
        facet("network", "Hỗ trợ mạng",
              option("4g", "4G", every(has(r"\b4g\b", "hỗ trợ mạng", "mạng di động", name=True),
                                       but_not(r"\b5g\b", "hỗ trợ mạng", "mạng di động", name=True))),
              option("5g", "5G", has(r"\b5g\b", "hỗ trợ mạng", "mạng di động", name=True))),
    ),
    price_ranges=(
        price("under-2", "Dưới 2 triệu", None, "2"), price("2-4", "2 – 4 triệu", "2", "4"),
        price("4-7", "4 – 7 triệu", "4", "7"), price("7-13", "7 – 13 triệu", "7", "13"),
        price("13-20", "13 – 20 triệu", "13", "20"), price("from-20", "Trên 20 triệu", "20", None),
    ),
)

_DEDICATED_GPU = r"rtx|geforce|radeon rx|quadro|\barc a\d"

LAPTOPS = FacetGroup(
    facets=(
        facet("cpu", "Chip xử lý",
              option("core-ultra", "Intel Core Ultra", has(r"core ultra", "loại cpu", "cpu", name=True)),
              option("core-i", "Intel Core i3/i5/i7/i9", has(r"core i[3579]\b", "loại cpu", "cpu", name=True)),
              option("core", "Intel Core 3/5/7", has(r"intel core [3579] \d{3}", "loại cpu", "cpu", name=True)),
              option("ryzen", "AMD Ryzen", has(r"ryzen", "loại cpu", "cpu", name=True)),
              option("apple-m", "Apple M", has(r"(?:apple|chip) m\d|macbook.* m\d", "loại cpu", "cpu", name=True)),
              option("snapdragon", "Snapdragon X", has(r"snapdragon", "loại cpu", "cpu", name=True))),
        facet("ram", "Dung lượng RAM",
              option("under-8gb", "Dưới 8 GB", between(first_size("dung lượng ram", "ram"), high=7)),
              option("8gb", "8 GB", between(first_size("dung lượng ram", "ram"), 8, 8)),
              option("16gb", "16 GB", between(first_size("dung lượng ram", "ram"), 16, 16)),
              option("24gb", "24 GB", between(first_size("dung lượng ram", "ram"), 24, 24)),
              option("from-32gb", "32 GB trở lên", between(first_size("dung lượng ram", "ram"), low=32))),
        facet("storage", "Ổ cứng",
              option("256gb", "256 GB", between(first_size("ổ cứng", "bộ nhớ trong"), high=256)),
              option("512gb", "512 GB", between(first_size("ổ cứng", "bộ nhớ trong"), 512, 512)),
              option("from-1tb", "1 TB trở lên", between(first_size("ổ cứng", "bộ nhớ trong"), low=1024))),
        facet("gpu", "Card đồ họa",
              option("dedicated", "Card rời", has(_DEDICATED_GPU, "loại card đồ họa", "card đồ họa")),
              option("integrated", "Card tích hợp", lacks(_DEDICATED_GPU, "loại card đồ họa", "card đồ họa"))),
        facet("screen-size", "Kích thước màn hình",
              option("13", "13 – 13.9 inch", between(screen_inches("kích thước màn hình"), 13, 13.95)),
              option("14", "14 inch", between(screen_inches("kích thước màn hình"), 14, 14.95)),
              option("15", "15 – 15.9 inch", between(screen_inches("kích thước màn hình"), 15, 15.95)),
              option("from-16", "16 inch trở lên", between(screen_inches("kích thước màn hình"), low=16))),
        # An NVIDIA card's "AI TOPS" is not an NPU; Apple's Neural Engine is.
        facet("ai", "Laptop AI",
              option("npu", "Có NPU / AI", has(r"\bnpu\b|ai boost|ryzen ai|copilot|neural engine",
                                               "chip ai", "loại cpu", "cpu", "loại card đồ họa", name=True))),
    ),
    price_ranges=(
        price("under-15", "Dưới 15 triệu", None, "15"), price("15-20", "15 – 20 triệu", "15", "20"),
        price("20-25", "20 – 25 triệu", "20", "25"), price("25-35", "25 – 35 triệu", "25", "35"),
        price("from-35", "Trên 35 triệu", "35", None),
    ),
)

TABLETS = FacetGroup(
    facets=(
        facet("chip", "Chip xử lý",
              option("apple-m", "Apple M", has(r"(?:apple|chip) m\d", *_PHONE_CHIP)),
              option("apple-a", "Apple A", has(r"(?:^|[\s;(])(?:apple |chip )?a\d{2}\b", *_PHONE_CHIP)),
              option("snapdragon", "Snapdragon", has(r"snapdragon", *_PHONE_CHIP)),
              option("dimensity", "MediaTek Dimensity", has(r"dimensity", *_PHONE_CHIP)),
              option("helio", "MediaTek Helio", has(r"helio", *_PHONE_CHIP)),
              option("exynos", "Exynos", has(r"exynos", *_PHONE_CHIP)),
              option("kirin", "Kirin", has(r"kirin", *_PHONE_CHIP)),
              option("unisoc", "Unisoc", has(r"unisoc|tiger t\d", *_PHONE_CHIP))),
        facet("os", "Hệ điều hành",
              option("ipados", "iPadOS", has(r"ipados|\bipad\b", "hệ điều hành khi ra mắt", "hệ điều hành", name=True)),
              option("android", "Android", has(r"android|hyperos|magicos|myos|one ?ui", "hệ điều hành khi ra mắt", "hệ điều hành")),
              option("harmonyos", "HarmonyOS", has(r"harmonyos", "hệ điều hành khi ra mắt", "hệ điều hành"))),
        facet("ram", "Dung lượng RAM",
              option("4gb", "4 GB", between(first_size("dung lượng ram", "ram"), high=4)),
              option("6gb", "6 GB", between(first_size("dung lượng ram", "ram"), 6, 6)),
              option("8gb", "8 GB", between(first_size("dung lượng ram", "ram"), 8, 8)),
              option("from-12gb", "12 GB trở lên", between(first_size("dung lượng ram", "ram"), low=12))),
        facet("storage", "Bộ nhớ trong",
              *(option(value, label, between(storage_sizes("bộ nhớ trong"), low, high)) for value, label, low, high in (
                  ("64gb", "64 GB", None, 64), ("128gb", "128 GB", 128, 128), ("256gb", "256 GB", 256, 256),
                  ("from-512gb", "512 GB trở lên", 512, None)))),
        facet("screen-size", "Kích thước màn hình",
              option("under-10", "Dưới 10 inch", between(screen_inches("kích thước màn hình"), high=9.99)),
              option("10-12", "Từ 10 đến dưới 12 inch", between(screen_inches("kích thước màn hình"), 10, 11.99)),
              option("from-12", "Từ 12 inch", between(screen_inches("kích thước màn hình"), low=12))),
        facet("network", "Kết nối mạng",
              option("cellular", "Có SIM 4G/5G", has(r"\b[45]g\b|\blte\b|cellular", "hỗ trợ mạng", "thẻ sim", name=True)),
              option("wifi", "Chỉ Wi-Fi", every(named(r"wi-?fi"),
                                                 but_not(r"\b[45]g\b|\blte\b|cellular", "hỗ trợ mạng", "thẻ sim", name=True)))),
    ),
    price_ranges=(
        price("under-5", "Dưới 5 triệu", None, "5"), price("5-10", "5 – 10 triệu", "5", "10"),
        price("10-15", "10 – 15 triệu", "10", "15"), price("15-25", "15 – 25 triệu", "15", "25"),
        price("from-25", "Trên 25 triệu", "25", None),
    ),
)

_BATTERY_HOURS = ("thời lượng sử dụng pin", "thời lượng pin", "pin")

HEADPHONES = FacetGroup(
    facets=(
        facet("noise", "Chống ồn",
              option("anc", "Chống ồn chủ động (ANC)", has(r"\banc\b|chống ồn chủ động|khử tiếng ồn|noise cancel")),
              option("enc", "Chống ồn đàm thoại (ENC)", has(r"\benc\b|chống ồn (?:cuộc gọi|đàm thoại)|micro chống ồn|micro giảm ồn"))),
        facet("battery", "Thời lượng pin",
              option("under-20h", "Dưới 20 giờ", between(largest(r"giờ|h", *_BATTERY_HOURS), high=19.9)),
              option("20-40h", "20 – 40 giờ", between(largest(r"giờ|h", *_BATTERY_HOURS), 20, 40)),
              option("from-40h", "Trên 40 giờ", between(largest(r"giờ|h", *_BATTERY_HOURS), low=40.1))),
        facet("features", "Tính năng",
              option("water-resistant", "Kháng nước", has(_WATERPROOF)),
              option("hi-res", "Hi-Res / LDAC", has(r"hi-?res|ldac")),
              option("spatial", "Âm thanh không gian", has(r"spatial|không gian|360|\b3d\b")),
              option("multipoint", "Kết nối đa điểm", has(r"đa điểm|multipoint|dual connect|auto switch")),
              option("microphone", "Có micro", has(r"^(?:có|\d)", "micro"))),
        facet("control", "Điều khiển",
              option("touch", "Cảm ứng", has(r"cảm ứng|chạm|cảm biến lực", "phương thức điều khiển")),
              option("buttons", "Nút bấm", has(r"nút|phím", "phương thức điều khiển"))),
    ),
    price_ranges=ACCESSORY_PRICES,
)

MONITORS = FacetGroup(
    facets=(
        facet("screen-size", "Kích thước",
              option("under-24", "Dưới 24 inch", between(screen_inches("kích thước màn hình"), high=23.9)),
              option("24-26", "24 – 26 inch", between(screen_inches("kích thước màn hình"), 24, 26.9)),
              option("27", "27 inch", between(screen_inches("kích thước màn hình"), 27, 27.9)),
              option("from-28", "Trên 27 inch", between(screen_inches("kích thước màn hình"), low=28))),
        facet("resolution", "Độ phân giải",
              option("fhd", "Full HD", has(r"1920\s*[x×]\s*1080|full ?hd|\bfhd\b", "độ phân giải màn hình", "độ phân giải", name=True)),
              option("qhd", "2K QHD", has(r"2560\s*[x×]\s*1440|\b2k\b|\bqhd\b", "độ phân giải màn hình", "độ phân giải", name=True)),
              option("uhd", "4K UHD", has(r"3840\s*[x×]\s*2160|\b4k\b|\buhd\b", "độ phân giải màn hình", "độ phân giải", name=True))),
        facet("refresh-rate", "Tần số quét",
              option("up-to-75hz", "60 – 75Hz", between(refresh_rate("tần số quét"), high=75)),
              option("100-120hz", "100 – 120Hz", between(refresh_rate("tần số quét"), 76, 120)),
              option("144-165hz", "144 – 165Hz", between(refresh_rate("tần số quét"), 121, 165)),
              option("from-180hz", "180Hz trở lên", between(refresh_rate("tần số quét"), low=166))),
        facet("panel", "Tấm nền",
              option("ips", "IPS", has(r"\bips\b", "tấm nền", name=True)),
              option("va", "VA", has(r"\bva\b", "tấm nền", name=True)),
              option("oled", "OLED", has(r"oled", "tấm nền", name=True)),
              option("tn", "TN", has(r"\btn\b", "tấm nền", name=True))),
        facet("response-time", "Thời gian phản hồi",
              option("up-to-1ms", "1 ms trở xuống", between(largest("ms", "thời gian phản hồi"), high=1)),
              option("over-1ms", "Trên 1 ms", between(largest("ms", "thời gian phản hồi"), low=1.01))),
    ),
    price_ranges=(
        price("under-3", "Dưới 3 triệu", None, "3"), price("3-5", "3 – 5 triệu", "3", "5"),
        price("5-10", "5 – 10 triệu", "5", "10"), price("10-20", "10 – 20 triệu", "10", "20"),
        price("from-20", "Trên 20 triệu", "20", None),
    ),
)

_KEYBOARD_CONNECTION = ("kết nối", "phương thức kết nối")
_KEYBOARD_LAYOUT = ("loại bàn phím", "kích thước/layout")


def _key_count(facts: ProductFacts) -> list[float]:
    return _amounts(facts.text(("số phím", "số lượng phím")), "phím")[:1]


KEYBOARDS = FacetGroup(
    facets=(
        facet("connection", "Kết nối",
              option("wired", "Có dây", has(r"(?<!không )dây\b|usb 2\.0", *_KEYBOARD_CONNECTION)),
              option("bluetooth", "Bluetooth", has(r"bluetooth", *_KEYBOARD_CONNECTION)),
              option("wireless", "Không dây 2.4GHz", has(r"2[.,]4|receiver|đầu thu|bolt|wireless", *_KEYBOARD_CONNECTION))),
        facet("layout", "Kích thước bàn phím",
              option("full-size", "Full-size", any_of(has(r"full|9[6-9]%", *_KEYBOARD_LAYOUT), between(_key_count, low=96))),
              option("tenkeyless", "Tenkeyless (TKL)", any_of(has(r"tenkeyless|tenlesskey|\btkl\b|80%", *_KEYBOARD_LAYOUT),
                                                              between(_key_count, 85, 90))),
              option("75", "75%", any_of(has(r"75%", *_KEYBOARD_LAYOUT), between(_key_count, 75, 84))),
              option("compact", "Mini (60 – 68%)", any_of(has(r"mini|6[0-8]%", *_KEYBOARD_LAYOUT), between(_key_count, high=74)))),
        facet("type", "Loại bàn phím",
              option("mechanical", "Bàn phím cơ", has(r"bàn phím cơ|\bcơ\b|mechanical|switch")),
              option("low-profile", "Low-profile", has(r"low-?profile"))),
        facet("lighting", "Đèn nền",
              option("rgb", "LED RGB", has(r"rgb|rainbow", "đèn led", "đèn nền")),
              option("single", "LED một màu", has(r"trắng|1 màu|một màu", "đèn led", "đèn nền")),
              option("none", "Không đèn", has(r"^không", "đèn led", "đèn nền"))),
    ),
    price_ranges=ACCESSORY_PRICES,
)

_DPI = ("độ phân giải (dpi)", "độ phân giải", "dpi")

MICE = FacetGroup(
    facets=(
        facet("connection", "Kết nối",
              option("wired", "Có dây", has(r"(?<!không )dây\b|usb 2\.0|cổng usb|usb-c to usb-a", "kết nối")),
              option("wireless", "Không dây 2.4GHz", has(r"2[.,]4|receiver|không dây|wireless", "kết nối")),
              option("bluetooth", "Bluetooth", has(r"bluetooth", "kết nối"))),
        facet("dpi", "Độ phân giải (DPI)",
              option("under-2000", "Dưới 2.000 DPI", between(largest("dpi", *_DPI), high=1999)),
              option("2000-10000", "2.000 – 10.000 DPI", between(largest("dpi", *_DPI), 2000, 10000)),
              option("over-10000", "Trên 10.000 DPI", between(largest("dpi", *_DPI), low=10001))),
        facet("lighting", "Đèn LED",
              option("rgb", "LED RGB", has(r"rgb|lightsync", "đèn led")),
              option("none", "Không LED", has(r"^không", "đèn led"))),
        facet("power", "Nguồn điện",
              option("rechargeable", "Pin sạc", has(r"pin sạc|li-?ion|li-?po|sạc", "loại pin", "pin")),
              option("aa", "Pin AA/AAA", has(r"\baaa?\b", "loại pin", "pin"))),
    ),
    price_ranges=ACCESSORY_PRICES,
)

SPEAKERS = FacetGroup(
    facets=(
        facet("type", "Kiểu loa",
              option("portable", "Loa di động (có pin)", any_of(has(r"có pin", "kiểu loa"),
                                                                between(largest(r"giờ|h", "thời lượng pin"), low=1))),
              option("plug-in", "Loa cắm điện", has(r"cắm điện|cắm nguồn", "kiểu loa", "thời lượng pin"))),
        facet("water", "Chống nước",
              option("ip67", "IP67 trở lên", has(r"\bip6[7-8]\b", "chống nước", "tính năng khác")),
              option("splash", "IPX4 – IP66", every(has(r"\bipx?[4-6]\b|\bip6[4-6]\b", "chống nước", "tính năng khác"),
                                                   but_not(r"\bip6[7-8]\b", "chống nước", "tính năng khác")))),
        facet("power", "Công suất",
              option("under-20w", "Dưới 20 W", between(largest("w", "công suất"), high=19.9)),
              option("20-50w", "20 – 50 W", between(largest("w", "công suất"), 20, 50)),
              option("over-50w", "Trên 50 W", between(largest("w", "công suất"), low=50.1))),
        facet("battery", "Thời lượng pin",
              option("under-12h", "Dưới 12 giờ", between(largest(r"giờ|h", "thời lượng pin"), high=11.9)),
              option("12-24h", "12 – 24 giờ", between(largest(r"giờ|h", "thời lượng pin"), 12, 24)),
              option("over-24h", "Trên 24 giờ", between(largest(r"giờ|h", "thời lượng pin"), low=24.1))),
        facet("ports", "Cổng kết nối",
              option("aux", "AUX 3.5 mm", has(r"3[.,]5|aux", "cổng kết nối")),
              option("usb-c", "USB-C", has(r"usb-?c|type-?c", "cổng kết nối"))),
    ),
    price_ranges=ACCESSORY_PRICES,
)

POWER_BANKS = FacetGroup(
    facets=(
        facet("capacity", "Dung lượng pin",
              option("under-10000", "Dưới 10.000 mAh", between(largest("mah", "dung lượng pin"), high=9999)),
              option("10000", "10.000 mAh", between(largest("mah", "dung lượng pin"), 10000, 10000)),
              option("20000", "20.000 mAh", between(largest("mah", "dung lượng pin"), 20000, 20000)),
              option("over-20000", "Trên 20.000 mAh", between(largest("mah", "dung lượng pin"), low=20001))),
        facet("power", "Công suất sạc",
              option("under-20w", "Dưới 20 W", between(largest("w", "công suất sạc"), high=19.9)),
              option("20-45w", "20 – 45 W", between(largest("w", "công suất sạc"), 20, 45)),
              option("over-45w", "Trên 45 W", between(largest("w", "công suất sạc"), low=45.1))),
        facet("features", "Tính năng",
              option("wireless", "Sạc không dây / MagSafe", has(r"không dây|wireless|magsafe|\bqi\b")),
              option("laptop", "Sạc được laptop", has(r"laptop")),
              option("display", "Màn hình hiển thị", has(r"màn hình hiển thị|hiển thị thông số")),
              option("fast", "Sạc nhanh", has(r"sạc nhanh|\bpd\b|\bqc\b|quick charge"))),
        facet("ports", "Cổng sạc ra",
              option("usb-c", "Có USB-C", has(r"usb-?c|type-?c", "cổng sạc ra")),
              option("usb-a", "Có USB-A", has(r"usb-?a", "cổng sạc ra"))),
    ),
    price_ranges=ACCESSORY_PRICES,
)

# A root category without its own criteria still gets price ranges (the homepage menu's ranges).
DEFAULT = FacetGroup(facets=(), price_ranges=(
    price("under-5", "Dưới 5 triệu", None, "5"), price("5-10", "5 – 10 triệu", "5", "10"),
    price("10-15", "10 – 15 triệu", "10", "15"), price("15-20", "15 – 20 triệu", "15", "20"),
    price("from-20", "Trên 20 triệu", "20", None),
))

_GROUPS = {
    ("dien-thoai", "phone", "smartphone"): PHONES,
    ("laptop", "may-tinh-xach-tay"): LAPTOPS,
    ("may-tinh-bang", "tablet"): TABLETS,
    ("tai-nghe", "headphone", "headphones"): HEADPHONES,
    ("man-hinh", "monitor"): MONITORS,
    ("ban-phim", "keyboard"): KEYBOARDS,
    ("chuot", "mouse"): MICE,
    ("loa", "speaker", "speakers"): SPEAKERS,
    ("pin-sac-du-phong", "sac-du-phong", "powerbank"): POWER_BANKS,
}


def facet_group(root_slug: str | None) -> FacetGroup:
    """Criteria of a root category, found by its slug."""
    slug = (root_slug or "").strip().lower()
    return next((group for slugs, group in _GROUPS.items() if slug in slugs), DEFAULT)
