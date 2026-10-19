import { useRef, useState } from 'react'
import Button from '../../components/shared/Button.jsx'
import useCustomerRequest from '../../hooks/useCustomerRequest.js'
import { toProductCard } from '../../lib/catalog-api.js'
import { formatMoney } from '../../lib/format.js'
import { canPurchase, initialVariant, productVariants } from '../../lib/product-detail.js'
import ProductCard from './ProductCard.jsx'
import ProductModal from './product/ProductModal.jsx'
import '../pages/ProductPage.css'

export default function WishlistProductCard({ product, unavailable = false }) {
  const variants = productVariants(product)
  const [selectedId, setSelectedId] = useState(initialVariant(variants, product.DefaultVariantId)?.ProductVariantId ?? '')
  const [choosing, setChoosing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)
  const pending = useRef(false)
  const send = useCustomerRequest()
  const selected = variants.find((variant) => variant.ProductVariantId === selectedId)
  const purchasable = !unavailable && variants.some(canPurchase)

  async function add(variant) {
    if (pending.current || !canPurchase(variant)) return
    pending.current = true; setBusy(true); setNotice(null)
    try {
      await send('/cart/items', { method: 'POST', body: { ProductVariantId: variant.ProductVariantId, Quantity: 1 } })
      window.dispatchEvent(new Event('vietech-cart-changed'))
      setChoosing(false); setNotice({ ok: true, text: 'Đã thêm vào giỏ hàng.' })
    } catch (failure) { setNotice({ ok: false, text: failure.message || 'Không thể thêm vào giỏ hàng.' }) }
    finally { pending.current = false; setBusy(false) }
  }

  function startAdd() {
    if (!purchasable || pending.current) return
    setNotice(null)
    if (variants.length > 1) setChoosing(true)
    else add(variants[0])
  }

  return <ProductCard product={{ ...toProductCard(product), unavailable }} wishlistLayout>
    <Button className="wishlist-add-cart" disabled={!purchasable} loading={busy} onClick={startAdd}>Thêm vào giỏ hàng</Button>
    {notice && !choosing && <p className={`wishlist-notice${notice.ok ? ' is-success' : ''}`} role={notice.ok ? 'status' : 'alert'}>{notice.text}</p>}
    <ProductModal open={choosing} title={`Chọn phiên bản ${product.Name}`} className="wishlist-variant-modal" onClose={() => { if (!pending.current) setChoosing(false) }}>
      <div className="wishlist-variant-form">
        <label htmlFor={`wishlist-variant-${product.ProductId}`}>Phiên bản sản phẩm</label>
        <select id={`wishlist-variant-${product.ProductId}`} value={selectedId} disabled={busy} onChange={(event) => setSelectedId(event.target.value)}>
          {variants.map((variant) => <option key={variant.ProductVariantId} value={variant.ProductVariantId} disabled={!canPurchase(variant)}>
            {variant.VariantName || [variant.Color, variant.Storage].filter(Boolean).join(' · ') || 'Tiêu chuẩn'} · {formatMoney(variant.Price)}{!canPurchase(variant) ? ' · Hết hàng' : ''}
          </option>)}
        </select>
        {notice && <p className="wishlist-notice" role="alert">{notice.text}</p>}
        <Button disabled={!canPurchase(selected)} loading={busy} onClick={() => add(selected)}>Thêm phiên bản đã chọn vào giỏ</Button>
      </div>
    </ProductModal>
  </ProductCard>
}
