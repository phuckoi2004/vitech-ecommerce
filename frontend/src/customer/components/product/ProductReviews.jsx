import { useEffect, useState } from 'react'
import Button from '../../../components/shared/Button.jsx'
import ErrorState from '../../../components/shared/ErrorState.jsx'
import LoadingState from '../../../components/shared/LoadingState.jsx'
import useApiData from '../../../hooks/useApiData.js'
import useCustomerSession from '../../../hooks/useCustomerSession.js'
import { formatDate, formatRating } from '../../../lib/format.js'
import { canEditReview, getProductReviewSummary } from '../../../lib/review-api.js'
import { normalizeImageUrl } from '../../../lib/rich-text.js'
import ProductModal from './ProductModal.jsx'
import ReviewComposer from './ReviewComposer.jsx'
import ReviewStars, { StarIcon } from './ReviewStars.jsx'
import useProductReviewList from './useProductReviewList.js'
import './ProductReviews.css'

function ReviewCard({ review, userId, onEdit, onImage }) {
  const name = review.User?.FullName || 'Khách hàng'
  const images = (review.Images ?? []).filter((image) => normalizeImageUrl(image.ImageUrl))
    .slice().sort((a, b) => a.DisplayOrder - b.DisplayOrder)
  const own = !!userId && review.User?.UserId === userId
  return <article className="pr-review" aria-label={`Đánh giá của ${name}`}>
    <header className="pr-review-heading">
      <div className="pr-review-author"><strong>{name}{own && <span className="pr-own-label">Bạn</span>}</strong>
        <span className="pr-purchased">Đã mua hàng</span>
      </div>
      <ReviewStars rating={review.Rating} />
    </header>
    <p className="pr-review-content">{review.Content}</p>
    <time dateTime={review.CreatedAt}>{formatDate(review.CreatedAt)}</time>
    {!!images.length && <div className="pr-review-images">
      {images.map((image, index) => <ReviewImage key={image.ReviewImageId} image={image} index={index} onImage={onImage} />)}
    </div>}
    {own && <div className="pr-review-actions">{canEditReview(review, userId)
      ? <Button size="sm" variant="ghost" onClick={() => onEdit(review)}>Chỉnh sửa đánh giá</Button>
      : <span>Đã hết thời hạn chỉnh sửa 7 ngày</span>}</div>}
  </article>
}

function ReviewImage({ image, index, onImage }) {
  const [failed, setFailed] = useState(false)
  const url = normalizeImageUrl(image.ImageUrl)
  return <button type="button" className="pr-review-image" disabled={failed} aria-label={`Phóng to ảnh đánh giá ${index + 1}`} onClick={() => onImage(url)}>
    {failed ? <span>Ảnh không tải được</span>
      : <img src={url} alt={`Ảnh trải nghiệm sản phẩm ${index + 1}`} loading="lazy" onError={() => setFailed(true)} />}
  </button>
}

export default function ProductReviews({ product, onRequireLogin, onSummaryChange }) {
  const { ready, user } = useCustomerSession()
  const [ratingFilter, setRatingFilter] = useState(null)
  const [page, setPage] = useState(1)
  const [version, setVersion] = useState(0)
  const [composer, setComposer] = useState(null)
  const [composerBusy, setComposerBusy] = useState(false)
  const [reviewedItemIds, setReviewedItemIds] = useState([])
  const [notice, setNotice] = useState('')
  const [image, setImage] = useState(null)
  const reviews = useProductReviewList(product.ProductId, ratingFilter, page, version)
  const summary = useApiData(`review-summary:${product.ProductId}:${version}`, (signal) =>
    getProductReviewSummary(product.ProductId, { signal }))
  const count = summary.data?.count ?? product.ReviewCount ?? 0
  const rating = summary.data?.rating ?? (Number(product.AverageRating) || 0)
  const items = reviews.data?.Items ?? []
  const hasMore = items.length < (reviews.data?.Total ?? 0)

  useEffect(() => {
    if (summary.data) onSummaryChange?.(summary.data)
  }, [summary.data, onSummaryChange])

  function writeReview() {
    if (!ready) return
    if (!user) return onRequireLogin()
    setNotice(''); setComposer({ review: null })
  }

  function selectRating(value) {
    setRatingFilter(value); setPage(1)
  }

  function saved({ orderItemId }) {
    if (orderItemId) setReviewedItemIds((items) => [...items, orderItemId])
    setComposer(null); setComposerBusy(false); selectRating(null); setVersion((value) => value + 1)
    setNotice(composer?.review ? 'Đã cập nhật đánh giá của bạn.' : 'Cảm ơn bạn! Đánh giá đã được gửi thành công.')
  }

  return <section id="product-reviews" className="pd-card pr-section" aria-labelledby="product-reviews-title">
    <header className="pr-heading"><div><h2 id="product-reviews-title">Đánh giá sản phẩm</h2>
      <p className="pr-subtitle">Đánh giá từ khách hàng đã mua sản phẩm tại VieTech</p></div>
      <Button className="pr-write-button" disabled={!ready} onClick={writeReview}>Viết đánh giá</Button>
    </header>
    <div className="pr-summary">
      <div className="pr-score"><strong>{count ? formatRating(rating) : '—'}</strong>
        <ReviewStars rating={count ? rating : 0} label={count ? `Điểm trung bình ${formatRating(rating)} trên 5 sao` : 'Chưa có điểm đánh giá'} />
        <p>{count} đánh giá</p>
      </div>
      <div className="pr-distribution" aria-label="Phân bố số sao">
        {summary.loading ? <p className="pr-subtitle" role="status">Đang tải thống kê đánh giá…</p>
          : summary.error ? <div className="pr-summary-error" role="alert"><p>Không tải được thống kê đánh giá.</p>
            <Button size="sm" variant="outline" onClick={summary.reload}>Tải lại thống kê</Button></div>
            : summary.data.distribution.map((item) => <button key={item.rating} type="button" className="pr-distribution-row"
              aria-label={`Lọc ${item.rating} sao, ${item.count} đánh giá`} onClick={() => selectRating(item.rating)}>
              <span>{item.rating} <StarIcon /></span><span className="pr-bar" aria-hidden="true">
                <span style={{ width: `${count ? item.count / count * 100 : 0}%` }} /></span><span>{item.count}</span>
            </button>)}
      </div>
      <div className="pr-invitation"><strong>Bạn đã mua sản phẩm này?</strong>
        <p>Khách hàng đã đăng nhập và sản phẩm đã được giao thành công mới có thể gửi đánh giá.</p>
        <span className="pr-purchased" aria-label="Điều kiện đánh giá: đã mua hàng">✓ Đã mua hàng</span>
      </div>
    </div>
    <div className="pr-toolbar"><div className="pr-filters" role="group" aria-label="Lọc đánh giá theo số sao">
      {[null, 5, 4, 3, 2, 1].map((value) => <button key={value ?? 'all'} type="button"
        aria-pressed={value === ratingFilter} onClick={() => selectRating(value)}>
        {value === null ? 'Tất cả' : <>{value} <StarIcon /></>}
      </button>)}
    </div></div>
    {notice && <p className="pd-notice is-success" role="status">{notice}</p>}
    {!!items.length && <div className="pr-review-list">{items.map((review) => <ReviewCard key={review.ReviewId}
      review={review} userId={user?.UserId} onEdit={(value) => { setNotice(''); setComposer({ review: value }) }} onImage={setImage} />)}</div>}
    {reviews.error && <ErrorState title="Không thể tải đánh giá" message={reviews.error} onRetry={reviews.reload} />}
    {reviews.loading && !items.length && <LoadingState label="Đang tải đánh giá…" />}
    {!reviews.loading && !reviews.error && !items.length && <div className="pr-empty"><ReviewStars rating={0} label="Chưa có đánh giá phù hợp" />
      <strong>{ratingFilter ? `Chưa có đánh giá ${ratingFilter} sao` : 'Chưa có đánh giá ở đây'}</strong>
      <p>{ratingFilter ? 'Bạn có thể chọn số sao khác hoặc xem tất cả đánh giá.' : 'Hãy chia sẻ trải nghiệm sau khi nhận sản phẩm.'}</p>
    </div>}
    {hasMore && !reviews.error && <Button className="pr-load-more" variant="outline" loading={reviews.loading}
      onClick={() => setPage(page + 1)}>Xem thêm đánh giá</Button>}
    <ProductModal open={!!composer && !!user} title={composer?.review ? 'Chỉnh sửa đánh giá' : `Đánh giá ${product.Name}`}
      className="pr-composer-modal" onClose={() => { if (!composerBusy) setComposer(null) }}>
      {composer && user && <ReviewComposer key={`${user.UserId}:${composer.review?.ReviewId ?? 'new'}`} product={product}
        review={composer.review} reviewedItemIds={reviewedItemIds} onSaved={saved} onBusyChange={setComposerBusy} onCancel={() => setComposer(null)} />}
    </ProductModal>
    <ProductModal open={!!image} title="Ảnh đánh giá sản phẩm" onClose={() => setImage(null)}>
      {image && <img className="pr-expanded-image" src={image} alt="Ảnh trải nghiệm sản phẩm của khách hàng" />}
    </ProductModal>
  </section>
}
