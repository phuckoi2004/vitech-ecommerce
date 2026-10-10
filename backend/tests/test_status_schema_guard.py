"""Đợt 5.10: schema cho phép client đặt thẳng trạng thái không được nối vào nghiệp vụ/API.

OrderPaymentStatusUpdate và PurchaseOrderStatusUpdate được giữ lại (đang export trong app.schemas, chưa có quyết định
xóa) nhưng không mã nào ngoài app/schemas được dùng: PaymentStatus và trạng thái phiếu nhập chỉ đổi qua các use case có
kiểm tra (PaymentService, OrderService.confirm_cod_delivery, PurchaseOrderService). Test quét cả thư mục app/ nên mọi
Router thêm sau này cũng bị kiểm tra.
"""

import ast
import pathlib
import unittest

import app.schemas

APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "app"
FORBIDDEN = {"OrderPaymentStatusUpdate", "PurchaseOrderStatusUpdate"}


def names_used(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.alias):
            used.add(node.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            used.add(node.value)  # getattr(schemas, "…") / chuỗi chú thích kiểu
    return used


class StatusSchemaGuardTest(unittest.TestCase):
    def test_direct_status_schemas_are_not_used_outside_schemas(self):
        offenders = {
            str(path.relative_to(APP_DIR)): sorted(names_used(path) & FORBIDDEN)
            for path in APP_DIR.rglob("*.py")
            if "schemas" not in path.relative_to(APP_DIR).parts and names_used(path) & FORBIDDEN
        }
        self.assertEqual(offenders, {})

    def test_schemas_are_kept_and_documented_as_not_for_direct_wiring(self):
        for name in sorted(FORBIDDEN):
            with self.subTest(schema=name):
                schema = getattr(app.schemas, name)
                self.assertIn(name, app.schemas.__all__)
                self.assertIn("KHÔNG nối trực tiếp vào API", schema.__doc__)


if __name__ == "__main__":
    unittest.main()
