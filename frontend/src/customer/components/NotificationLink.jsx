import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import bellIcon from '../../assets/icons/bell.svg'
import useApiData from '../../hooks/useApiData.js'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { getUnreadNotificationCount } from '../../lib/account-api.js'
import { NOTIFICATIONS_PATH } from '../routes/paths.js'

// Header "Thông báo" entry. A signed-in customer sees a red dot while they have unread notifications (the count
// is read out to screen readers); for guests it only links to the notifications page, which asks them to sign in.
export default function NotificationLink() {
  const { ready, user, withAccessToken } = useCustomerSession()
  const unread = useApiData(ready && user ? `unread:${user.UserId}` : null,
    () => withAccessToken((token) => getUnreadNotificationCount(token)))
  const count = user ? unread.data?.Count ?? 0 : 0
  useEffect(() => {
    window.addEventListener('vietech-notifications-changed', unread.reload)
    return () => window.removeEventListener('vietech-notifications-changed', unread.reload)
  }, [unread.reload])

  return <Link className="shop-action shop-bell" to={NOTIFICATIONS_PATH}>
    <span className="shop-action-text">
      <strong>Thông báo</strong>
      {count > 0 && <span className="sr-only">, {count} chưa đọc</span>}
    </span>
    <img className="shop-action-icon" src={bellIcon} alt="" width="24" height="24" />
    {count > 0 && <span className="shop-bell-dot" aria-hidden="true" />}
  </Link>
}
