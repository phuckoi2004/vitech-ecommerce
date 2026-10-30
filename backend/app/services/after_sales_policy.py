"""Public after-sales wording shared by the storefront and AI, matching the active service workflows."""

from .returns import ReturnPolicy


WARRANTY_LINES = (
    "Thời hạn bảo hành tùy từng sản phẩm và được ghi trên trang sản phẩm, sản phẩm ghi 0 tháng không có bảo hành.",
    "Bảo hành tính từ ngày giao hàng thành công, theo số tháng được ghi nhận trong đơn hàng khi mua.",
    "Gửi yêu cầu trong Tài khoản → Bảo hành và đổi trả: chọn sản phẩm thuộc đơn đã giao, mô tả lỗi, chọn "
    "Serial/IMEI nếu có và đính kèm ảnh minh chứng nếu cần.",
    "VieTech tiếp nhận, kiểm tra và thông báo kết quả sửa chữa, thay linh kiện hoặc không thể bảo hành. "
    "Hiện chưa hỗ trợ đổi máy trong phiếu bảo hành.",
)
WARRANTY_REVIEW_LINE = (
    "Các tình trạng như rơi vỡ, vào nước hoặc đã tự ý can thiệp cần được nhân viên kiểm tra theo điều kiện "
    "bảo hành của từng sản phẩm, việc còn thời hạn không tự xác nhận mọi lỗi đều được bảo hành."
)
WARRANTY_TIMING_LINE = (
    "Thời gian xử lý và phí gửi/nhận bảo hành cần được nhân viên xác nhận theo từng trường hợp trước khi gửi máy."
)
RETURN_MODE_LINE = (
    "VieTech hiện tiếp nhận yêu cầu đổi sản phẩm, mỗi phiếu đổi 1 sản phẩm, chưa hỗ trợ yêu cầu trả hàng hoàn tiền mới."
)
RETURN_LINES = (
    "Mỗi yêu cầu đổi mới 1 sản phẩm: còn hàng thì đổi đúng phiên bản đã mua, nếu hết hàng, bạn có thể chọn sản phẩm "
    "khác cùng danh mục.",
    "Nếu chọn sản phẩm giá cao hơn, bạn thanh toán thêm phần chênh lệch, phần chênh lệch còn dư không được hoàn lại. "
    "Đơn đổi được miễn phí giao hàng tiêu chuẩn.",
    "VieTech đối chiếu chính sách, Serial/IMEI và tình trạng thực tế của sản phẩm rồi thông báo kết quả.",
)
RETURN_STEPS_LINE = (
    "Vào Tài khoản → Bảo hành và đổi trả → Tạo yêu cầu đổi trả, chọn sản phẩm trong đơn đã giao, "
    "chọn Serial/IMEI nếu có, mô tả lý do và đính kèm ảnh minh chứng nếu cần rồi gửi yêu cầu."
)
RETURN_CHECK_LINE = (
    "VieTech kiểm tra thời hạn, Serial/IMEI và tình trạng thực tế trước khi xác nhận, "
    "gửi yêu cầu không đồng nghĩa sản phẩm đã được chấp nhận đổi."
)


def return_window_line(days: int | None) -> str:
    window = (f"Gửi yêu cầu đổi trả trong {days} ngày kể từ ngày giao hàng (ngày giao là ngày thứ nhất)"
              if days else "Gửi yêu cầu đổi trả trong thời hạn ghi ở trang tạo yêu cầu")
    return window + ", cho sản phẩm thuộc đơn đã giao."


def store_policies(policy: ReturnPolicy) -> dict:
    """No account/catalog reads: the public window uses the same policy dependency as request creation."""
    return {
        "ReturnWindowDays": policy.window_days,
        "Warranty": [*WARRANTY_LINES, WARRANTY_REVIEW_LINE, WARRANTY_TIMING_LINE,
                     "Chỉ gửi yêu cầu cho sản phẩm của bạn. Sản phẩm hết hạn, không có bảo hành hoặc đang có "
                     "yêu cầu bảo hành/đổi trả chưa kết thúc sẽ được kiểm tra và phản hồi theo tình trạng tương ứng.",
                     "Ảnh minh chứng là tùy chọn. "
                     "Nhân viên liên hệ theo thông tin tài khoản để hướng dẫn gửi và nhận lại sản phẩm."],
        "Returns": [RETURN_MODE_LINE, return_window_line(policy.window_days), *RETURN_LINES[:2],
                    RETURN_STEPS_LINE, RETURN_CHECK_LINE,
                    "Sản phẩm phải thuộc đơn đã giao của chính bạn, đúng Serial/IMEI nếu có và không có phiếu "
                    "bảo hành/đổi trả đang xử lý trùng. Bạn có thể hủy trước khi chốt đơn đổi.",
                    "Thời gian xử lý và phí gửi sản phẩm cũ về cửa hàng cần được nhân viên xác nhận, "
                    "miễn phí giao hàng tiêu chuẩn nêu trên áp dụng cho đơn sản phẩm đổi gửi tới bạn.",
                    "Nếu bạn có phiếu trả hàng cũ, hãy xem kết quả trong tài khoản hoặc liên hệ nhân viên "
                    "để được kiểm tra riêng."],
    }


class StorePolicyService:
    """Read-only public settings; no session or customer data is required."""

    def __init__(self, policy: ReturnPolicy):
        self.policy = policy

    def get_store_policies(self) -> dict:
        return store_policies(self.policy)
