"""Catalog APIs: categories, brands, products, variants, images and serials.

Public reads accept an optional Actor: signed-in Staff/Admin also see hidden items (``active_only=false``).
Business rules and permissions live in the catalog Services.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.schemas import (
    AdminProductDetailResponse,
    AdminProductResponse,
    AdminProductVariantResponse,
    BrandCreate,
    BrandResponse,
    BrandUpdate,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    PageResponse,
    ProductCreate,
    ProductDetailResponse,
    ProductImageCreate,
    ProductImageResponse,
    ProductImageUpdate,
    ProductSerialCreate,
    ProductSerialResponse,
    ProductSerialUpdate,
    ProductSummary,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantUpdate,
)
from app.services.catalog import (
    BrandService,
    CategoryService,
    ProductImageService,
    ProductSerialService,
    ProductService,
    ProductVariantService,
)

from .dependencies import (
    CurrentActor,
    InternalOnly,
    OptionalActor,
    Page,
    PageSize,
    get_brand_service,
    get_category_service,
    get_image_service,
    get_product_service,
    get_serial_service,
    get_variant_service,
)

router = APIRouter(tags=["Sản phẩm"])
admin_router = APIRouter(prefix="/admin", tags=["Quản lý sản phẩm"], dependencies=[InternalOnly])

Categories = Annotated[CategoryService, Depends(get_category_service)]
Brands = Annotated[BrandService, Depends(get_brand_service)]
Products = Annotated[ProductService, Depends(get_product_service)]
Variants = Annotated[ProductVariantService, Depends(get_variant_service)]
Images = Annotated[ProductImageService, Depends(get_image_service)]
Serials = Annotated[ProductSerialService, Depends(get_serial_service)]


# ------------------------------------------------------------------ categories


@router.get("/categories", response_model=list[CategoryResponse])
def list_categories(service: Categories, actor: OptionalActor, active_only: bool = True,
                    parent_id: uuid.UUID | None = None, roots_only: bool = False):
    """Customers see active categories; Staff/Admin may pass ``active_only=false`` to include hidden ones."""
    return service.list_categories(actor=actor, active_only=active_only, parent_id=parent_id, roots_only=roots_only)


@router.get("/categories/slug/{slug}", response_model=CategoryResponse)
def get_category_by_slug(slug: str, service: Categories, actor: OptionalActor, active_only: bool = True):
    return service.get_category_by_slug(slug, actor=actor, active_only=active_only)


@router.get("/categories/{category_id}", response_model=CategoryResponse)
def get_category(category_id: uuid.UUID, service: Categories, actor: OptionalActor, active_only: bool = True):
    return service.get_category(category_id, actor=actor, active_only=active_only)


@admin_router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(data: CategoryCreate, service: Categories, actor: CurrentActor):
    return service.create_category(actor, data)


@admin_router.patch("/categories/{category_id}", response_model=CategoryResponse)
def update_category(category_id: uuid.UUID, data: CategoryUpdate, service: Categories, actor: CurrentActor):
    return service.update_category(actor, category_id, data)


@admin_router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: uuid.UUID, service: Categories, actor: CurrentActor):
    service.delete_category(actor, category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ brands


@router.get("/brands", response_model=list[BrandResponse])
def list_brands(service: Brands, actor: OptionalActor, active_only: bool = True):
    return service.list_brands(actor=actor, active_only=active_only)


@router.get("/brands/slug/{slug}", response_model=BrandResponse)
def get_brand_by_slug(slug: str, service: Brands, actor: OptionalActor, active_only: bool = True):
    return service.get_brand_by_slug(slug, actor=actor, active_only=active_only)


@router.get("/brands/{brand_id}", response_model=BrandResponse)
def get_brand(brand_id: uuid.UUID, service: Brands, actor: OptionalActor, active_only: bool = True):
    return service.get_brand(brand_id, actor=actor, active_only=active_only)


@admin_router.post("/brands", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
def create_brand(data: BrandCreate, service: Brands, actor: CurrentActor):
    return service.create_brand(actor, data)


@admin_router.patch("/brands/{brand_id}", response_model=BrandResponse)
def update_brand(brand_id: uuid.UUID, data: BrandUpdate, service: Brands, actor: CurrentActor):
    return service.update_brand(actor, brand_id, data)


@admin_router.delete("/brands/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_brand(brand_id: uuid.UUID, service: Brands, actor: CurrentActor):
    service.delete_brand(actor, brand_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ products (public)


@router.get("/products", response_model=PageResponse[ProductSummary])
def search_products(service: Products, keyword: str | None = None, category_id: uuid.UUID | None = None,
                    brand_id: uuid.UUID | None = None, page: Page = 1, page_size: PageSize = 20):
    return service.search_products(keyword=keyword, category_id=category_id, brand_id=brand_id,
                                   page=page, page_size=page_size)


@router.get("/products/slug/{slug}", response_model=ProductDetailResponse)
def get_product_by_slug(slug: str, service: Products):
    return service.get_product_detail_by_slug(slug)


@router.get("/products/{product_id}", response_model=ProductDetailResponse)
def get_product(product_id: uuid.UUID, service: Products):
    return service.get_product_detail(product_id)


@router.get("/products/{product_id}/images", response_model=list[ProductImageResponse])
def list_product_images(product_id: uuid.UUID, service: Images):
    return service.list_images(product_id)


# ------------------------------------------------------------------ products (admin)


@admin_router.get("/products", response_model=PageResponse[AdminProductResponse])
def admin_list_products(service: Products, actor: CurrentActor, keyword: str | None = None,
                        category_id: uuid.UUID | None = None, brand_id: uuid.UUID | None = None,
                        status_filter: Annotated[str | None, Query(alias="status")] = None,
                        include_deleted: bool = False, page: Page = 1, page_size: PageSize = 20):
    return service.admin_list_products(actor, keyword=keyword, category_id=category_id, brand_id=brand_id,
                                       status=status_filter, include_deleted=include_deleted,
                                       page=page, page_size=page_size)


@admin_router.get("/products/{product_id}", response_model=AdminProductDetailResponse)
def admin_get_product(product_id: uuid.UUID, service: Products, actor: CurrentActor):
    return service.admin_get_product(actor, product_id)


@admin_router.post("/products", response_model=AdminProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(data: ProductCreate, service: Products, actor: CurrentActor):
    return service.create_product(actor, data)


@admin_router.patch("/products/{product_id}", response_model=AdminProductResponse)
def update_product(product_id: uuid.UUID, data: ProductUpdate, service: Products, actor: CurrentActor):
    return service.update_product(actor, product_id, data)


@admin_router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: uuid.UUID, service: Products, actor: CurrentActor):
    service.delete_product(actor, product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ variants (admin)


@admin_router.get("/products/{product_id}/variants", response_model=list[AdminProductVariantResponse])
def list_variants(product_id: uuid.UUID, service: Variants, actor: CurrentActor, include_deleted: bool = False):
    return service.list_variants(actor, product_id, include_deleted=include_deleted)


@admin_router.get("/variants/{variant_id}", response_model=AdminProductVariantResponse)
def get_variant(variant_id: uuid.UUID, service: Variants, actor: CurrentActor):
    return service.get_variant(actor, variant_id)


@admin_router.post("/variants", response_model=AdminProductVariantResponse, status_code=status.HTTP_201_CREATED)
def create_variant(data: ProductVariantCreate, service: Variants, actor: CurrentActor):
    return service.create_variant(actor, data)


@admin_router.patch("/variants/{variant_id}", response_model=AdminProductVariantResponse)
def update_variant(variant_id: uuid.UUID, data: ProductVariantUpdate, service: Variants, actor: CurrentActor):
    return service.update_variant(actor, variant_id, data)


@admin_router.delete("/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variant(variant_id: uuid.UUID, service: Variants, actor: CurrentActor):
    service.delete_variant(actor, variant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ images (admin)


@admin_router.post("/products/{product_id}/images", response_model=ProductImageResponse,
                   status_code=status.HTTP_201_CREATED)
def add_image(product_id: uuid.UUID, data: ProductImageCreate, service: Images, actor: CurrentActor):
    return service.add_image(actor, product_id, data)


@admin_router.patch("/products/{product_id}/images/{image_id}", response_model=ProductImageResponse)
def update_image(product_id: uuid.UUID, image_id: uuid.UUID, data: ProductImageUpdate, service: Images,
                 actor: CurrentActor):
    return service.update_image(actor, product_id, image_id, data)


@admin_router.delete("/products/{product_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(product_id: uuid.UUID, image_id: uuid.UUID, service: Images, actor: CurrentActor):
    service.delete_image(actor, product_id, image_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ serials (admin)


@admin_router.get("/variants/{variant_id}/serials", response_model=PageResponse[ProductSerialResponse])
def list_serials(variant_id: uuid.UUID, service: Serials, actor: CurrentActor,
                 status_filter: Annotated[str | None, Query(alias="status")] = None,
                 page: Page = 1, page_size: PageSize = 20):
    return service.list_serials(actor, variant_id, status=status_filter, page=page, page_size=page_size)


@admin_router.get("/serials/lookup", response_model=ProductSerialResponse)
def get_serial_by_number(serial_number: str, service: Serials, actor: CurrentActor):
    return service.get_by_serial_number(actor, serial_number)


@admin_router.get("/serials/{serial_id}", response_model=ProductSerialResponse)
def get_serial(serial_id: uuid.UUID, service: Serials, actor: CurrentActor):
    return service.get_serial(actor, serial_id)


@admin_router.post("/serials", response_model=ProductSerialResponse, status_code=status.HTTP_201_CREATED)
def create_serial(data: ProductSerialCreate, service: Serials, actor: CurrentActor):
    return service.create_serial(actor, data)


@admin_router.patch("/serials/{serial_id}", response_model=ProductSerialResponse)
def update_serial(serial_id: uuid.UUID, data: ProductSerialUpdate, service: Serials, actor: CurrentActor):
    return service.update_serial(actor, serial_id, data)


@admin_router.delete("/serials/{serial_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_serial(serial_id: uuid.UUID, service: Serials, actor: CurrentActor):
    service.delete_serial(actor, serial_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
