import { useEffect, useRef, useState } from 'react'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { formatDateTime } from '../../lib/format.js'
import useAdminQuery from '../hooks/useAdminQuery.js'
import { reviewTimestamp } from '../lib/reviews.js'
import { hideReview } from '../services/reviews.js'
import Modal from './Modal.jsx'
import { ReviewButton, ReviewImage, ReviewRating } from './ReviewUi.jsx'

function ReviewInfo({ label, children }) {
  return <div className="grid grid-cols-[165px_minmax(0,1fr)] gap-0 text-[10px] leading-3"><dt className="font-medium text-admin-muted">{label}</dt><dd className="m-0 min-w-0 break-words whitespace-pre-wrap">{children ?? '—'}</dd></div>
}

export default function ReviewDialog({ mode, reviewId, productName, onClose, onDone, onRefresh }) {
  const auth = useInternalAuth()
  const permitted = ['Admin', 'Staff'].includes(auth.user.Role) && auth.permissions.includes('reviews:view') && (mode === 'view' || (mode === 'delete' && auth.permissions.includes('reviews:delete')))
  const detail = useAdminQuery('/admin/reviews/' + encodeURIComponent(reviewId), {}, permitted)
  const review = detail.data
  const product = useAdminQuery('/admin/products/' + encodeURIComponent(review?.ProductId ?? ''), {}, permitted && Boolean(review) && !productName && auth.permissions.includes('products:view'))
  const name = productName ?? product.data?.Name
  const [reason, setReason] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [showError, setShowError] = useState(false)
  const writing = useRef(false), mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  async function confirm(event) {
    event.preventDefault()
    if (!permitted || mode !== 'delete' || !review || review.IsDeleted || !reason.trim() || writing.current) return
    writing.current = true; setBusy(true); setError('')
    try {
      await auth.withAccessToken((token) => hideReview(token, reviewId, reason.trim()))
      if (mounted.current) onDone('Đã ẩn đánh giá khỏi trang sản phẩm và cập nhật điểm đánh giá của sản phẩm.')
    } catch (failure) { if (mounted.current) { setError(failure.message); setShowError(true) } }
    finally { writing.current = false; if (mounted.current) setBusy(false) }
  }
  function dismissError() {
    setShowError(false); setError('')
    // A lost response does not prove that the server rolled back. Re-read before allowing a retry.
    detail.refresh(); onRefresh?.()
  }
  if (!permitted) return null
  if (showError) return <Modal open variant="review-error" className="w-[480px] min-h-[220px]" title="Không thể xóa đánh giá" onClose={dismissError}>
    <div className="flex flex-col gap-2.5"><p role="alert" className="m-0 text-[10px] leading-3 text-admin-muted">{error || 'Hệ thống gặp lỗi khi xóa.'} Vui lòng kiểm tra lại trạng thái đánh giá và thử lại.</p><div className="flex justify-end"><ReviewButton secondary onClick={dismissError}>Đóng</ReviewButton></div></div>
  </Modal>
  const deleting = mode === 'delete'
  const blocked = busy || detail.loading || Boolean(detail.error) || !review || review.IsDeleted || !reason.trim()
  return <Modal open variant={deleting ? 'review-delete' : 'review-detail'} className={deleting ? 'w-[500px] min-h-[390px]' : 'w-[560px] min-h-[560px]'} title={deleting ? 'Xóa đánh giá?' : 'Chi tiết đánh giá'} busy={busy} onClose={onClose}>
    {product.error && <ErrorState title="Chưa tải được tên sản phẩm" message={product.error} onRetry={product.refresh} className="py-2" />}
    {detail.loading ? <div className="flex flex-col gap-3"><LoadingState label="Đang tải đánh giá…" /><div className="flex justify-end"><ReviewButton secondary onClick={onClose}>Đóng</ReviewButton></div></div> : detail.error ? <div className="flex flex-col gap-3"><ErrorState title="Không tải được đánh giá" message={detail.error} onRetry={detail.refresh} /><div className="flex justify-end"><ReviewButton secondary onClick={onClose}>Đóng</ReviewButton></div></div> : review && (deleting ? <form id="review-hide-form" className="flex min-w-0 flex-col gap-3.5" onSubmit={confirm}>
      <p className="m-0 text-[10px] leading-3 text-admin-muted">Nhân viên và Quản trị viên phải nhập lý do trước khi xóa bình luận. Dữ liệu được xóa mềm và lưu người xóa, thời điểm xóa.</p>
      {review.IsDeleted ? <p role="status" className="m-0 text-[10px] leading-3 text-admin-muted">Đánh giá này đã được ẩn, không cần xóa lại.</p> : <label className="flex flex-col gap-[5px] text-[9px] leading-[11px] font-medium text-admin-muted">Lý do xóa *<input aria-label="Lý do xóa" type="text" required maxLength={2000} disabled={busy} className="h-[38px] w-full rounded-lg border border-admin-border bg-white px-2.5 text-[9px] font-normal text-admin-text placeholder:text-admin-muted disabled:opacity-60" placeholder="Nhập lý do xóa đánh giá" value={reason} onChange={(event) => setReason(event.target.value)} /></label>}
      <section aria-label="Đánh giá sẽ được xóa" className="flex min-w-0 flex-col gap-1 rounded-lg bg-admin-page p-2.5 text-[9px] leading-[11px]"><p className="m-0 font-semibold break-words">{name ?? (product.loading ? 'Đang tải…' : '—')} • <ReviewRating value={review.Rating} className="text-admin-text!" /></p><p className="m-0 break-words whitespace-pre-wrap text-admin-muted">“{review.Content || '—'}”</p></section>
      <div className="flex justify-end gap-0"><ReviewButton secondary disabled={busy} onClick={onClose}>Hủy</ReviewButton><ReviewButton type="submit" secondary className="border-admin-red! enabled:hover:bg-red-50!" disabled={blocked}><span className="text-admin-red">{busy ? 'Đang xử lý…' : 'Xác nhận xóa'}</span></ReviewButton></div>
    </form> : <div className="flex min-w-0 flex-col gap-3"><dl className="m-0 flex flex-col gap-3">
      <ReviewInfo label="Khách hàng">{review.User?.FullName ?? '—'}</ReviewInfo><ReviewInfo label="Sản phẩm">{name ?? (product.loading ? 'Đang tải…' : '—')}</ReviewInfo><ReviewInfo label="Số sao"><ReviewRating value={review.Rating} className="text-[10px]!" /></ReviewInfo><ReviewInfo label="Thời gian đánh giá">{reviewTimestamp(review.CreatedAt)}</ReviewInfo>
    </dl><section aria-label="Bình luận đầy đủ" className="flex min-w-0 flex-col gap-1.5"><h3 className="m-0 text-[10px] leading-3 font-medium text-admin-muted">Nội dung bình luận</h3><p className="m-0 min-h-[100px] max-h-[240px] overflow-y-auto rounded-lg border border-admin-border bg-admin-page p-3 text-[10px] leading-3 break-words whitespace-pre-wrap">{review.Content || '—'}</p></section>
      {review.IsDeleted && <section aria-label="Thông tin kiểm duyệt" className="flex flex-col gap-1 rounded-lg bg-admin-page p-2.5 text-[10px] leading-3"><p className="m-0 font-semibold">Đã ẩn</p><p className="m-0 text-admin-muted">Thời điểm ẩn: {formatDateTime(review.DeletedAt)}</p><p className="m-0 break-words whitespace-pre-wrap text-admin-muted">Lý do ẩn: {review.DeleteReason || '—'}</p></section>}
      {review.Images?.length > 0 && <section aria-label="Ảnh đánh giá"><h3 className="mt-0 mb-1.5 text-[10px] leading-3 font-medium text-admin-muted">Ảnh đánh giá</h3><div className="flex flex-wrap gap-3">{[...review.Images].sort((left, right) => left.DisplayOrder - right.DisplayOrder).map((entry, index) => <ReviewImage key={entry.ReviewImageId} entry={entry} number={index + 1} />)}</div></section>}
      <div className="flex justify-end"><ReviewButton secondary onClick={onClose}>Đóng</ReviewButton></div>
    </div>)}
  </Modal>
}
