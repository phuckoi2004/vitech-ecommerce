"""Variant photos and the default variant.

A variant without its own selection never shows photos chosen by a sibling, and the default variant is never
picked by ID order: it is recorded explicitly or follows the gallery's main photo.
"""

import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.catalog_media import MEDIA_KEY, default_variant_id, set_variant_media, variant_images
from app.schemas.catalog_item import CatalogProductWrite


def image(url, *, default=False, order=0):
    return SimpleNamespace(ProductImageId=uuid.uuid4(), ImageUrl=url, IsDefault=default, DisplayOrder=order)


def product(images, variants):
    return SimpleNamespace(images=images, Specifications={MEDIA_KEY: {"Variants": variants}})


def test_unselected_variant_keeps_shared_photos_but_not_a_siblings_own_photos():
    black, blue, box = image("https://cdn.test/black.webp", default=True), image("https://cdn.test/blue.webp", order=1), image("https://cdn.test/box.webp", order=2)
    legacy, configured = uuid.uuid4(), uuid.uuid4()
    item = product([black, blue, box], {str(configured): {"ImageUrls": [blue.ImageUrl], "DefaultImageUrl": blue.ImageUrl}})

    chosen, thumbnail = variant_images(item, legacy)
    assert [entry.ImageUrl for entry in chosen] == [black.ImageUrl, box.ImageUrl]
    assert thumbnail == black.ImageUrl
    assert variant_images(item, configured) == ([blue], blue.ImageUrl)


def test_unselected_variant_moves_to_the_next_photo_when_the_default_belongs_to_a_sibling():
    black, blue = image("https://cdn.test/black.webp", default=True), image("https://cdn.test/blue.webp", order=1)
    item = product([black, blue], {str(uuid.uuid4()): {"ImageUrls": [black.ImageUrl], "DefaultImageUrl": black.ImageUrl}})
    assert variant_images(item, uuid.uuid4()) == ([blue], blue.ImageUrl)


def test_product_without_any_selection_still_shares_the_whole_gallery():
    black, blue = image("https://cdn.test/black.webp", default=True), image("https://cdn.test/blue.webp", order=1)
    item = SimpleNamespace(images=[blue, black], Specifications=None)
    assert variant_images(item, uuid.uuid4()) == ([black, blue], black.ImageUrl)


def variant(identifier):
    return SimpleNamespace(ProductVariantId=uuid.UUID(identifier), IsDeleted=False)


# The blue variant's ID sorts first, as on the real Galaxy S26 data where it wrongly became the default.
BLUE, BLACK = variant("00000000-0000-0000-0000-000000000001"), variant("ffffffff-0000-0000-0000-000000000002")


def test_without_a_recorded_default_the_variant_with_the_main_photo_is_default_not_the_lowest_id():
    black, blue = image("https://cdn.test/black.webp", default=True), image("https://cdn.test/blue.webp", order=1)
    item = product([black, blue], {str(BLUE.ProductVariantId): {"ImageUrls": [blue.ImageUrl], "DefaultImageUrl": blue.ImageUrl}})
    assert default_variant_id(item, [BLUE, BLACK]) == BLACK.ProductVariantId
    item.Specifications[MEDIA_KEY]["DefaultVariantId"] = str(BLUE.ProductVariantId)
    assert default_variant_id(item, [BLUE, BLACK]) == BLUE.ProductVariantId  # an explicit choice always wins


def test_editing_a_variant_never_records_a_guessed_default():
    black, blue = image("https://cdn.test/black.webp", default=True), image("https://cdn.test/blue.webp", order=1)
    item = product([black, blue], {})
    set_variant_media(item, BLUE.ProductVariantId, urls=[blue.ImageUrl], default_url=blue.ImageUrl,
                      make_default=False, variants=[BLUE, BLACK])
    assert "DefaultVariantId" not in item.Specifications[MEDIA_KEY]
    assert default_variant_id(item, [BLUE, BLACK]) == BLACK.ProductVariantId
    set_variant_media(item, BLUE.ProductVariantId, urls=None, default_url=None, make_default=True, variants=[BLUE, BLACK])
    assert default_variant_id(item, [BLUE, BLACK]) == BLUE.ProductVariantId


def test_a_new_variant_keeps_the_earlier_default_and_the_first_variant_becomes_default():
    black, blue = image("https://cdn.test/black.webp", default=True), image("https://cdn.test/blue.webp", order=1)
    item = product([black, blue], {})
    set_variant_media(item, BLUE.ProductVariantId, urls=[blue.ImageUrl], default_url=blue.ImageUrl, make_default=False,
                      variants=[BLUE, BLACK], previous_default=BLACK.ProductVariantId, created=True)
    assert item.Specifications[MEDIA_KEY]["DefaultVariantId"] == str(BLACK.ProductVariantId)
    first = product([black], {})
    set_variant_media(first, BLACK.ProductVariantId, urls=[black.ImageUrl], default_url=black.ImageUrl, make_default=False,
                      variants=[BLACK], created=True)
    assert first.Specifications[MEDIA_KEY]["DefaultVariantId"] == str(BLACK.ProductVariantId)


def test_gallery_cannot_contain_the_same_photo_twice():
    shared = {"Name": "Điện thoại", "CategoryId": uuid.uuid4(), "BrandId": uuid.uuid4(), "WarrantyMonths": 12, "Status": "Draft"}
    url = "https://cdn.test/black.webp"
    with pytest.raises(ValidationError, match="trùng"):
        CatalogProductWrite(**shared, Images=[{"ImageUrl": url, "IsDefault": True}, {"ImageUrl": url}])
    assert len(CatalogProductWrite(**shared, Images=[{"ImageUrl": url, "IsDefault": True}]).Images) == 1
