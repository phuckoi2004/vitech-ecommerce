import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { buttonClassName } from '../../components/shared/buttonStyles.js'
import EmptyState from '../../components/shared/EmptyState.jsx'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import useApiData from '../../hooks/useApiData.js'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { getCart, removeCartItem, setCartSelection, updateCartItem } from '../../lib/cart-api.js'
import CartItem from '../components/cart/CartItem.jsx'
import CartSummary from '../components/cart/CartSummary.jsx'
import CouponDialog from '../components/cart/CouponDialog.jsx'
import { checkoutBlock, couponBlock } from '../components/cart/cartLines.js'
import useCartCoupon from '../components/cart/useCartCoupon.js'
import useProductDetails from '../components/cart/useProductDetails.js'
import { HOME_PATH } from '../routes/paths.js'
import './CartPage.css'

// After these errors the cart on screen is out of date (stock changed, product withdrawn, line removed elsewhere).
const STALE_CART_CODES = new Set(['insufficient_stock', 'variant_not_available', 'cart_item_not_found'])

// The header cart entry (CartLink) reloads its count on this event.
const announceCartChange = () => window.dispatchEvent(new Event('vietech-cart-changed'))

// Customer cart (Figma "Giỏ hàng"), inside CustomerLayout and RequireCustomer. Every change is saved at once and the
// cart returned by the server replaces the one on screen; one change is saved at a time.
export default function CartPage() {
  const { user, withAccessToken } = useCustomerSession()
  const loaded = useApiData(`cart:${user?.UserId ?? ''}`, (signal) => withAccessToken((token) => getCart(token, { signal })))
  // The latest cart returned by a change, valid only for the load it was made on (a retry starts over).
  const [latest, setLatest] = useState(null)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState('')
  const cart = latest && latest.base === loaded.data ? latest.cart : loaded.data
  const details = useProductDetails(cart?.Items.map((line) => line.ProductId) ?? [])
  const coupon = useCartCoupon({ userId: user?.UserId, cart, withAccessToken })
  const [choosingCoupon, setChoosingCoupon] = useState(false)

  useEffect(() => {
    document.title = 'Giỏ hàng | VieTech'
  }, [])

  async function save(target, call) {
    const base = loaded.data
    setBusy(target); setError('')
    try {
      setLatest({ base, cart: await withAccessToken(call) })
      announceCartChange()
    } catch (failure) {
      setError(failure.message)
      if (STALE_CART_CODES.has(failure.code)) {
        try {
          setLatest({ base, cart: await withAccessToken((token) => getCart(token)) })
          announceCartChange()
        } catch { /* keep the message */ }
      }
    } finally {
      setBusy(null)
    }
  }

  const changeLine = (line, changes) => save({ id: line.CartItemId, kind: 'IsSelected' in changes ? 'select' : 'quantity' },
    (token) => updateCartItem(token, line.CartItemId, changes))
  const removeLine = (line) => save({ id: line.CartItemId, kind: 'remove' }, (token) => removeCartItem(token, line.CartItemId))
  const selectAll = (isSelected) => save({ id: 'all', kind: 'select' }, (token) => setCartSelection(token, isSelected))

  const lines = cart?.Items ?? []
  const allSelected = lines.length > 0 && lines.every((line) => line.IsSelected)
  const someSelected = lines.some((line) => line.IsSelected)
  // An order with a coupon that no longer applies would be rejected as a whole.
  const block = checkoutBlock(lines) || couponBlock(coupon, 'Hãy đổi hoặc bỏ mã.')

  function confirmCoupon(preview) {
    if (preview) coupon.apply(preview)
    else coupon.remove()
    setChoosingCoupon(false)
  }

  return <div className="cart-page">
    <div className="cart-card">
      <nav className="cart-breadcrumb" aria-label="Đường dẫn">
        <ol>
          <li><Link to={HOME_PATH}>Trang chủ</Link></li>
          <li aria-current="page">Giỏ hàng</li>
        </ol>
      </nav>
      <div className="cart-heading">
        <h1>Giỏ hàng</h1>
        {lines.length > 0 && <p>{lines.length} sản phẩm trong giỏ hàng</p>}
      </div>
      {loaded.loading ? <LoadingState label="Đang tải giỏ hàng…" />
        : loaded.error ? <ErrorState title="Không thể tải giỏ hàng" message={loaded.error} onRetry={loaded.reload} />
          : !lines.length ? <EmptyState title="Giỏ hàng đang trống"
            description="Hãy chọn sản phẩm bạn yêu thích và thêm vào giỏ hàng."
            action={<Link className={buttonClassName({ variant: 'outline' })} to={HOME_PATH}>Tiếp tục mua sắm</Link>} />
            : <div className="cart-columns">
              <section className="cart-products" aria-labelledby="cart-products-title">
                <h2 id="cart-products-title" className="sr-only">Sản phẩm trong giỏ hàng</h2>
                {error && <p className="cart-alert" role="alert">{error}</p>}
                <div className="cart-select-all">
                  <label>
                    <input type="checkbox" className="cart-check" checked={allSelected} disabled={!!busy}
                      ref={(node) => { if (node) node.indeterminate = someSelected && !allSelected }}
                      aria-busy={busy?.id === 'all' || undefined}
                      onChange={() => selectAll(!allSelected)} />
                    Chọn tất cả ({lines.length} sản phẩm)
                  </label>
                </div>
                <ul className="cart-list">
                  {lines.map((line) => <li key={line.CartItemId}>
                    <CartItem line={line} detail={details[line.ProductId]} locked={!!busy}
                      busy={busy?.id === line.CartItemId ? busy.kind : ''}
                      onChange={(changes) => changeLine(line, changes)} onRemove={() => removeLine(line)} />
                  </li>)}
                </ul>
                <div className="cart-continue">
                  <Link className="cart-continue-link" to={HOME_PATH}><span aria-hidden="true">←</span>Tiếp tục mua hàng</Link>
                  <p>Chỉ tính tiền các sản phẩm đã chọn</p>
                </div>
              </section>
              <CartSummary cart={cart} coupon={coupon} block={block} pending={!!busy || coupon.status === 'checking'}
                onChooseCoupon={() => setChoosingCoupon(true)} onRemoveCoupon={coupon.remove} onRetryCoupon={coupon.retry}
                onReloadCart={() => { loaded.reload(); coupon.retry() }} />
            </div>}
      {choosingCoupon && <CouponDialog code={coupon.code} applied={coupon.preview} withAccessToken={withAccessToken}
        onConfirm={confirmCoupon} onClose={() => setChoosingCoupon(false)} />}
    </div>
  </div>
}
