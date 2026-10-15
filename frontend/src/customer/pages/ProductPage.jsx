import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import useAuth from '../../auth/useAuth.js'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import useApiData from '../../hooks/useApiData.js'
import useCustomerRequest from '../../hooks/useCustomerRequest.js'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { getProductBySlug } from '../../lib/catalog-api.js'
import { formatRating } from '../../lib/format.js'
import { canPurchase, initialVariant, productVariants } from '../../lib/product-detail.js'
import LoginPromptDialog from '../components/LoginPromptDialog.jsx'
import ProductGallery from '../components/product/ProductGallery.jsx'
import ProductInformation from '../components/product/ProductInformation.jsx'
import ProductPurchasePanel from '../components/product/ProductPurchasePanel.jsx'
import ProductReviews from '../components/product/ProductReviews.jsx'
import RelatedProducts from '../components/product/RelatedProducts.jsx'
import { CART_PATH, HOME_PATH, LOGIN_PATH, brandPath, categoryPath, productPath } from '../routes/paths.js'
import './ProductPage.css'

function ProductDetails({ product }) {
  const variants = productVariants(product)
  const [variantId, setVariantId] = useState(initialVariant(variants)?.ProductVariantId ?? '')
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)
  const [loginPrompt, setLoginPrompt] = useState(false)
  const [reviewSummary, setReviewSummary] = useState(null)
  const pending = useRef(false)
  const { ready, user } = useCustomerSession()
  const { session } = useAuth()
  const send = useCustomerRequest()
  const navigate = useNavigate()
  const variant = variants.find((item) => item.ProductVariantId === variantId)
  const reviewCount = Math.max(0, reviewSummary?.count ?? (Number(product.ReviewCount) || 0))
  const rating = Math.min(5, Math.max(0, reviewSummary?.rating ?? (Number(product.AverageRating) || 0)))

  async function act(kind) {
    if (pending.current || !ready || !canPurchase(variant)) return
    if (!user) return session ? navigate(`${LOGIN_PATH}?next=${encodeURIComponent(productPath(product.Slug))}`) : setLoginPrompt(true)
    pending.current = true
    setBusy(kind); setNotice(null)
    try {
      await send('/cart/items', { method: 'POST', body: { ProductVariantId: variant.ProductVariantId, Quantity: 1 } })
      window.dispatchEvent(new Event('vietech-cart-changed'))
      if (kind === 'buy') navigate(CART_PATH)
      else setNotice({ ok: true, text: 'Đã thêm vào giỏ hàng.' })
    } catch (error) { setNotice({ ok: false, text: error.message || 'Không thể thực hiện. Vui lòng thử lại.' }) }
    finally { pending.current = false; setBusy('') }
  }

  function consult() {
    if (!ready) return
    if (!user) return session ? navigate(`${LOGIN_PATH}?next=${encodeURIComponent(productPath(product.Slug))}`) : setLoginPrompt(true)
    window.dispatchEvent(new Event('vietech-open-staff-chat'))
  }

  function select(item) {
    if (!item || pending.current) return
    setVariantId(item.ProductVariantId); setNotice(null)
  }

  return <div className="pd-page">
    <nav className="pd-breadcrumb" aria-label="Đường dẫn sản phẩm"><ol>
      <li><Link to={HOME_PATH}>Trang chủ</Link></li>
      {product.Category?.Name && <li>{product.Category.Slug ? <Link to={categoryPath(product.Category.Slug)}>{product.Category.Name}</Link> : product.Category.Name}</li>}
      {product.Brand?.Name && <li>{product.Brand.Slug ? <Link to={brandPath(product.Brand.Slug)}>{product.Brand.Name}</Link> : product.Brand.Name}</li>}
      <li aria-current="page">{product.Name}</li>
    </ol></nav>
    <header className="pd-heading"><h1>{product.Name}</h1>
      <div className="pd-meta"><span className="pd-stars" aria-label={`Đánh giá ${formatRating(rating)} trên 5 sao`}>
        {Array.from({ length: 5 }, (_, index) => <span key={index} aria-hidden="true">{index < Math.round(rating) ? '★' : '☆'}</span>)}
      </span><a className="pd-review-link" href="#product-reviews">{reviewCount ? `${formatRating(rating)} (${reviewCount} đánh giá)` : 'Chưa có đánh giá'}</a>
        <span>Đã bán {Math.max(0, Number(product.SoldQuantity) || 0)}</span>
      </div>
    </header>
    <div className="pd-main-grid grid grid-cols-1 items-start gap-5 min-[1000px]:grid-cols-[520fr_750fr]">
      <ProductGallery product={product} />
      <ProductPurchasePanel variants={variants} variant={variant} onSelect={select} busy={busy} notice={notice} ready={ready}
        onCart={() => act('cart')} onBuy={() => act('buy')}
        onConsult={consult} />
    </div>
    <ProductInformation product={product} variant={variant} />
    <ProductReviews product={product} onSummaryChange={setReviewSummary}
      onRequireLogin={() => session ? navigate(`${LOGIN_PATH}?next=${encodeURIComponent(productPath(product.Slug))}`) : setLoginPrompt(true)} />
    <RelatedProducts product={product} />
    <LoginPromptDialog open={loginPrompt} next={productPath(product.Slug)} onClose={() => setLoginPrompt(false)} />
  </div>
}

export default function ProductPage() {
  const { slug } = useParams()
  const product = useApiData(`product:${slug}`, async (signal) => {
    try { return await getProductBySlug(slug, { signal }) }
    catch (error) { if (error.status === 404) return null; throw error }
  })
  if (product.loading) return <div className="pd-page"><LoadingState label="Đang tải sản phẩm…" /></div>
  if (product.error) return <div className="pd-page"><ErrorState message={product.error} onRetry={product.reload} /></div>
  if (!product.data?.ProductId) return <div className="pd-page"><h1>Không tìm thấy sản phẩm</h1>
    <p>Sản phẩm không tồn tại hoặc đã ngừng bán.</p><Link to={HOME_PATH}>Về trang chủ</Link></div>
  return <ProductDetails key={product.data.ProductId} product={product.data} />
}
