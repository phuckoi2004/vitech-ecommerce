import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Button from '../../components/shared/Button.jsx'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import Money from '../../components/shared/Money.jsx'
import useApiData from '../../hooks/useApiData.js'
import useCustomerRequest from '../../hooks/useCustomerRequest.js'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { getProductBySlug } from '../../lib/catalog-api.js'
import { CART_PATH, CHAT_PATH, LOGIN_PATH, productPath } from '../routes/paths.js'
import './ShoppingPages.css'

function ProductDetails({ product }) {
  const [variantId, setVariantId] = useState(product.Variants?.[0]?.ProductVariantId ?? '')
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)
  const { user } = useCustomerSession()
  const send = useCustomerRequest()
  const navigate = useNavigate()
  const variant = product.Variants?.find((item) => item.ProductVariantId === variantId)
  const images = [...(product.Images ?? [])].sort((a, b) => Number(b.IsDefault) - Number(a.IsDefault) || a.DisplayOrder - b.DisplayOrder)

  async function act(kind) {
    if (!user) return navigate(`${LOGIN_PATH}?next=${encodeURIComponent(productPath(product.Slug))}`)
    setBusy(kind); setNotice(null)
    try {
      await send(kind === 'cart' ? '/cart/items' : '/wishlist/items', { method: 'POST', body: kind === 'cart'
        ? { ProductVariantId: variantId, Quantity: 1 } : { ProductId: product.ProductId } })
      setNotice({ ok: true, text: kind === 'cart' ? 'Đã thêm vào giỏ hàng.' : 'Đã lưu vào danh sách yêu thích.' })
    } catch (error) { setNotice({ ok: false, text: error.message }) }
    finally { setBusy('') }
  }

  return <div className="shopping-page">
    <h1>{product.Name}</h1>
    <div className="product-detail-grid">
      <div className="product-detail-images">
        {images.length ? images.map((image) => <img key={image.ProductImageId ?? image.ImageUrl} src={image.ImageUrl} alt={product.Name} />)
          : <div className="product-detail-placeholder">Chưa có ảnh sản phẩm</div>}
      </div>
      <section className="shopping-panel" aria-label="Thông tin mua hàng">
        <p>{product.Brand?.Name} · {product.Category?.Name}</p>
        <p>Bảo hành: {product.WarrantyMonths} tháng</p>
        {!!product.Variants?.length && <label className="shopping-filter">Phiên bản
          <select value={variantId} onChange={(event) => setVariantId(event.target.value)}>
            {product.Variants.map((item) => <option key={item.ProductVariantId} value={item.ProductVariantId}>
              {item.VariantName} {item.Color ? `· ${item.Color}` : ''} {item.Storage ? `· ${item.Storage}` : ''}
            </option>)}
          </select>
        </label>}
        <p className="product-detail-price">{variant ? <Money value={variant.Price} /> : 'Đang cập nhật giá'}</p>
        <p>{variant?.StockQuantity > 0 ? `Còn ${variant.StockQuantity} sản phẩm` : 'Hết hàng'}</p>
        <div className="shopping-actions">
          <Button onClick={() => act('cart')} loading={busy === 'cart'} disabled={!!busy || !variant || variant.StockQuantity <= 0}>Thêm vào giỏ hàng</Button>
          <Button variant="outline" onClick={() => act('wishlist')} loading={busy === 'wishlist'} disabled={!!busy}>Yêu thích</Button>
        </div>
        {notice && <p role={notice.ok ? 'status' : 'alert'}>{notice.text}</p>}
        <div className="shopping-actions"><Link to={CART_PATH}>Xem giỏ hàng</Link><Link to={CHAT_PATH}>Chat với nhân viên</Link></div>
      </section>
    </div>
    <section className="shopping-panel"><h2>Mô tả sản phẩm</h2><p className="shopping-text">{product.Description || 'Đang cập nhật mô tả.'}</p></section>
    {product.Specifications && <section className="shopping-panel"><h2>Thông số kỹ thuật</h2>
      <dl className="shopping-specs">{Object.entries(product.Specifications).map(([name, value]) => <div key={name}>
        <dt>{name}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd>
      </div>)}</dl>
    </section>}
  </div>
}

export default function ProductPage() {
  const { slug } = useParams()
  const product = useApiData(`product:${slug}`, (signal) => getProductBySlug(slug, { signal }))
  if (product.loading) return <LoadingState />
  if (product.error) return <ErrorState message={product.error} onRetry={product.reload} />
  return <ProductDetails key={product.data.ProductId} product={product.data} />
}
