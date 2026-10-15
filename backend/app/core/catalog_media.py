"""Variant media metadata inside the existing Product.Specifications JSON column.

No schema changes. URLs identify immutable images in the parent's gallery; the private
namespace is excluded from technical specifications returned to any client.
"""

from copy import deepcopy


MEDIA_KEY = "_vietech_variant_media"


def technical_specifications(value):
    if value is None:
        return None
    result = {key: item for key, item in value.items() if key != MEDIA_KEY}
    return result if result or MEDIA_KEY not in value else None


def validate_specifications(value):
    if value and MEDIA_KEY in value:
        raise ValueError("Khóa dữ liệu này do hệ thống quản lý, không thuộc thông số kỹ thuật")
    return value


def merge_specifications(current, incoming):
    result = dict(incoming or {})
    if isinstance(current, dict) and MEDIA_KEY in current:
        result[MEDIA_KEY] = deepcopy(current[MEDIA_KEY])
    return result or None


def media_settings(product):
    value = (product.Specifications or {}).get(MEDIA_KEY, {})
    return deepcopy(value) if isinstance(value, dict) else {}


def default_variant_id(product, variants=None):
    variants = [variant for variant in (product.variants if variants is None else variants) if not variant.IsDeleted]
    stored = media_settings(product).get("DefaultVariantId")
    selected = next((variant for variant in variants if str(variant.ProductVariantId) == stored), None)
    # Legacy products have no recorded first variant; use a stable fallback until explicitly chosen.
    selected = selected or min(variants, key=lambda variant: str(variant.ProductVariantId), default=None)
    return selected.ProductVariantId if selected else None


def variant_images(product, variant_id, images=None):
    images = list(product.images if images is None else images)
    config = media_settings(product).get("Variants", {}).get(str(variant_id))
    ordered = sorted(images, key=lambda image: (not image.IsDefault, image.DisplayOrder, str(image.ProductImageId)))
    if config is None:  # Legacy variants retain the previously shared gallery.
        return ordered, ordered[0].ImageUrl if ordered else None
    by_url = {image.ImageUrl: image for image in images}
    chosen = [by_url[url] for url in config.get("ImageUrls", []) if url in by_url]
    default = config.get("DefaultImageUrl")
    if default not in {image.ImageUrl for image in chosen}:
        default = chosen[0].ImageUrl if chosen else None
    return chosen, default


def set_variant_media(product, variant_id, *, urls, default_url, make_default, variants, previous_default=None):
    settings = media_settings(product)
    current_default = previous_default or default_variant_id(product, variants)
    settings["DefaultVariantId"] = str(variant_id if make_default or current_default is None else current_default)
    if urls is not None:
        settings.setdefault("Variants", {})[str(variant_id)] = {"ImageUrls": urls, "DefaultImageUrl": default_url}
    product.Specifications = {**(product.Specifications or {}), MEDIA_KEY: settings}
