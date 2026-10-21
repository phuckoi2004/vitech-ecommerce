"""Add test offers to existing products without changing prices/cost/stock/orders.

Default: dry-run. --apply adds only missing deterministic test records. A rerun
never resets coupon usage or edits an existing offer. Cancel [TEST] offers in admin
to stop them. Requires migration 82d6f1a9b407.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import SessionLocal
from app.models import Coupon, Product, Promotion, User
from app.schemas.promotion import CouponCreate, PromotionCreate
from app.services.actor import Actor
from app.services.promotion import CouponService, PromotionService

BATCH = "public-pricing-test-v1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    groups = {"2000000": [], "200000": [], "100000": [], "50000": [], "10000": []}
    skipped, examples = [], []
    with SessionLocal() as session:
        products = session.scalars(select(Product).where(Product.Status == "Active", Product.IsDeleted.is_(False))
                                   .options(selectinload(Product.variants)).order_by(Product.Slug)).all()
        for product in products:
            variants = [v for v in product.variants if v.IsActive and not v.IsDeleted]
            if not variants:
                continue
            lowest = min(v.Price for v in variants)
            amount = "2000000" if lowest >= 20000000 else "200000" if lowest >= 2000000 else "100000"
            if all(v.CostPrice > 0 for v in variants):
                headroom = min(v.Price - v.CostPrice for v in variants)
                if headroom < Decimal(amount):
                    amount = next((fallback for fallback in ("50000", "10000") if headroom >= Decimal(fallback)), amount)
            if any(v.CostPrice <= 0 or v.Price - Decimal(amount) < v.CostPrice for v in variants):
                skipped.append(product.Slug)
                continue
            groups[amount].append(product.ProductId)
            if len([entry for entry in examples if entry["Discount"] == amount]) < 2:
                variant = min(variants, key=lambda v: v.Price)
                examples.append(dict(Product=product.Name, Path=f"/san-pham/{product.Slug}",
                                     ProductVariantId=str(variant.ProductVariantId), OriginalPrice=str(variant.Price),
                                     SalePrice=str(variant.Price - Decimal(amount)), Discount=amount))
        report = dict(Batch=BATCH, Apply=args.apply, ProductsPerDiscount={k: len(v) for k, v in groups.items()},
                      SkippedProducts=skipped, Examples=examples, CreatedPromotions=0, CreatedCoupons=0,
                      Coupons=["TEST300K", "TEST100K", "TEST10P", "TESTHETLUOT", "TESTSAPTOI"],
                      StartsAt=now.isoformat(), EndsAt=(now + timedelta(days=60)).isoformat())
        if args.apply:
            admin = session.scalar(select(User).where(User.Role == "Admin", User.AccountStatus == "Active")
                                   .order_by(User.CreatedAt).limit(1))
            if admin is None:
                raise RuntimeError("Cần một tài khoản Admin đang hoạt động để ghi nhận người tạo.")
            actor = Actor(admin.UserId, "Admin")
            promotions, coupons = PromotionService(session), CouponService(session)

            def ensure_program(key, mode, amount, *, targets=(), kind="FixedAmount", minimum="0", cap=None, upcoming=False):
                name = f"[TEST] {BATCH} · {key}"
                existing = session.scalar(select(Promotion).where(Promotion.Name == name))
                if existing is not None:
                    return existing.PromotionId
                data = PromotionCreate(Name=name, Description="Dữ liệu thử giảm trực tiếp và mã công khai; có thể hủy chương trình sau khi thử.",
                    ApplyMode=mode, DiscountType=kind, DiscountValue=amount, MinOrderValue=minimum,
                    MaxDiscountAmount=cap, Status="Scheduled", ProductIds=list(targets),
                    StartDate=now + timedelta(days=1) if upcoming else now - timedelta(minutes=1),
                    EndDate=now + timedelta(days=60))
                result = promotions.create_promotion(actor, data)
                report["CreatedPromotions"] += 1
                return result.PromotionId

            with promotions.transaction():
                for amount, targets in groups.items():
                    if targets:
                        ensure_program(f"Giảm trực tiếp {int(amount):,}đ", "Automatic", amount, targets=targets)
                for code, amount, minimum, limit, kind, cap, upcoming in (
                    ("TEST300K", "300000", "20000000", 100, "FixedAmount", None, False),
                    ("TEST100K", "100000", "2000000", 100, "FixedAmount", None, False),
                    ("TEST10P", "10", "500000", 20, "Percentage", "50000", False),
                    ("TESTHETLUOT", "50000", "1000000", 0, "FixedAmount", None, False),
                    ("TESTSAPTOI", "50000", "1000000", 10, "FixedAmount", None, True),
                ):
                    if session.scalar(select(Coupon.CouponId).where(Coupon.Code == code)) is not None:
                        continue
                    program_id = ensure_program(code, "Coupon", amount, minimum=minimum, kind=kind, cap=cap, upcoming=upcoming)
                    coupons.create_coupon(actor, CouponCreate(PromotionId=program_id, Code=code,
                        Name=f"[TEST] Ưu đãi {code}", UsageLimit=limit))
                    report["CreatedCoupons"] += 1
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        # stdout may use a non-Unicode Windows terminal.
        print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
