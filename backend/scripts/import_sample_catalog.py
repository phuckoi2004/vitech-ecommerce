"""Validate or import the reviewed 200-product sample catalog.

Dry-run is the default. --apply creates only new rows; reruns never reset stock,
prices, images or existing catalog records. Opening inventory uses InventoryService.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
import uuid
from collections import Counter
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import func, select

BACKEND = Path(__file__).resolve().parents[1]
WORKSPACE = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal
from app.models import Brand, Category, Product, ProductImage, ProductVariant, StockAdjustment, User
from app.schemas.catalog import BrandCreate, CategoryCreate, ProductCreate, ProductImageCreate, ProductVariantCreate
from app.schemas.inventory import StockOpeningCreate
from app.services import Actor
from app.services.catalog import BrandService, CategoryService, ProductImageService, ProductService, ProductVariantService
from app.services.inventory import InventoryService

BATCH = "sample-catalog-2026-10-17"
DEFAULT_MANIFEST = BACKEND / "data" / f"{BATCH}.json"
SOURCE_HOSTS = {"cellphones.com.vn", "gearvn.com"}
IMAGE_HOSTS = {"cdn2.cellphones.com.vn", "cdn.hstatic.net"}
DUMMY_UUID = uuid.UUID(int=1)


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
    return re.sub(r"[^a-z0-9]+", "-", value.encode("ascii", "ignore").decode()).strip("-")


def model_key(value: str, category: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d").split("|")[0])
    value = value.encode("ascii", "ignore").decode()
    value = re.sub(r"\b(dien thoai|laptop|may tinh bang|chinh hang|viet nam)\b", " ", value)
    if category in {"dien-thoai", "may-tinh-bang"}:
        value = re.sub(r"\b\d+\s*(gb|tb)\b|\b5g\b", " ", value)
    if category in {"chuot", "ban-phim", "tai-nghe", "loa", "pin-sac-du-phong"}:
        value = re.sub(r"\b(black|white|grey|gray|pink|red|blue|green|den|trang|xam|hong|xanh)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def checked_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    rows = manifest["products"]
    if manifest.get("batch") != BATCH or len(rows) != 200:
        raise ValueError("Manifest phải đúng batch và có đủ 200 sản phẩm.")
    if manifest.get("sample_quantity_per_product") != 10 or manifest.get("sample_cost_ratio") != "0.80":
        raise ValueError("Thiết lập tồn/giá vốn mẫu không khớp bản đã chuẩn bị.")
    for field in ("sku", "slug", "source_url"):
        if len({row[field] for row in rows}) != 200:
            raise ValueError(f"Trùng {field} trong manifest.")
    if len({(row["category_slug"], row["model_key"]) for row in rows}) != 200:
        raise ValueError("Trùng mẫu sản phẩm.")
    if len({row["category_slug"] for row in rows}) < 8 or len({normalized(row["brand"]) for row in rows}) < 15:
        raise ValueError("Bộ sản phẩm chưa đủ đa dạng danh mục/thương hiệu.")
    if {urlparse(row["source_url"]).hostname for row in rows} != SOURCE_HOSTS:
        raise ValueError("Nguồn sản phẩm không đúng hai website đã chuẩn bị.")
    for row in rows:
        source, image = urlparse(row["source_url"]), urlparse(row["image_url"])
        if source.scheme != "https" or source.hostname not in SOURCE_HOSTS:
            raise ValueError("Nguồn sản phẩm không hợp lệ.")
        if image.scheme != "https" or image.hostname not in IMAGE_HOSTS or not row.get("image_verified_at"):
            raise ValueError("Ảnh chưa được kiểm tra.")
        if not row.get("warranty_evidence") or not 1 <= row["warranty_months"] <= 60:
            raise ValueError("Thiếu căn cứ thời hạn bảo hành.")
        if row["model_key"] != model_key(row["name"], row["category_slug"]):
            raise ValueError("Khóa nhận diện sản phẩm không khớp.")
        ProductCreate(CategoryId=DUMMY_UUID, BrandId=DUMMY_UUID, Name=row["name"], Slug=row["slug"],
                      Description=row["description"], Specifications=row["specifications"],
                      WarrantyMonths=row["warranty_months"], Status="Active")
        ProductVariantCreate(ProductId=DUMMY_UUID, Sku=row["sku"], VariantName=variant_name(row),
                             Color=row["color"], Storage=row["storage"], Price=Decimal(row["price"]),
                             MinStockLevel=2, IsActive=True, IsSerialTracked=False)
        ProductImageCreate(ImageUrl=row["image_url"], DisplayOrder=0, IsDefault=True)
        StockOpeningCreate(Quantity=10, UnitCost=sample_cost(row), Reason=opening_reason())
    return manifest


def variant_name(row):
    return " · ".join(filter(None, (row["color"], row["storage"]))) or row["name"]


def sample_cost(row):
    return (Decimal(row["price"]) * Decimal("0.80")).quantize(Decimal("0.01"))


def opening_reason():
    return f"{BATCH}: tồn mẫu 10 đơn vị; giá vốn mẫu = 80% giá tham khảo, không phải giá nhập thực tế."


def fingerprint(record):
    return {column.key: str(getattr(record, column.key)) for column in record.__mapper__.column_attrs}


def counts(db):
    return {model.__tablename__: db.scalar(select(func.count()).select_from(model))
            for model in (Product, ProductVariant, ProductImage, Category, Brand, StockAdjustment)}


def run(manifest_path: Path, apply: bool):
    manifest = checked_manifest(manifest_path)
    rows = manifest["products"]
    result = {"batch": BATCH, "apply": apply, "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              "categories": dict(Counter(row["category_name"] for row in rows)),
              "brand_count": len({normalized(row["brand"]) for row in rows}),
              "sources": dict(Counter(row["source_retailer"] for row in rows)), "created_products": 0,
              "created_categories": 0, "created_brands": 0, "skipped_existing_batch": 0, "products": []}
    with SessionLocal() as db:
        before = counts(db)
        products = db.scalars(select(Product)).all()
        existing_products = {product.Slug: product for product in products}
        variants = {variant.Sku: variant for variant in db.scalars(select(ProductVariant)).all()}
        categories = list(db.scalars(select(Category)).all())
        brands = list(db.scalars(select(Brand)).all())
        category_lookup = {normalized(item.Slug): item for item in categories}
        category_lookup.update({normalized(item.Name): item for item in categories if item.ParentCategoryId is None})
        brand_lookup = {normalized(item.Name): item for item in brands}
        brand_lookup.update({normalized(item.Slug): item for item in brands})
        preserved = {model: {str(item.__dict__[model.__mapper__.primary_key[0].key]): fingerprint(item)
                              for item in db.scalars(select(model)).all()}
                     for model in (Product, ProductVariant, ProductImage, Category, Brand)}
        missing = []
        for row in rows:
            variant = variants.get(row["sku"])
            if variant is not None:
                product = existing_products.get(row["slug"])
                if product is None or variant.ProductId != product.ProductId or product.Name != row["name"]:
                    raise ValueError("SKU batch đã được sử dụng cho dữ liệu khác.")
                result["skipped_existing_batch"] += 1
                result["products"].append({"product_id": str(product.ProductId), "variant_id": str(variant.ProductVariantId), "slug": product.Slug, "sku": variant.Sku})
                continue
            if row["slug"] in existing_products:
                raise ValueError("Slug đã tồn tại ngoài batch; không ghi đè.")
            if any(model_key(product.Name, row["category_slug"]) == row["model_key"] for product in products):
                raise ValueError("Mẫu sản phẩm đã có trong project; không tạo trùng.")
            category = category_lookup.get(row["category_slug"])
            brand = brand_lookup.get(normalized(row["brand"]))
            if category is not None and not category.IsActive:
                raise ValueError("Danh mục hiện có đang ẩn; không tự kích hoạt lại.")
            if brand is not None and not brand.IsActive:
                raise ValueError("Thương hiệu hiện có đang ẩn; không tự kích hoạt lại.")
            missing.append(row)
        result["would_create_products"] = len(missing)
        result["before"] = before
        if not apply:
            return result
        admin = db.execute(select(User.UserId, User.Role).where(User.Role == "Admin", User.AccountStatus == "Active",
                            User.IsDeleted.is_(False)).order_by(User.CreatedAt).limit(1)).first()
        if admin is None:
            raise ValueError("Không có Admin đang hoạt động để ghi nhận nghiệp vụ nhập mẫu.")
        actor = Actor(admin.UserId, admin.Role)
        product_service, variant_service = ProductService(db), ProductVariantService(db)
        category_service, brand_service = CategoryService(db), BrandService(db)
        image_service, inventory_service = ProductImageService(db), InventoryService(db)
        order = max((category.DisplayOrder for category in categories), default=0)
        with product_service.transaction():
            for index, row in enumerate(missing, 1):
                category = category_lookup.get(row["category_slug"])
                if category is None:
                    order += 1
                    category = category_service.create_category(actor, CategoryCreate(Name=row["category_name"],
                        Slug=row["category_slug"], DisplayOrder=order, ImageUrl=row["image_url"], IsActive=True))
                    category_lookup[row["category_slug"]] = category
                    result["created_categories"] += 1
                brand_key = normalized(row["brand"])
                brand = brand_lookup.get(brand_key)
                if brand is None:
                    brand = brand_service.create_brand(actor, BrandCreate(Name=row["brand"], Slug=brand_key, IsActive=True))
                    brand_lookup[brand_key] = brand
                    result["created_brands"] += 1
                product = product_service.create_product(actor, ProductCreate(CategoryId=category.CategoryId,
                    BrandId=brand.BrandId, Name=row["name"], Slug=row["slug"], Description=row["description"],
                    Specifications=row["specifications"], WarrantyMonths=row["warranty_months"], Status="Active"))
                variant = variant_service.create_variant(actor, ProductVariantCreate(ProductId=product.ProductId,
                    Sku=row["sku"], VariantName=variant_name(row), Color=row["color"], Storage=row["storage"],
                    Price=Decimal(row["price"]), MinStockLevel=2, IsActive=True, IsSerialTracked=False))
                image_service.add_image(actor, product.ProductId, ProductImageCreate(ImageUrl=row["image_url"], DisplayOrder=0, IsDefault=True))
                inventory_service.declare_opening(actor, variant.ProductVariantId, StockOpeningCreate(
                    Quantity=10, UnitCost=sample_cost(row), Reason=opening_reason()))
                result["created_products"] += 1
                result["products"].append({"product_id": str(product.ProductId), "variant_id": str(variant.ProductVariantId), "slug": product.Slug, "sku": variant.Sku})
                if index % 20 == 0:
                    print(json.dumps({"stage": "importing", "prepared": index, "total": len(missing), "committed": False}), flush=True)
            db.flush()
            for model, old_records in preserved.items():
                for item in db.scalars(select(model)).all():
                    key = str(getattr(item, model.__mapper__.primary_key[0].key))
                    if key in old_records and fingerprint(item) != old_records[key]:
                        raise ValueError("Dữ liệu cũ đã thay đổi; hủy transaction nhập mẫu.")
            after = counts(db)
            if after["Products"] != before["Products"] + len(missing) or after["StockAdjustments"] != before["StockAdjustments"] + len(missing):
                raise ValueError("Số sản phẩm hoặc lịch sử tồn đầu kỳ không khớp.")
        result["after"] = after
        result["existing_catalog_preserved"] = True
    folder = WORKSPACE / "output" / "catalog-import-20261017"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ("import-result.json" if result["created_products"] else "rerun-result.json")).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def export_csv(manifest, result):
    path = WORKSPACE / "docs" / "data" / "sample-products-2026-10-17.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    ids = {row["sku"]: row for row in result.get("products", [])}
    fields = ["STT", "TenSanPham", "DanhMuc", "ThuongHieu", "GiaThamKhaoVND", "TonMau", "BaoHanhThang", "LinkAnh", "NguonSanPham", "LinkTrongProject", "SKU"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, row in enumerate(manifest["products"], 1):
            saved = ids.get(row["sku"], row)
            writer.writerow(dict(zip(fields, [index, row["name"], row["category_name"], row["brand"], row["price"], 10,
                row["warranty_months"], row["image_url"], row["source_url"], "http://127.0.0.1:5173/san-pham/" + saved["slug"], row["sku"]])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = run(args.manifest, args.apply)
    export_csv(checked_manifest(args.manifest), result)
    print(json.dumps({key: value for key, value in result.items() if key != "products"}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except Exception as error:
        # Driver exception strings may contain connection details. Never print credentials.
        print(json.dumps({"ok": False, "error_type": type(error).__name__,
                          "message": str(error) if isinstance(error, (ValueError, AssertionError)) else "Nhập mẫu không hoàn thành; transaction chưa commit sẽ được hoàn tác."}, ensure_ascii=False), flush=True)
        raise SystemExit(1)
