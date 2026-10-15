import { useId, useRef, useState } from 'react'
import Button from '../../../components/shared/Button.jsx'
import ErrorState from '../../../components/shared/ErrorState.jsx'
import LoadingState from '../../../components/shared/LoadingState.jsx'
import useApiData from '../../../hooks/useApiData.js'
import useCustomerRequest from '../../../hooks/useCustomerRequest.js'
import useCustomerSession from '../../../hooks/useCustomerSession.js'
import { formatDate } from '../../../lib/format.js'
import { canEditReview, reviewableOrderItems } from '../../../lib/review-api.js'
import { StarIcon } from './ReviewStars.jsx'

const ORDER_PAGE_SIZE = 10
const RATING_LABELS = ['Chọn số sao', 'Rất không hài lòng', 'Không hài lòng', 'Bình thường', 'Hài lòng', 'Rất hài lòng']

function PurchasedItemPicker({ product, selectedItemId, onSelect, blockedItems, disabled }) {
  const { user } = useCustomerSession()
  const send = useCustomerRequest()
  const [page, setPage] = useState(1)
  const [selectedOrderId, setSelectedOrderId] = useState('')
  const id = useId()
  const orders = useApiData(`review-orders:${user.UserId}:${page}`, (signal) =>
    send('/orders', { query: { order_status: 'Delivered', page, page_size: ORDER_PAGE_SIZE }, signal }))
  const orderId = selectedOrderId || orders.data?.Items[0]?.OrderId
  const detail = useApiData(orderId ? `review-order:${user.UserId}:${orderId}` : null, (signal) =>
    send(`/orders/${encodeURIComponent(orderId)}`, { signal }))
  const items = reviewableOrderItems(detail.data, product)
  const pages = Math.max(1, Math.ceil((orders.data?.Total || 0) / ORDER_PAGE_SIZE))

  function changePage(next) {
    setPage(next); setSelectedOrderId(''); onSelect('')
  }

  if (orders.loading) return <LoadingState label="Đang tải đơn hàng đã giao…" />
  if (orders.error) return <ErrorState message={orders.error} onRetry={orders.reload} />
  if (!orders.data?.Items.length) return <p className="pr-form-hint">Bạn chưa có đơn hàng đã giao để đánh giá. Bạn chỉ có thể đánh giá sản phẩm đã mua trong đơn đang ở trạng thái đã giao.</p>

  return <div className="pr-purchase-picker">
    <label htmlFor={`${id}-order`}>Đơn hàng đã giao</label>
    <select id={`${id}-order`} value={orderId} disabled={disabled} onChange={(event) => {
      setSelectedOrderId(event.target.value); onSelect('')
    }}>
      {orders.data.Items.map((order) => <option key={order.OrderId} value={order.OrderId}>
        {order.OrderCode} · {formatDate(order.OrderedAt)}
      </option>)}
    </select>
    {pages > 1 && <nav className="pr-pagination" aria-label="Trang đơn hàng đã giao">
      <Button size="sm" variant="outline" disabled={disabled || page <= 1} onClick={() => changePage(page - 1)}>Đơn trước</Button>
      <span>Trang {page} / {pages}</span>
      <Button size="sm" variant="outline" disabled={disabled || page >= pages} onClick={() => changePage(page + 1)}>Đơn tiếp</Button>
    </nav>}
    {detail.loading ? <LoadingState label="Đang kiểm tra sản phẩm đã mua…" />
      : detail.error ? <ErrorState message={detail.error} onRetry={detail.reload} />
        : !items.length ? <p className="pr-form-hint">Đơn này không có sản phẩm đang xem hoặc không còn ở trạng thái đã giao. Vui lòng chọn đơn khác.</p>
          : <>
            <label htmlFor={`${id}-item`}>Sản phẩm đã mua trong đơn</label>
            <select id={`${id}-item`} value={selectedItemId} required disabled={disabled} onChange={(event) => onSelect(event.target.value)}>
              <option value="">Chọn phiên bản đã mua</option>
              {items.map((item) => <option key={item.OrderItemId} value={item.OrderItemId} disabled={blockedItems.includes(item.OrderItemId)}>
                {item.ProductName} · {item.VariantInfo || 'Phiên bản tiêu chuẩn'}{blockedItems.includes(item.OrderItemId) ? ' · Đã đánh giá' : ''}
              </option>)}
            </select>
          </>}
  </div>
}

export default function ReviewComposer({ product, review, reviewedItemIds = [], onSaved, onCancel, onBusyChange }) {
  const { user } = useCustomerSession()
  const send = useCustomerRequest()
  const id = useId()
  const [itemId, setItemId] = useState('')
  const [rating, setRating] = useState(review?.Rating ?? 0)
  const [content, setContent] = useState(review?.Content ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [blockedItems, setBlockedItems] = useState(reviewedItemIds)
  const pending = useRef(false)

  async function submit(event) {
    event.preventDefault()
    if (pending.current) return
    setError('')
    if (review && !canEditReview(review, user.UserId)) return setError('Đã quá thời hạn 7 ngày để chỉnh sửa đánh giá.')
    if (!review && (!itemId || blockedItems.includes(itemId))) return setError('Vui lòng chọn phiên bản đã mua chưa được đánh giá.')
    if (!rating) return setError('Vui lòng chọn số sao từ 1 đến 5.')
    if (!content.trim()) return setError('Nội dung đánh giá không được để trống.')
    pending.current = true; setBusy(true)
    onBusyChange?.(true)
    try {
      const result = await send(review ? `/reviews/${encodeURIComponent(review.ReviewId)}` : '/reviews', {
        method: review ? 'PATCH' : 'POST',
        body: review ? { Rating: rating, Content: content.trim() }
          : { OrderItemId: itemId, Rating: rating, Content: content.trim() },
      })
      onSaved({ review: result, orderItemId: review ? null : itemId })
    } catch (failure) {
      setError(failure.message || 'Không thể gửi đánh giá. Vui lòng thử lại.')
      // ReviewResponse intentionally has no OrderItemId. The server is the authority for older duplicates.
      if (!review && failure.code === 'review_exists') {
        setBlockedItems((items) => [...items, itemId]); setItemId('')
      }
    } finally {
      pending.current = false; setBusy(false)
      onBusyChange?.(false)
    }
  }

  return <form className="pr-form" onSubmit={submit}>
    <p className="pr-form-hint">{review ? 'Bạn được sửa số sao và nội dung trong 7 ngày kể từ khi gửi đánh giá.'
      : 'Mỗi sản phẩm trong đơn đã giao được đánh giá một lần. Bạn có thể sửa số sao và nội dung trong 7 ngày sau khi gửi.'}</p>
    {!review && <PurchasedItemPicker product={product} selectedItemId={itemId} onSelect={setItemId} blockedItems={blockedItems} disabled={busy} />}
    <fieldset disabled={busy} className="pr-rating-picker">
      <legend>Bạn đánh giá sản phẩm bao nhiêu sao?</legend>
      <div className="pr-rating-options">
        {[1, 2, 3, 4, 5].map((star) => <label key={star} className={star <= rating ? 'is-selected' : ''}>
          <input type="radio" name={`${id}-rating`} value={star} checked={star === rating} onChange={() => setRating(star)} aria-label={`${star} sao`} />
          <StarIcon filled={star <= rating} />
        </label>)}
      </div>
      <span className="pr-rating-caption" aria-live="polite">{RATING_LABELS[rating]}</span>
    </fieldset>
    <label htmlFor={`${id}-content`}>Nội dung đánh giá</label>
    <textarea id={`${id}-content`} value={content} onChange={(event) => setContent(event.target.value)}
      placeholder="Chia sẻ trải nghiệm sử dụng sản phẩm của bạn…" rows="5" required disabled={busy} />
    {error && <p className="pd-notice" role="alert">{error}</p>}
    <div className="pr-form-actions">
      <Button variant="outline" disabled={busy} onClick={onCancel}>Hủy</Button>
      <Button type="submit" loading={busy} disabled={!review && !itemId}>{review ? 'Lưu thay đổi' : 'Gửi đánh giá'}</Button>
    </div>
  </form>
}
