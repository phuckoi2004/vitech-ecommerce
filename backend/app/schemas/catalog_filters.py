"""Bộ lọc của trang danh mục khách hàng (GET /categories/{id}/filters, docs/customer-category-listing.md)."""

import uuid

from .common import Money, NonNegativeInt, ResponseSchema


class FilterOptionResponse(ResponseSchema):
    Value: str
    Label: str
    ProductCount: NonNegativeInt


class PriceRangeResponse(FilterOptionResponse):
    MinPrice: Money | None
    MaxPrice: Money | None


class FilterFacetResponse(ResponseSchema):
    """Một tiêu chí theo thông số; gửi lựa chọn lên GET /products dạng ``spec=<Key>:<Value>``."""

    Key: str
    Label: str
    Options: list[FilterOptionResponse]


class FilterBrandResponse(ResponseSchema):
    BrandId: uuid.UUID
    Name: str
    Slug: str
    ProductCount: NonNegativeInt


class CategoryFiltersResponse(ResponseSchema):
    """Chỉ gồm lựa chọn có sản phẩm đang bán trong danh mục và các danh mục con đang hiển thị."""

    Brands: list[FilterBrandResponse]
    PriceRanges: list[PriceRangeResponse]
    Facets: list[FilterFacetResponse]


class FilterCategoryResponse(ResponseSchema):
    CategoryId: uuid.UUID
    Name: str
    Slug: str
    ProductCount: NonNegativeInt


class SearchFiltersResponse(ResponseSchema):
    """Danh mục gốc và hãng của các sản phẩm khớp tìm kiếm (GET /products/filters, docs/customer-search.md).

    Mỗi nhóm đếm theo mọi bộ lọc khác trừ chính nó, nên khách đổi sang danh mục/hãng khác mà không phải bỏ chọn trước.
    """

    Categories: list[FilterCategoryResponse]
    Brands: list[FilterBrandResponse]


class SuggestedSearchResponse(ResponseSchema):
    """“Có phải bạn muốn tìm”: a category page, with one brand chosen when BrandId is set."""

    Label: str
    CategorySlug: str
    BrandId: uuid.UUID | None
    ImageUrl: str | None


class SuggestedProductResponse(ResponseSchema):
    """Price is the lowest one customers pay now; OriginalPrice only when it is higher (shown struck through)."""

    ProductId: uuid.UUID
    Name: str
    Slug: str
    ImageUrl: str | None
    Price: Money | None
    OriginalPrice: Money | None


class SearchSuggestionsResponse(ResponseSchema):
    """Gợi ý dưới ô tìm kiếm khi khách đang gõ (GET /products/suggestions, docs/customer-search.md)."""

    Searches: list[SuggestedSearchResponse]
    Products: list[SuggestedProductResponse]
