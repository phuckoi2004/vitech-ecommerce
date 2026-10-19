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


def _image_order(image):
    return not image.IsDefault, image.DisplayOrder, str(image.ProductImageId)


def default_variant_id(product, variants=None):
    variants = [variant for variant in (product.variants if variants is None else variants) if not variant.IsDeleted]
    stored = media_settings(product).get("DefaultVariantId")
    selected = next((variant for variant in variants if str(variant.ProductVariantId) == stored), None)
    if selected is None and variants:
        # No recorded default (older products): the variant showing the photo marked "Mặc định" in the gallery,
        # so the default follows the main photo instead of whichever ID happens to sort first.
        main = min(product.images, key=_image_order, default=None)
        owners = [variant for variant in variants if main is not None
                  and main.ImageUrl in {image.ImageUrl for image in variant_images(product, variant.ProductVariantId)[0]}]
        selected = min(owners or variants, key=lambda variant: str(variant.ProductVariantId))
    return selected.ProductVariantId if selected else None


def variant_images(product, variant_id, images=None):
    images = list(product.images if images is None else images)
    configured = media_settings(product).get("Variants", {})
    config = configured.get(str(variant_id))
    ordered = sorted(images, key=_image_order)
    if config is None:
        # Legacy variants retain the shared gallery, except photos another variant has chosen as its own,
        # so a photo added for one colour does not also appear on every other colour.
        claimed = {url for key, other in configured.items() if key != str(variant_id) and isinstance(other, dict)
                   for url in other.get("ImageUrls", [])}
        ordered = [image for image in ordered if image.ImageUrl not in claimed]
        return ordered, ordered[0].ImageUrl if ordered else None
    by_url = {image.ImageUrl: image for image in images}
    chosen = [by_url[url] for url in config.get("ImageUrls", []) if url in by_url]
    default = config.get("DefaultImageUrl")
    if default not in {image.ImageUrl for image in chosen}:
        default = chosen[0].ImageUrl if chosen else None
    return chosen, default


def set_variant_media(product, variant_id, *, urls, default_url, make_default, variants, previous_default=None, created=False):
    settings = media_settings(product)
    if urls is not None:
        settings.setdefault("Variants", {})[str(variant_id)] = {"ImageUrls": urls, "DefaultImageUrl": default_url}
    recorded = any(str(variant.ProductVariantId) == settings.get("DefaultVariantId") for variant in variants if not variant.IsDeleted)
    if make_default:
        settings["DefaultVariantId"] = str(variant_id)
    elif created and not recorded:
        # A variant added to a product keeps the earlier default, or becomes the default as the first variant.
        settings["DefaultVariantId"] = str(previous_default or variant_id)
    # Editing a variant without "make default" never records a guessed default.
    product.Specifications = {**(product.Specifications or {}), MEDIA_KEY: settings}
