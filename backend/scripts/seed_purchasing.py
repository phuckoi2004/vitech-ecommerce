"""Nhà cung cấp theo hãng và phiếu nhập đã nhận hàng cho mọi phiên bản đang bán, qua đúng nghiệp vụ.

Mỗi hãng một nhà cung cấp (dùng lại nhà cung cấp đã có cùng tên hãng). Mỗi hãng một phiếu nhập do Admin lập
(duyệt ngay), Staff nhận đủ hàng: tồn kho tăng --quantity mỗi phiên bản, giá nhập tính bình quân gia quyền như
khi nhập hàng thật. Đơn giá nhập = giá nhập hiện tại (CostPrice) nên giá nhập bình quân không đổi.

Mặc định chỉ xem trước; --apply mới ghi. Chạy lại bỏ qua hãng đã có phiếu của đợt này, không nhập trùng.
Liên hệ của nhà cung cấp mới ghi "Đang cập nhật": hãy sửa số điện thoại, địa chỉ, mã số thuế thật ở trang admin.
"""
import argparse
import json
import re
import sys
import unicodedata
from decimal import Decimal
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import func, select
from app.database import SessionLocal
from app.models import Brand, Product, ProductVariant, PurchaseOrder, Supplier, User
from app.schemas import PurchaseOrderCreate, PurchaseOrderItemCreate, PurchaseOrderReceive, PurchaseOrderReceiveItem, SupplierCreate
from app.services.actor import Actor
from app.services.purchasing import PurchaseOrderService, SupplierService

BATCH = "purchasing-seed-v1"
PENDING_INFO = "Đang cập nhật"


def code_of(brand_name):
    ascii_name = unicodedata.normalize("NFKD", brand_name).encode("ascii", "ignore").decode()
    return "NPP-" + re.sub(r"[^A-Z0-9]+", "-", ascii_name.upper()).strip("-")


def active_user(session, role):
    return session.scalar(select(User).where(User.Role == role, User.AccountStatus == "Active", User.IsDeleted.is_(False))
                          .order_by(User.CreatedAt).limit(1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--quantity", type=int, default=5, help="số lượng nhập mỗi phiên bản (mặc định 5)")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.quantity < 1:
        parser.error("--quantity phải lớn hơn 0")

    with SessionLocal() as session:
        rows = session.execute(
            select(Brand, ProductVariant).join(Product, Product.BrandId == Brand.BrandId)
            .join(ProductVariant, ProductVariant.ProductId == Product.ProductId)
            .where(Product.IsDeleted.is_(False), ProductVariant.IsDeleted.is_(False), ProductVariant.IsActive.is_(True))
            .order_by(Brand.Name, ProductVariant.Sku)).all()
        by_brand, skipped = {}, []
        for brand, variant in rows:
            if variant.CostPrice is None or variant.CostPrice <= 0:
                skipped.append(variant.Sku)  # chưa có giá nhập đầu kỳ: nhập hàng sẽ bị từ chối
                continue
            by_brand.setdefault(brand.Name, []).append(variant)

        suppliers = {s.Name.casefold(): s for s in session.scalars(select(Supplier))}
        seeded = {supplier_id for (supplier_id,) in session.execute(
            select(PurchaseOrder.SupplierId).where(PurchaseOrder.Note.like(f"[{BATCH}]%")))}
        plan = []
        for brand_name, variants in by_brand.items():
            supplier = suppliers.get(brand_name.casefold()) or session.scalar(
                select(Supplier).where(Supplier.SupplierCode == code_of(brand_name)))
            plan.append(dict(Brand=brand_name, Supplier=supplier.Name if supplier else f"Nhà phân phối {brand_name}",
                             SupplierCode=supplier.SupplierCode if supplier else code_of(brand_name),
                             NewSupplier=supplier is None, AlreadySeeded=bool(supplier and supplier.SupplierId in seeded),
                             Variants=len(variants),
                             Amount=str(sum(v.CostPrice * args.quantity for v in variants))))
        report = dict(Batch=BATCH, Apply=args.apply, QuantityPerVariant=args.quantity, Brands=len(plan),
                      NewSuppliers=sum(p["NewSupplier"] for p in plan),
                      PurchaseOrders=sum(not p["AlreadySeeded"] for p in plan),
                      Units=sum(p["Variants"] * args.quantity for p in plan if not p["AlreadySeeded"]),
                      SkippedVariantsWithoutCost=skipped, Plan=plan,
                      StockBefore=session.scalar(select(func.sum(ProductVariant.StockQuantity))))

        if args.apply:
            admin, staff = active_user(session, "Admin"), active_user(session, "Staff")
            if admin is None:
                raise RuntimeError("Cần một tài khoản Admin đang hoạt động để lập phiếu nhập.")
            admin_actor = Actor(admin.UserId, "Admin")
            receiver = Actor(staff.UserId, "Staff") if staff else admin_actor
            supplier_service, po_service = SupplierService(session), PurchaseOrderService(session)
            created = []
            for entry in plan:
                if entry["AlreadySeeded"]:
                    continue
                variants = by_brand[entry["Brand"]]
                # Mỗi hãng một transaction: tạo nhà cung cấp (nếu thiếu), lập phiếu, nhận đủ hàng; lỗi thì không ghi gì.
                with po_service.transaction():
                    supplier = suppliers.get(entry["Brand"].casefold()) or session.scalar(
                        select(Supplier).where(Supplier.SupplierCode == entry["SupplierCode"]))
                    supplier_id = supplier.SupplierId if supplier else supplier_service.create_supplier(admin_actor, SupplierCreate(
                        SupplierCode=entry["SupplierCode"], Name=entry["Supplier"], PhoneNumber=PENDING_INFO,
                        Address=PENDING_INFO, IsActive=True,
                        Note=f"[{BATCH}] Nhà cung cấp mẫu cho hàng {entry['Brand']}. Cập nhật liên hệ, mã số thuế thật.")).SupplierId
                    po = po_service.create_purchase_order(admin_actor, PurchaseOrderCreate(
                        SupplierId=supplier_id, Note=f"[{BATCH}] Nhập hàng {entry['Brand']}: {len(variants)} phiên bản × {args.quantity}.",
                        Items=[PurchaseOrderItemCreate(ProductVariantId=v.ProductVariantId, OrderedQuantity=args.quantity,
                                                       UnitPrice=v.CostPrice) for v in variants]))
                    done = po_service.receive_items(receiver, po.PurchaseOrderId, PurchaseOrderReceive(
                        Items=[PurchaseOrderReceiveItem(PurchaseOrderItemId=i.PurchaseOrderItemId, Quantity=i.OrderedQuantity)
                               for i in po.Items], Note="Nhận đủ hàng theo phiếu."))
                created.append(dict(Brand=entry["Brand"], PurchaseOrderCode=done.PurchaseOrderCode, Status=done.Status,
                                    TotalAmount=str(done.TotalAmount)))
            report["Created"] = created
            report["StockAfter"] = session.scalar(select(func.sum(ProductVariant.StockQuantity)))

        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = {k: v for k, v in report.items() if k not in ("Plan", "Created")}
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
