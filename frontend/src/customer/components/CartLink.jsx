import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import cartIcon from '../../assets/icons/cart.svg'
import useApiData from '../../hooks/useApiData.js'
import useCustomerRequest from '../../hooks/useCustomerRequest.js'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { CART_PATH } from '../routes/paths.js'

export default function CartLink() {
  const { ready, user } = useCustomerSession()
  const send = useCustomerRequest()
  const cart = useApiData(ready && user ? `cart-count:${user.UserId}` : null, (signal) => send('/cart', { signal }))
  const reload = cart.reload
  const count = user ? (cart.data?.Items ?? []).reduce((total, item) => total + Number(item.Quantity || 0), 0) : 0
  useEffect(() => {
    function refresh() { if (!document.hidden) reload() }
    window.addEventListener('vietech-cart-changed', reload)
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      window.removeEventListener('vietech-cart-changed', reload)
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [reload])
  return <Link className="shop-action shop-cart" to={CART_PATH}>
    <span className="shop-action-text"><strong>Giỏ hàng</strong>
      {count > 0 && <span className="sr-only">, {count} sản phẩm</span>}</span>
    <img className="shop-action-icon" src={cartIcon} alt="" width="24" height="24" />
    {count > 0 && <span className="shop-cart-count" aria-hidden="true">{count > 99 ? '99+' : count}</span>}
  </Link>
}
