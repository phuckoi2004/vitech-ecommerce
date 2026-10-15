import Modal from './Modal.jsx'
import { PaymentButton } from './PaymentMethodUi.jsx'

export default function PaymentResultDialog({ success = false, message, deleting = false, busy = false, onClose, onRetry }) {
  return <Modal variant={success ? 'payment-success' : 'payment-error'} open title={success ? 'Cập nhật thành công' : 'Thay đổi thất bại'} className="min-h-[220px] w-[460px]" busy={busy} onClose={onClose}>
    <p role={success ? 'status' : undefined} className="m-0 text-[10px] leading-3 text-admin-muted">{success ? 'Hệ thống đã lưu thay đổi của Quản trị viên đối với phương thức thanh toán.' : deleting ? 'Hệ thống không thể xóa phương thức thanh toán. Vui lòng thử lại.' : 'Hệ thống không thể lưu thay đổi phương thức thanh toán. Vui lòng thử lại.'}</p>
    {!success && message && <p role="alert" className="mt-2 mb-0 text-[10px] leading-3 break-words text-admin-red">{message}</p>}
    <div className="mt-2.5 flex justify-end"><PaymentButton secondary className="text-admin-text!" disabled={busy} onClick={onClose}>Đóng</PaymentButton>{!success && onRetry && <PaymentButton loading={busy} onClick={onRetry}>Thử lại</PaymentButton>}</div>
  </Modal>
}
