import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { nextQuery } from '../../auth/session.js'
import { buttonClassName } from '../../components/shared/buttonStyles.js'
import EmptyState from '../../components/shared/EmptyState.jsx'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import useApiData from '../../hooks/useApiData.js'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { listAddresses } from '../../lib/account-api.js'
import { getCart } from '../../lib/cart-api.js'
import { listPaymentMethods, listShippingMethods } from '../../lib/catalog-api.js'
import { createOrder, listMyOrders } from '../../lib/order-api.js'
import { checkoutBlock, couponBlock } from '../components/cart/cartLines.js'
import useCartCoupon, { clearCartCoupon } from '../components/cart/useCartCoupon.js'
import useProductDetails from '../components/cart/useProductDetails.js'
import AddressPicker from '../components/checkout/AddressPicker.jsx'
import CheckoutSection from '../components/checkout/CheckoutSection.jsx'
import CheckoutSummary from '../components/checkout/CheckoutSummary.jsx'
import { newReceiver, orderPayload, shippingDetail, validateCheckout } from '../components/checkout/checkoutForm.js'
import OptionCard from '../components/checkout/OptionCard.jsx'
import OrderProblem from '../components/checkout/OrderProblem.jsx'
import { orderFailure } from '../components/checkout/orderErrors.js'
import { CART_PATH, HOME_PATH, LOGIN_PATH, orderPath } from '../routes/paths.js'
import './CheckoutPage.css'

// Fields in the order they appear, to focus the first one with an error.
const FIELD_ORDER = ['address', 'ReceiverName', 'ReceiverPhone', 'Province', 'Ward', 'DetailAddress', 'shipping', 'payment']
// Places of orderFailure that are fields of this form: their message shows under the field.
const FIELD_PLACES = new Set(['address', 'shipping', 'payment'])
const STEPS = [['✓', 'Giỏ hàng'], ['2', 'Xác nhận đặt hàng'], ['3', 'Thanh toán / Hoàn tất']]

// Order confirmation (Figma "Xác nhận đặt hàng" 261:333), inside CustomerLayout and RequireCustomer. The lines are
// the selected cart lines read from the cart API, never passed from the cart page; the coupon applied in the cart is
// checked again with the preview API. The customer picks an address, a shipping and a payment method from the API;
// the form is checked here, then POST /orders places the order (the server prices it). Payment starts on the order page.
export default function CheckoutPage() {
  const { user, withAccessToken } = useCustomerSession()
  const navigate = useNavigate()
  const location = useLocation()
  const userKey = user?.UserId ?? ''
  const cart = useApiData(`checkout-cart:${userKey}`, (signal) => withAccessToken((token) => getCart(token, { signal })))
  const addresses = useApiData(`addresses:${userKey}`, (signal) => withAccessToken((token) => listAddresses(token, { signal })))
  const shipping = useApiData('shipping-methods', (signal) => listShippingMethods({ signal }))
  const payment = useApiData('payment-methods', (signal) => listPaymentMethods({ signal }))
  const lines = (cart.data?.Items ?? []).filter((line) => line.IsSelected)
  const details = useProductDetails(lines.map((line) => line.ProductId))
  const coupon = useCartCoupon({ userId: user?.UserId, cart: cart.data, withAccessToken })

  // Choices left null follow the data: the default (else first) saved address, the first shipping/payment method.
  const [picked, setPicked] = useState(null)
  const [choosing, setChoosing] = useState(false)
  const [receiver, setReceiver] = useState(() => newReceiver(user))
  const [shippingId, setShippingId] = useState(null)
  const [paymentId, setPaymentId] = useState(null)
  const [note, setNote] = useState('')
  const [submitted, setSubmitted] = useState(false)
  // The order being sent. The ref is set at once, so a second click before the next render sends nothing.
  const [placing, setPlacing] = useState(false)
  const placingRef = useRef(false)
  // The last failed attempt (orderFailure) and, when its outcome is unknown, the check of the latest order.
  const [failure, setFailure] = useState(null)
  const [lookup, setLookup] = useState(null)
  const formRef = useRef(null)

  useEffect(() => {
    document.title = 'Xác nhận đặt hàng | VieTech'
  }, [])

  const saved = addresses.data ?? []
  const fallbackAddress = saved.find((address) => address.IsDefault) ?? saved[0]
  const mode = picked?.mode ?? (fallbackAddress ? 'saved' : 'new')
  const addressId = picked?.addressId ?? fallbackAddress?.AddressId ?? null
  const shippingMethods = shipping.data ?? []
  const paymentMethods = [...(payment.data ?? [])].sort((a, b) => a.DisplayOrder - b.DisplayOrder)
  const shippingMethodId = shippingId ?? shippingMethods[0]?.ShippingMethodId ?? null
  const paymentMethodId = paymentId ?? paymentMethods[0]?.PaymentMethodId ?? null
  const form = {
    delivery: mode === 'saved' ? { mode, addressId } : { mode, receiver },
    shippingMethodId,
    paymentMethodId,
    note,
    couponCode: coupon.status === 'ok' ? coupon.preview.Code : '',
  }
  const errors = {
    ...(failure && FIELD_PLACES.has(failure.place) ? { [failure.place]: failure.message } : {}),
    ...(submitted ? validateCheckout(form) : {}),
  }
  const waiting = addresses.loading || shipping.loading || payment.loading || coupon.status === 'checking'
  // An unknown outcome may be a placed order: nothing is sent again before the customer has checked.
  const unresolved = failure?.outcome === 'unknown' && lookup?.status !== 'done'
  const block = couponBlock(coupon, 'Hãy bỏ mã hoặc quay lại giỏ hàng để đổi mã.')
    || (unresolved ? 'Hãy kiểm tra đơn hàng trước khi đặt lại.' : '')

  function focusField(name) {
    formRef.current?.querySelector(`[data-field="${name}"]`)?.focus()
  }

  // A server error under a field goes once the customer changes that field.
  function settle(place) {
    setFailure((current) => (current?.place === place ? null : current))
  }

  function pickAddress(value) {
    setPicked(value === 'new' ? { mode: 'new', addressId } : { mode: 'saved', addressId: value })
    setChoosing(false)
    settle('address')
  }

  // What the page does about a rejected order (orderFailure `action`); the message says the rest.
  function follow(action) {
    if (action === 'reloadCart') cart.reload()
    else if (action === 'recheckCoupon') coupon.retry()
    else if (action === 'reloadAddresses') {
      addresses.reload()
      setPicked(null)
    } else if (action === 'reloadShipping') {
      shipping.reload()
      setShippingId(null)
    } else if (action === 'reloadPayment') {
      payment.reload()
      setPaymentId(null)
    }
  }

  // The order exists from here on. What is shown next comes from the server's answer (amounts, statuses), not from
  // this page's estimate; paying for it starts on the order page.
  function placed(order) {
    clearCartCoupon(user?.UserId)
    window.dispatchEvent(new Event('vietech-cart-changed'))
    const method = paymentMethods.find((item) => item.PaymentMethodId === order.PaymentMethodId)
    navigate(orderPath(order.OrderId), { replace: true, state: { order, paymentCode: method?.Code ?? null } })
  }

  async function submit(event) {
    event.preventDefault()
    if (placingRef.current || waiting || block) return
    setSubmitted(true)
    const found = validateCheckout(form)
    const first = FIELD_ORDER.find((name) => found[name])
    if (first) {
      focusField(first)
      return
    }
    placingRef.current = true
    setPlacing(true)
    setFailure(null)
    setLookup(null)
    try {
      placed(await withAccessToken((token) => createOrder(token, orderPayload(form))))
    } catch (error) {
      const result = orderFailure(error)
      setFailure(result)
      follow(result.action)
      if (FIELD_PLACES.has(result.place)) focusField(result.place)
    } finally {
      placingRef.current = false
      setPlacing(false)
    }
  }

  // The newest order of the customer (GET /orders is sorted by OrderedAt, newest first), and the cart again: a placed
  // order has taken its lines out of the cart.
  async function checkLatestOrder() {
    setLookup({ status: 'checking' })
    try {
      const page = await withAccessToken((token) => listMyOrders(token, { page: 1, page_size: 1 }))
      setLookup({ status: 'done', order: page.Items[0] ?? null })
      cart.reload()
    } catch (error) {
      setLookup({ status: 'error', message: error.message })
    }
  }

  const cartBlock = cart.data ? checkoutBlock(lines) : ''
  const showForm = !cart.loading && !cart.error && !cartBlock
  // The coupon verdict itself is shown by the coupon check once it has run again.
  const problem = failure && !FIELD_PLACES.has(failure.place) && !(failure.place === 'coupon' && coupon.status === 'invalid')
    ? <OrderProblem failure={failure} lookup={lookup} signInTo={`${LOGIN_PATH}${nextQuery(location)}`} onCheck={checkLatestOrder} />
    : null

  return <div className="checkout-page">
    <div className="checkout-card">
      <nav className="checkout-breadcrumb" aria-label="Đường dẫn">
        <ol>
          <li><Link to={HOME_PATH}>Trang chủ</Link></li>
          <li><Link to={CART_PATH}>Giỏ hàng</Link></li>
          <li aria-current="page">Xác nhận đặt hàng</li>
        </ol>
      </nav>
      <h1 className="checkout-title">Xác nhận đặt hàng</h1>
      <ol className="checkout-steps" aria-label="Các bước đặt hàng">
        {STEPS.map(([mark, label], index) => <li key={label} className={index === 1 ? 'is-current' : index === 0 ? 'is-done' : ''}
          aria-current={index === 1 ? 'step' : undefined}>
          <span aria-hidden="true">{mark}</span>{label}
        </li>)}
      </ol>
      {!showForm && problem}
      {cart.loading ? <LoadingState label="Đang tải đơn hàng…" />
        : cart.error ? <ErrorState title="Không thể tải đơn hàng" message={cart.error} onRetry={cart.reload} />
          : cartBlock ? <EmptyState title={lines.length ? 'Chưa thể đặt hàng' : 'Chưa có sản phẩm nào được chọn'}
            description={lines.length ? cartBlock : 'Hãy quay lại giỏ hàng và chọn sản phẩm bạn muốn mua.'}
            action={<Link className={buttonClassName({ variant: 'outline' })} to={CART_PATH}>Quay lại giỏ hàng</Link>} />
            : <form ref={formRef} className="checkout-columns" noValidate onSubmit={submit}>
              <div className="checkout-form">
                <CheckoutSection step="1" title="Thông tin khách hàng" id="checkout-customer">
                  <dl className="checkout-readonly">
                    <div><dt>Họ và tên</dt><dd>{user?.FullName || 'Chưa cập nhật'}</dd></div>
                    <div><dt>Số điện thoại</dt><dd>{user?.PhoneNumber || 'Chưa cập nhật'}</dd></div>
                    <div><dt>Email</dt><dd>{user?.Email || 'Chưa cập nhật'}</dd></div>
                  </dl>
                </CheckoutSection>
                <CheckoutSection step="2" title="Thông tin nhận hàng" id="checkout-delivery">
                  <AddressPicker addresses={addresses} mode={mode} addressId={addressId} receiver={receiver}
                    choosing={choosing} errors={errors} onToggle={() => setChoosing((open) => !open)} onPick={pickAddress}
                    onReceiverChange={(name, value) => {
                      setReceiver((current) => ({ ...current, [name]: value }))
                      settle('address')
                    }} />
                  <MethodGroup title="Phương thức vận chuyển" data={shipping} error={errors.shipping} field="shipping"
                    empty="Hiện chưa có phương thức vận chuyển khả dụng." loadingLabel="Đang tải phương thức vận chuyển…">
                    {shippingMethods.map((method) => <OptionCard key={method.ShippingMethodId} name="checkout-shipping"
                      value={method.ShippingMethodId} checked={method.ShippingMethodId === shippingMethodId} field="shipping"
                      title={method.Name} detail={shippingDetail(method)} onSelect={(id) => {
                        setShippingId(id)
                        settle('shipping')
                      }} />)}
                  </MethodGroup>
                </CheckoutSection>
                <CheckoutSection step="3" title="Ghi chú đơn hàng" id="checkout-note-title">
                  <textarea className="checkout-textarea" aria-labelledby="checkout-note-title" value={note} rows={3}
                    placeholder="Nhập ghi chú cho đơn hàng (không bắt buộc)" onChange={(event) => setNote(event.target.value)} />
                </CheckoutSection>
                <CheckoutSection step="4" title="Phương thức thanh toán" id="checkout-payment">
                  <MethodGroup title="Phương thức thanh toán" hideTitle stacked data={payment} error={errors.payment} field="payment"
                    empty="Hiện chưa có phương thức thanh toán khả dụng." loadingLabel="Đang tải phương thức thanh toán…">
                    {paymentMethods.map((method) => <OptionCard key={method.PaymentMethodId} name="checkout-payment"
                      value={method.PaymentMethodId} checked={method.PaymentMethodId === paymentMethodId} field="payment"
                      title={method.Name} detail={method.Description} onSelect={(id) => {
                        setPaymentId(id)
                        settle('payment')
                      }} />)}
                  </MethodGroup>
                  <p className="checkout-payment-note"><span aria-hidden="true">ⓘ</span>
                    Đơn hàng chỉ được tạo khi bạn xác nhận. Thanh toán trực tuyến (nếu chọn) được thực hiện sau khi đơn hàng được tạo.
                  </p>
                </CheckoutSection>
              </div>
              <CheckoutSummary cart={cart.data} lines={lines} details={details} waiting={waiting} placing={placing}
                shipping={shippingMethods.find((method) => method.ShippingMethodId === shippingMethodId)}
                coupon={coupon} block={block} orderProblem={problem}
                onRemoveCoupon={() => {
                  coupon.remove()
                  settle('coupon')
                }} onRetryCoupon={coupon.retry}
                onReload={() => { cart.reload(); coupon.retry() }} />
            </form>}
    </div>
  </div>
}

// A radio group of shipping or payment methods, with its loading, error and empty states.
function MethodGroup({ title, hideTitle = false, stacked = false, data, error, field, empty, loadingLabel, children }) {
  const errorId = `checkout-${field}-error`
  return <fieldset className={`checkout-options${stacked ? ' is-stacked' : ''}`} aria-describedby={error ? errorId : undefined}>
    <legend className={hideTitle ? 'sr-only' : 'checkout-legend'}>{title}</legend>
    {data.loading ? <p className="checkout-muted" role="status">{loadingLabel}</p>
      : data.error ? <p className="checkout-inline-error" role="alert">
        {data.error} <button type="button" onClick={data.reload}>Thử lại</button>
      </p>
        : !data.data?.length ? <p className="checkout-muted">{empty}</p> : children}
    {error && <p id={errorId} className="checkout-error">{error}</p>}
  </fieldset>
}
