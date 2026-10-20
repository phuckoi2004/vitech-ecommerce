import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import useAuth from '../../auth/useAuth.js'
import Money from '../../components/shared/Money.jsx'
import useCustomerRequest from '../../hooks/useCustomerRequest.js'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { formatCompactCount, formatDiscountPercent, formatRating } from '../../lib/format.js'
import useWishlistProduct, { updateWishlistProduct } from '../hooks/useWishlistProduct.js'
import { LOGIN_PATH, productPath } from '../routes/paths.js'
import LoginPromptDialog from './LoginPromptDialog.jsx'
import StoreImage from './StoreImage.jsx'
import wishlistHeartActive from '../../assets/storefront/wishlist-heart-active.svg'
import './ProductCard.css'

// Product card from toProductCard() (lib/catalog-api.js): image, name, lowest variant price, rating, sold count.
// Original/sale prices always come from the same lowest-priced visible variant.
export default function ProductCard({ product, headingLevel = 3, wishlistLayout = false, children }) {
  const Heading = `h${headingLevel}`
  const rated = product.reviewCount > 0
  const discounted = !product.unavailable && product.originalPrice > product.price
  const { ready, user } = useCustomerSession()
  const { session } = useAuth()
  const send = useCustomerRequest()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [added, setAdded] = useWishlistProduct({ enabled: ready && !!user, productId: product.id, userId: user?.UserId, send })
  const [error, setError] = useState('')
  const [loginPrompt, setLoginPrompt] = useState(false)
  const path = productPath(product.slug)

  async function toggleWishlist(event) {
    event.preventDefault()
    event.stopPropagation()
    if (busy || !ready) return
    if (!user) {
      if (session) navigate(`${LOGIN_PATH}?next=${encodeURIComponent(path)}`)
      else setLoginPrompt(true)
      return
    }
    setBusy(true)
    setError('')
    try {
      await send(added ? `/wishlist/products/${encodeURIComponent(product.id)}` : '/wishlist/items', {
        method: added ? 'DELETE' : 'POST',
        ...(added ? {} : { body: { ProductId: product.id } }),
      })
      const nextAdded = !added
      setAdded(nextAdded)
      updateWishlistProduct(user.UserId, product.id, nextAdded)
      window.dispatchEvent(new Event('vietech-wishlist-changed'))
    } catch (failure) {
      setError(failure.message || (added ? 'Không thể bỏ sản phẩm khỏi yêu thích.' : 'Không thể thêm sản phẩm vào yêu thích.'))
    } finally {
      setBusy(false)
    }
  }

  const heart = <button type="button" className={`pcard-wishlist${added ? ' is-added' : ''}`} aria-label={added ? `Bỏ ${product.name} khỏi yêu thích` : `Thêm ${product.name} vào yêu thích`}
    aria-pressed={added} disabled={busy} onClick={toggleWishlist} title={added ? 'Bỏ yêu thích' : 'Thêm vào yêu thích'}>
    {added ? <img src={wishlistHeartActive} alt="" width="26" height="26" /> : <span aria-hidden="true">♡</span>}
  </button>

  return <article className={`pcard${wishlistLayout ? ' pcard-wishlist-layout' : ''}`}>
    <Link className="pcard-link" to={path}>
      <div className="pcard-media">
        <StoreImage src={product.imageUrl} alt="" loading="lazy" decoding="async"
          fallback={<span className="pcard-noimage" aria-hidden="true">VieTech</span>} />
        {product.unavailable ? <span className="pcard-badge">Ngừng bán</span>
          : !product.inStock && <span className="pcard-badge">Hết hàng</span>}
      </div>
      <Heading className="pcard-name">{product.name}</Heading>
      <div className="pcard-pricing">
        <p className="pcard-price">
          {product.price === null
            ? <span className="pcard-noprice">Đang cập nhật giá</span>
            : <Money value={product.price} />}
        </p>
        {discounted && <p className="pcard-original">
          <span className="sr-only">Giá niêm yết </span><del><Money value={product.originalPrice} /></del>
          <span className="pcard-discount"><span className="sr-only">Giảm </span>-{formatDiscountPercent(product.discountPercent)}</span>
        </p>}
      </div>
      <p className="pcard-meta">
        {rated && <span><span className="sr-only">Đánh giá </span><span aria-hidden="true">★ </span>{formatRating(product.rating)}</span>}
        {rated && product.sold > 0 && <span aria-hidden="true"> • </span>}
        {product.sold > 0 && <span>Đã bán {formatCompactCount(product.sold)}</span>}
      </p>
    </Link>
    {wishlistLayout ? <div className="pcard-wishlist-status"><span>{added ? 'Đã thêm vào yêu thích' : 'Chưa thêm vào yêu thích'}</span>{heart}</div> : heart}
    {children}
    {error && <p className="pcard-error" role="alert">{error}</p>}
    <LoginPromptDialog open={loginPrompt} next={path} onClose={() => setLoginPrompt(false)} />
  </article>
}

// Same footprint as a card while the list loads.
export function ProductCardSkeleton() {
  return <div className="pcard is-skeleton" aria-hidden="true">
    <div className="pcard-media" />
    <span className="pcard-line" />
    <span className="pcard-line is-short" />
  </div>
}
