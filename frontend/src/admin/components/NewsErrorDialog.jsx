import Modal from './Modal.jsx'

export default function NewsErrorDialog({ failure, onClose }) {
  return <Modal variant="news-error" open title={failure.title || 'Không thể cập nhật tin tức'} onClose={onClose} className="w-[470px]">
    <p className="m-0 w-full text-center text-[10px] leading-3 text-admin-muted">Hệ thống gặp lỗi khi thay đổi dữ liệu. Dữ liệu cũ được giữ nguyên.</p>
    {failure.message && <p role="alert" className="mt-2 mb-0 text-center text-[10px] leading-3 break-words text-admin-muted">{failure.message}</p>}
    <button type="button" aria-label="Đóng thông báo" onClick={onClose} className="absolute top-2.5 right-3 cursor-pointer border-0 bg-transparent px-1 text-base text-admin-muted hover:text-admin-blue">×</button>
  </Modal>
}
