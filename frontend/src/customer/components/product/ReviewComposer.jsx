import { useId, useRef, useState } from 'react'
import Button from '../../../components/shared/Button.jsx'
import ErrorState from '../../../components/shared/ErrorState.jsx'
import LoadingState from '../../../components/shared/LoadingState.jsx'
import useApiData from '../../../hooks/useApiData.js'
import useCustomerRequest from '../../../hooks/useCustomerRequest.js'
import useCustomerSession from '../../../hooks/useCustomerSession.js'
import { variantImages } from '../../../lib/product-detail.js'
import { canEditReview, REVIEWABLE_ORDER_STATUSES, reviewableOrderItems } from '../../../lib/review-api.js'
import { normalizeImageUrl } from '../../../lib/rich-text.js'
import StoreImage from '../StoreImage.jsx'

const ORDER_PAGE_SIZE = 50
const RATING_LABELS = ['Chọn số sao', 'Rất không hài lòng', 'Không hài lòng', 'Bình thường', 'Hài lòng', 'Rất hài lòng']

// A review belongs to the product it is written on; the API ties it to one purchased line (OrderItemId), which the
// customer does not pick. It is the newest line of this product, in a received order, without a review yet; the line
// in `preferredOrderId` (the order the customer came from) first. Reads the received orders holding the product page
// by page until one is found. `purchased` tells "every purchase is reviewed" from "never received this product".
async function findPurchase(send, product, preferredOrderId, blockedItems, signal) {
  let purchased = false
  let newest = null
  for (let page = 1; ; page += 1) {
    const orders = await send('/orders', { query: { order_status: REVIEWABLE_ORDER_STATUSES, product_id: product.ProductId,
      page, page_size: ORDER_PAGE_SIZE }, signal })
    for (const order of orders.Items) {
      for (const item of reviewableOrderItems(order, product)) {
        purchased = true
        if (item.ReviewId || blockedItems.includes(item.OrderItemId)) continue
        if (order.OrderId === preferredOrderId) return { line: { order, item }, purchased }
        newest ??= { order, item }
      }
    }
    if ((newest && !preferredOrderId) || page * ORDER_PAGE_SIZE >= orders.Total) return { line: newest, purchased }
  }
}

function ReviewProduct({ product, review, purchase }) {
  const line = purchase.data?.line
  const image = variantImages(product, line?.item.ProductVariantId)[0]
  return <div className="pr-form-product">
    <div className="pr-form-product-image"><StoreImage src={normalizeImageUrl(image?.ImageUrl)} alt={product.Name}
      fallback={<span>Ảnh</span>} /></div>
    <div className="pr-form-product-copy">
      <strong>{line?.item.ProductName || product.Name}</strong>
      {line ? <p>Đơn hàng {line.order.OrderCode || line.order.OrderId} • Đã nhận hàng
        {line.item.VariantInfo ? ` · ${line.item.VariantInfo}` : ''}</p>
        : <p>{review ? 'Đánh giá của bạn • Đã mua hàng' : 'Sản phẩm bạn muốn đánh giá'}</p>}
    </div>
  </div>
}

function PurchaseStatus({ purchase }) {
  if (purchase.loading) return <LoadingState label="Đang kiểm tra sản phẩm bạn đã mua…" />
  if (purchase.error) return <ErrorState message={purchase.error} onRetry={purchase.reload} />
  if (purchase.data?.line || purchase.data?.purchased) return null
  return <p className="pr-form-hint">Bạn chưa có đơn hàng đã giao nào có sản phẩm này. Bạn có thể đánh giá sau khi nhận được hàng.</p>
}

export default function ReviewComposer({ product, review, initialOrderId, reviewedItemIds = [], onSaved, onCancel, onBusyChange }) {
  const { user } = useCustomerSession()
  const send = useCustomerRequest()
  const id = useId()
  const [rating, setRating] = useState(review?.Rating ?? 0)
  const [hoverRating, setHoverRating] = useState(null)
  const [content, setContent] = useState(review?.Content ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [blockedItems, setBlockedItems] = useState(reviewedItemIds)
  const pending = useRef(false)
  // A new review only: the purchase it is for. A line refused as already reviewed is skipped on the next read.
  const purchase = useApiData(review ? null : `review-purchase:${user.UserId}:${product.ProductId}:${initialOrderId ?? ''}:${blockedItems.join(',')}`,
    (signal) => findPurchase(send, product, initialOrderId, blockedItems, signal))
  const itemId = purchase.data?.line?.item.OrderItemId ?? ''

  async function submit(event) {
    event.preventDefault()
    if (pending.current) return
    setError('')
    if (review && !canEditReview(review, user.UserId)) return setError('Đã quá thời hạn 7 ngày để chỉnh sửa đánh giá.')
    if (!review && !itemId) return setError('Bạn chỉ có thể đánh giá sản phẩm đã mua và đã nhận hàng.')
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
      // Reviewed meanwhile (another tab): the next purchase without a review is looked up.
      if (!review && failure.code === 'review_exists') setBlockedItems((items) => [...items, itemId])
    } finally {
      pending.current = false; setBusy(false)
      onBusyChange?.(false)
    }
  }

  return <form className="pr-form" onSubmit={submit}>
    <ReviewProduct product={product} review={review} purchase={purchase} />
    {!review && <PurchaseStatus purchase={purchase} />}
    <fieldset disabled={busy} className="pr-rating-picker">
      <legend>Mức đánh giá</legend>
      <div className="pr-rating-options" onMouseLeave={() => setHoverRating(null)}>
        {[1, 2, 3, 4, 5].map((star) => <label key={star} className={star <= (hoverRating ?? rating) ? 'is-selected' : ''}
          onMouseEnter={() => { if (!busy) setHoverRating(star) }}>
          <input type="radio" name={`${id}-rating`} value={star} checked={star === rating}
            onChange={() => { setRating(star); setHoverRating(null) }} aria-label={`${star} sao`} />
          <span aria-hidden="true">{star <= (hoverRating ?? rating) ? '★' : '☆'}</span>
        </label>)}
      </div>
      <span className="sr-only" aria-live="polite">{RATING_LABELS[rating]}</span>
    </fieldset>
    <label htmlFor={`${id}-content`}>Nhận xét của bạn</label>
    <textarea id={`${id}-content`} value={content} onChange={(event) => setContent(event.target.value)}
      placeholder="Chia sẻ trải nghiệm của bạn về sản phẩm..." rows="5" required disabled={busy} aria-describedby={`${id}-notice`} />
    <div className="pr-form-notice" id={`${id}-notice`}>
      <span aria-hidden="true">ⓘ</span>
      <p>{review ? 'Bạn có thể thay đổi số sao và nội dung đánh giá trong 7 ngày kể từ khi gửi.'
        : 'Chỉ sản phẩm đã mua và giao thành công mới có thể đánh giá.'}</p>
    </div>
    {error && <p className="pd-notice" role="alert">{error}</p>}
    <div className="pr-form-actions">
      <Button variant="outline" disabled={busy} onClick={onCancel}>Hủy</Button>
      <Button type="submit" loading={busy} disabled={!review && !itemId}>{review ? 'Cập nhật đánh giá' : 'Gửi đánh giá'}</Button>
    </div>
  </form>
}
