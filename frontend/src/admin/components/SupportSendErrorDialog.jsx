import Modal from './Modal.jsx'
import Button from '../../components/shared/Button.jsx'

export default function SupportSendErrorDialog({ failure, busy, canRetry, onClose, onRetry }) {
  const message = [400, 403, 404, 409].includes(failure.status) && failure.message
    ? failure.message
    : 'Tin nhắn gửi đi thất bại. Vui lòng kiểm tra kết nối và thử lại.'
  return <Modal open title="Không gửi được tin nhắn" variant="support-send-error" className="min-h-[230px] w-[460px]" busy={busy} onClose={onClose}>
    <p role="alert" className="m-0 text-[10px] leading-3 break-words text-admin-muted">{message}</p>
    <div className="mt-3 flex h-10 items-center justify-end">
      <Button variant="secondary" className="h-8! w-14 cursor-pointer rounded-lg border border-admin-border! bg-white! px-3.5! font-admin! text-[10px]! text-admin-text!" disabled={busy} onClick={onClose}>Đóng</Button>
      <Button className="h-[30px]! min-w-[61px] cursor-pointer rounded-lg bg-admin-blue! px-3.5! font-admin! text-[10px]! text-white!" disabled={busy || !canRetry} onClick={onRetry}>{busy ? 'Đang gửi…' : 'Thử lại'}</Button>
    </div>
  </Modal>
}
