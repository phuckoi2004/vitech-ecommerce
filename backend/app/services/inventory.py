"""Inventory service: tồn đầu kỳ (Opening), điều chỉnh kho thủ công, giá vốn bình quân gia quyền, Serial/IMEI khi nhận hàng.

Quyết định đã chốt (docs/business-requirements.md mục 5, 8 và các quyết định của người dùng):
- StockQuantity giữ mô hình hiện tại (tồn khả dụng); chưa tách tồn vật lý/khả dụng.
- Opening là nghiệp vụ riêng, chỉ Admin, mỗi biến thể một lần: đặt StockQuantity = Quantity, CostPrice = UnitCost.
- Điều chỉnh kho thủ công chỉ Admin, có lịch sử (StockAdjustments), không tạo tồn âm, không đổi giá vốn.
- Giá vốn bình quân gia quyền khi nhận hàng:
      CostPrice mới = (Tồn trước × CostPrice trước + SL nhận × Đơn giá nhập) / (Tồn trước + SL nhận)
  tính bằng Decimal, làm tròn 2 chữ số ROUND_HALF_UP (numeric(15,2)), trên dòng biến thể đã khóa (FOR UPDATE).
- Không nhận hàng khi biến thể còn tồn mà chưa có giá vốn hợp lệ (CostPrice = 0 chưa qua Opening/nhập hàng).
- Hủy đơn bán chỉ hoàn tồn, không đổi giá vốn (ProductVariantService.change_stock).
- Serial/IMEI: bắt buộc với biến thể IsSerialTracked; trim đầu/cuối, phân biệt hoa thường, không kiểm tra Luhn;
  không trùng trong yêu cầu và với database (UNIQUE SerialNumber). Serial chỉ được tạo qua nhận hàng, tồn đầu kỳ
  hoặc điều chỉnh tăng (không có CRUD tạo/xóa serial).
- Serial thuộc phiếu điều chỉnh được ghi vào StockAdjustmentSerials: Opening/Increase → In, Decrease → Out.
  Điều chỉnh giảm chuyển serial sang WrittenOff (loại khỏi tồn kho); chỉ serial Available, chưa gắn đơn.
  Tồn kho, trạng thái serial, phiếu điều chỉnh và liên kết serial nằm trong cùng một transaction.
"""

import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import ProductSerial, ProductVariant, StockAdjustment
from app.models.inventory import (
    ADJUSTMENT_DECREASE,
    ADJUSTMENT_INCREASE,
    ADJUSTMENT_OPENING,
    SERIAL_DIRECTION_IN,
    SERIAL_DIRECTION_OUT,
    STOCK_ADJUSTMENT_TYPES,
)
from app.repositories import (
    ProductSerialRepository,
    ProductVariantRepository,
    PurchaseOrderItemRepository,
    StockAdjustmentRepository,
    StockAdjustmentSerialRepository,
)
from app.schemas import (
    LowStockVariantResponse,
    PageResponse,
    StockAdjustmentCreate,
    StockAdjustmentResponse,
    StockOpeningCreate,
)

from .actor import ADMIN_ONLY, STAFF_OR_ADMIN, Actor, require_role
from .base import BaseService, utc_now
from .catalog import ProductVariantService, normalize_serial_number
from .exceptions import BusinessRuleError, ConflictError, NotFoundError
from .promotion import money

SERIAL_AVAILABLE = "Available"
# Serial bị loại khỏi tồn kho qua phiếu điều chỉnh giảm (chỉ dùng khi hàng thực sự rời khỏi tồn kho).
SERIAL_WRITTEN_OFF = "WrittenOff"


def weighted_average_cost(stock_before: int, cost_before: Decimal, quantity: int, unit_price: Decimal) -> Decimal:
    """Giá vốn bình quân gia quyền sau khi nhận ``quantity`` đơn vị giá ``unit_price`` (Decimal, làm tròn 2 chữ số)."""
    if stock_before < 0 or quantity <= 0:
        raise BusinessRuleError("Số lượng không hợp lệ khi tính giá vốn", code="invalid_cost_quantity")
    if cost_before < 0 or unit_price < 0:
        raise BusinessRuleError("Giá vốn/đơn giá nhập không được âm", code="invalid_unit_price")
    value = Decimal(stock_before) * cost_before + Decimal(quantity) * unit_price
    return money(value / Decimal(stock_before + quantity))


@dataclass
class ReceiptLine:
    """Một biến thể được nhận trong một lần nhận hàng (đã cộng dồn theo dòng phiếu nhập)."""

    variant_id: uuid.UUID
    quantity: int
    unit_price: Decimal
    serial_numbers: list[str] = field(default_factory=list)


class InventoryService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.variants = ProductVariantRepository(session)
        self.adjustments = StockAdjustmentRepository(session)
        self.purchase_items = PurchaseOrderItemRepository(session)
        self.serials = ProductSerialRepository(session)
        self.serial_links = StockAdjustmentSerialRepository(session)
        self.variant_service = ProductVariantService(session, clock=clock)

    # ------------------------------------------------------------------ Opening

    def declare_opening(self, actor: Actor, variant_id: uuid.UUID, data: StockOpeningCreate) -> StockAdjustmentResponse:
        """Admin khai báo tồn đầu kỳ (một lần cho mỗi biến thể, trước khi biến thể phát sinh nhập hàng).

        Trong một transaction: khóa biến thể → kiểm tra chưa khai báo/chưa nhập hàng → ghi serial (nếu quản lý serial)
        → đặt StockQuantity, CostPrice → ghi lịch sử Opening. Gọi lặp bị chặn (kiểm tra trên dòng đã khóa và
        unique index UX_StockAdjustments_Opening_ProductVariantId).
        """
        require_role(actor, *ADMIN_ONLY)
        quantity, unit_cost = data.Quantity, data.UnitCost
        if quantity is None or quantity < 0:
            raise BusinessRuleError("Số lượng tồn đầu kỳ không được âm", code="invalid_opening_quantity")
        if unit_cost is None or unit_cost < 0 or unit_cost != money(unit_cost):
            raise BusinessRuleError("Giá vốn đầu kỳ không hợp lệ", code="invalid_opening_cost")
        reason = self._reason(data.Reason)
        serials = self._normalize_serials(data.SerialNumbers)
        with self.transaction():
            variant = self._lock_variant(variant_id)
            if self.adjustments.has_opening(variant_id):
                raise ConflictError("Biến thể đã khai báo tồn đầu kỳ", code="opening_already_declared")
            if self.purchase_items.has_received_for_variant(variant_id):
                raise BusinessRuleError(
                    "Biến thể đã phát sinh nhập hàng, không khai báo tồn đầu kỳ", code="opening_after_receipt"
                )
            if variant.IsSerialTracked:
                available = self.serials.count_by_variant(variant_id, status=SERIAL_AVAILABLE)
                if available + len(serials) != quantity:
                    raise BusinessRuleError(
                        f"Số Serial/IMEI khả dụng ({available} hiện có + {len(serials)} mới) phải bằng số lượng tồn đầu kỳ ({quantity})",
                        code="serial_count_mismatch",
                    )
                self._register_serials(variant_id, serials)
            elif serials:
                raise BusinessRuleError("Biến thể không quản lý Serial/IMEI", code="serials_not_allowed")

            before_quantity, before_cost = variant.StockQuantity, variant.CostPrice
            variant.StockQuantity = quantity
            variant.CostPrice = money(unit_cost)
            record = self._record(actor, variant, ADJUSTMENT_OPENING, before_quantity, before_cost, reason)
            if variant.IsSerialTracked:
                # Serial khả dụng (mới + có sẵn từ trước) được tính vào tồn đầu kỳ → liên kết In (nếu chưa có).
                in_stock = self.serials.list_by_variant(variant_id, status=SERIAL_AVAILABLE)
                linked = self.serial_links.linked_serial_ids([s.ProductSerialId for s in in_stock], SERIAL_DIRECTION_IN)
                self._link_serials(record, [s for s in in_stock if s.ProductSerialId not in linked], SERIAL_DIRECTION_IN)
            self.variant_service.alert_if_low_stock(variant, before_quantity)
            self.adjustments.flush()
            return StockAdjustmentResponse.model_validate(record)

    # ------------------------------------------------------------------ Điều chỉnh thủ công

    def adjust_stock(self, actor: Actor, variant_id: uuid.UUID, data: StockAdjustmentCreate) -> StockAdjustmentResponse:
        """Admin điều chỉnh tồn kho (QuantityChange > 0 tăng, < 0 giảm); giá vốn giữ nguyên; có lịch sử.

        Không cho tồn âm. Tăng tồn cần giá vốn hợp lệ (khai báo tồn đầu kỳ/nhập hàng trước).
        Biến thể IsSerialTracked: SerialNumbers phải đúng bằng |QuantityChange|.
        - Tăng: serial mới (chưa tồn tại), ghi Available + liên kết In với phiếu.
        - Giảm: serial phải thuộc biến thể, đang Available, chưa gắn dòng đơn và chưa từng bị loại khỏi kho →
          WrittenOff + liên kết Out với phiếu.
        Khóa biến thể rồi serial (thứ tự SerialNumber); tồn kho, serial, phiếu và liên kết cùng một transaction:
        lỗi ở bất kỳ bước nào thì rollback toàn bộ. Hai phiếu đồng thời trên cùng serial: phiếu sau chờ khóa rồi
        thấy serial không còn Available (UNIQUE ProductSerialId + Direction là lớp chặn cuối ở database).
        """
        require_role(actor, *ADMIN_ONLY)
        change = data.QuantityChange
        if not isinstance(change, int) or change == 0:
            raise BusinessRuleError("Số lượng điều chỉnh phải khác 0", code="invalid_adjustment_quantity")
        reason = self._reason(data.Reason)
        serials = self._normalize_serials(getattr(data, "SerialNumbers", None))
        with self.transaction():
            variant = self._lock_variant(variant_id)
            before_quantity = variant.StockQuantity
            after_quantity = before_quantity + change
            if after_quantity < 0:
                raise BusinessRuleError(
                    f"Điều chỉnh làm tồn kho âm (hiện có {before_quantity})", code="insufficient_stock"
                )
            if change > 0 and not self._has_cost_basis(variant):
                raise BusinessRuleError(
                    "Biến thể chưa có giá vốn; khai báo tồn đầu kỳ trước khi tăng tồn", code="opening_required"
                )
            affected: list[ProductSerial] = []
            if variant.IsSerialTracked:
                if len(serials) != abs(change):
                    raise BusinessRuleError(
                        f"Cần đúng {abs(change)} Serial/IMEI cho điều chỉnh (nhận được {len(serials)})",
                        code="serial_count_mismatch",
                    )
                if change > 0:
                    affected = self._register_serials(variant.ProductVariantId, serials)
                else:
                    affected = self._remove_serials_from_stock(variant, serials)
            elif serials:
                raise BusinessRuleError("Biến thể không quản lý Serial/IMEI", code="serials_not_allowed")
            variant.StockQuantity = after_quantity
            adjustment_type = ADJUSTMENT_INCREASE if change > 0 else ADJUSTMENT_DECREASE
            record = self._record(actor, variant, adjustment_type, before_quantity, variant.CostPrice, reason)
            self._link_serials(record, affected, SERIAL_DIRECTION_IN if change > 0 else SERIAL_DIRECTION_OUT)
            self.variant_service.alert_if_low_stock(variant, before_quantity)
            self.adjustments.flush()
            return StockAdjustmentResponse.model_validate(record)

    def list_adjustments(
        self,
        actor: Actor,
        *,
        variant_id: uuid.UUID | None = None,
        adjustment_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PageResponse[StockAdjustmentResponse]:
        require_role(actor, *ADMIN_ONLY)
        if adjustment_type is not None and adjustment_type not in STOCK_ADJUSTMENT_TYPES:
            raise BusinessRuleError(f"AdjustmentType không hợp lệ: {adjustment_type}", code="invalid_adjustment_type")
        offset, limit = self._page_args(page, page_size)
        filters = {"variant_id": variant_id, "adjustment_type": adjustment_type}
        items = self.adjustments.list_adjustments(**filters, offset=offset, limit=limit)
        return PageResponse[StockAdjustmentResponse](
            Items=[StockAdjustmentResponse.model_validate(a) for a in items],
            Total=self.adjustments.count_adjustments(**filters),
            Page=page,
            PageSize=page_size,
        )

    def list_low_stock(self, actor: Actor, *, page: int = 1, page_size: int = 20) -> PageResponse[LowStockVariantResponse]:
        """Danh sách biến thể StockQuantity <= MinStockLevel (MinStockLevel > 0). Chỉ đọc, không tạo thông báo."""
        require_role(actor, *STAFF_OR_ADMIN)
        offset, limit = self._page_args(page, page_size)
        items = self.variants.list_low_stock(offset=offset, limit=limit)
        return PageResponse[LowStockVariantResponse](
            Items=[LowStockVariantResponse.model_validate(v) for v in items],
            Total=self.variants.count_low_stock(),
            Page=page,
            PageSize=page_size,
        )

    # ------------------------------------------------------------------ Nhận hàng (nội bộ, dùng bởi PurchaseOrderService)

    def receive_purchase_lines(self, lines: Sequence[ReceiptLine]) -> None:
        """Cộng tồn, tính giá vốn bình quân gia quyền và ghi Serial/IMEI cho một lần nhận hàng.

        Tham gia transaction của use case gọi nó (đã khóa phiếu nhập). Khóa biến thể theo thứ tự id; kiểm tra
        toàn bộ dòng trước khi thay đổi; lỗi ở bất kỳ dòng nào thì use case rollback toàn bộ.
        """
        self.require_enclosing_use_case()
        if not lines:
            raise BusinessRuleError("Phải có ít nhất một dòng nhận hàng", code="receive_items_empty")
        by_variant: dict[uuid.UUID, ReceiptLine] = {}
        for line in lines:
            if line.variant_id in by_variant:
                raise BusinessRuleError("Một biến thể chỉ nhận một dòng trong mỗi lần", code="duplicate_variant")
            if line.quantity <= 0:
                raise BusinessRuleError("Số lượng nhận phải lớn hơn 0", code="invalid_receive_quantity")
            if line.unit_price is None or line.unit_price < 0:
                raise BusinessRuleError("Đơn giá nhập không được âm", code="invalid_unit_price")
            by_variant[line.variant_id] = line

        with self.transaction():
            locked = {v.ProductVariantId: v for v in self.variants.get_many_by_ids_for_update(by_variant.keys())}
            missing = set(by_variant) - set(locked)
            if missing:
                raise NotFoundError(f"Không tìm thấy biến thể: {sorted(map(str, missing))}", code="variant_not_found")

            serials_by_variant: dict[uuid.UUID, list[str]] = {}
            for variant_id in sorted(by_variant):
                line, variant = by_variant[variant_id], locked[variant_id]
                if variant.StockQuantity > 0 and not self._has_cost_basis(variant):
                    raise BusinessRuleError(
                        f"Biến thể {variant.Sku} còn tồn nhưng chưa có giá vốn đầu kỳ; khai báo tồn đầu kỳ trước khi nhận hàng",
                        code="opening_required",
                    )
                serials = self._normalize_serials(line.serial_numbers)
                if variant.IsSerialTracked and len(serials) != line.quantity:
                    raise BusinessRuleError(
                        f"Biến thể {variant.Sku} cần đúng {line.quantity} Serial/IMEI (nhận được {len(serials)})",
                        code="serial_count_mismatch",
                    )
                if not variant.IsSerialTracked and serials:
                    raise BusinessRuleError(
                        f"Biến thể {variant.Sku} không quản lý Serial/IMEI", code="serials_not_allowed"
                    )
                serials_by_variant[variant_id] = serials
            self._ensure_new_serials([s for serials in serials_by_variant.values() for s in serials])

            for variant_id in sorted(by_variant):
                line, variant = by_variant[variant_id], locked[variant_id]
                variant.CostPrice = weighted_average_cost(
                    variant.StockQuantity, variant.CostPrice, line.quantity, line.unit_price
                )
                variant.StockQuantity += line.quantity
                self._create_serials(variant_id, serials_by_variant[variant_id])
            self.variants.flush()

    # ------------------------------------------------------------------ helpers

    def _lock_variant(self, variant_id: uuid.UUID) -> ProductVariant:
        locked = self.variants.get_many_by_ids_for_update([variant_id])
        if not locked or locked[0].IsDeleted:
            raise NotFoundError("Không tìm thấy biến thể", code="variant_not_found")
        return locked[0]

    def _has_cost_basis(self, variant: ProductVariant) -> bool:
        """Giá vốn hợp lệ: CostPrice > 0, hoặc đã khai báo tồn đầu kỳ, hoặc đã từng nhận hàng mua vào."""
        return (
            variant.CostPrice > 0
            or self.adjustments.has_opening(variant.ProductVariantId)
            or self.purchase_items.has_received_for_variant(variant.ProductVariantId)
        )

    @staticmethod
    def _reason(value: str | None) -> str:
        reason = (value or "").strip()
        if not reason:
            raise BusinessRuleError("Phải nhập lý do", code="reason_required")
        return reason

    @staticmethod
    def _normalize_serials(values: Iterable[str] | None) -> list[str]:
        serials = [normalize_serial_number(value) for value in (values or [])]
        duplicates = sorted({s for s in serials if serials.count(s) > 1})
        if duplicates:
            raise BusinessRuleError(f"Serial/IMEI bị trùng trong yêu cầu: {duplicates}", code="duplicate_serial_in_request")
        return serials

    def _ensure_new_serials(self, serials: list[str]) -> None:
        duplicates = sorted({s for s in serials if serials.count(s) > 1})
        if duplicates:
            raise BusinessRuleError(f"Serial/IMEI bị trùng trong yêu cầu: {duplicates}", code="duplicate_serial_in_request")
        existing = self.serials.find_existing_serial_numbers(serials)
        if existing:
            raise ConflictError(f"Serial/IMEI đã tồn tại: {sorted(existing)}", code="serial_exists")

    def _remove_serials_from_stock(self, variant: ProductVariant, serials: list[str]) -> list[ProductSerial]:
        """Khóa và kiểm tra serial được chọn để giảm tồn rồi chuyển WrittenOff (trả về theo thứ tự SerialNumber)."""
        locked = {s.SerialNumber: s for s in self.serials.list_by_serial_numbers_for_update(serials)}
        missing = sorted(s for s in serials if s not in locked)
        if missing:
            raise NotFoundError(f"Không tìm thấy Serial/IMEI: {missing}", code="serial_not_found")
        wrong_variant = sorted(s for s in serials if locked[s].ProductVariantId != variant.ProductVariantId)
        if wrong_variant:
            raise BusinessRuleError(
                f"Serial/IMEI không thuộc biến thể {variant.Sku}: {wrong_variant}", code="serial_variant_mismatch"
            )
        unavailable = sorted(
            s for s in serials if locked[s].Status != SERIAL_AVAILABLE or locked[s].OrderItemId is not None
        )
        if unavailable:
            raise BusinessRuleError(f"Serial/IMEI không còn tồn khả dụng: {unavailable}", code="serial_not_available")
        removed = [locked[s] for s in sorted(serials)]
        already_out = self.serial_links.linked_serial_ids([s.ProductSerialId for s in removed], SERIAL_DIRECTION_OUT)
        if already_out:
            numbers = sorted(s.SerialNumber for s in removed if s.ProductSerialId in already_out)
            raise ConflictError(f"Serial/IMEI đã bị loại khỏi kho trước đó: {numbers}", code="serial_already_adjusted")
        for serial in removed:
            serial.Status = SERIAL_WRITTEN_OFF
        return removed

    def _register_serials(self, variant_id: uuid.UUID, serials: list[str]) -> list[ProductSerial]:
        self._ensure_new_serials(serials)
        return self._create_serials(variant_id, serials)

    def _create_serials(self, variant_id: uuid.UUID, serials: list[str]) -> list[ProductSerial]:
        return [
            self.serials.create({"ProductVariantId": variant_id, "SerialNumber": serial, "Status": SERIAL_AVAILABLE})
            for serial in serials
        ]

    def _link_serials(self, record: StockAdjustment, serials: list[ProductSerial], direction: str) -> None:
        """Ghi serial thuộc phiếu điều chỉnh (flush trước để có khóa chính do database sinh)."""
        if not serials:
            return
        self.adjustments.flush()
        for serial in serials:
            self.serial_links.create(
                {
                    "StockAdjustmentId": record.StockAdjustmentId,
                    "ProductSerialId": serial.ProductSerialId,
                    "Direction": direction,
                }
            )

    def _record(
        self,
        actor: Actor,
        variant: ProductVariant,
        adjustment_type: str,
        quantity_before: int,
        cost_before: Decimal,
        reason: str,
    ):
        return self.adjustments.create(
            {
                "ProductVariantId": variant.ProductVariantId,
                "AdjustedByUserId": actor.user_id,
                "AdjustmentType": adjustment_type,
                "QuantityBefore": quantity_before,
                "QuantityChange": variant.StockQuantity - quantity_before,
                "QuantityAfter": variant.StockQuantity,
                "CostPriceBefore": cost_before,
                "CostPriceAfter": variant.CostPrice,
                "Reason": reason,
                "CreatedAt": self.now(),
            }
        )
