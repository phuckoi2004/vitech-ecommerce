import { Link } from 'react-router-dom'
import bellIcon from '../../assets/icons/bell.svg'
import useNotificationData from '../hooks/useNotificationData.js'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { getUnreadNotificationCount } from '../../lib/account-api.js'
import { NOTIFICATIONS_PATH } from '../routes/paths.js'

// Header "Thông báo" entry. A signed-in customer sees a red dot while they have unread notifications (the count
// is read out to screen readers); for guests it only links to the notifications page, which asks them to sign in.
export default function NotificationLink() {
  const { ready, user, withAccessToken } = useCustomerSession()
  const unread = useNotificationData(ready && user ? `unread:${user.UserId}` : null,
    (signal) => withAccessToken((token) => getUnreadNotificationCount(token, { signal })))
  const count = user ? unread.data?.Count ?? 0 : 0
  return <div className="shop-notification-entry"><Link className="shop-action shop-bell" to={NOTIFICATIONS_PATH} aria-busy={unread.refreshing || undefined}>
    <span className="shop-action-text">
      <strong>Thông báo</strong>
      {count > 0 && <span className="sr-only">, {count} chưa đọc</span>}
    </span>
    <img className="shop-action-icon" src={bellIcon} alt="" width="24" height="24" />
    {count > 0 && <span className="shop-bell-dot" aria-hidden="true" />}
  </Link>
    {user && unread.error && <div className="shop-notification-error" role="alert" aria-label="Không cập nhật được thông báo">
      <span>Chưa cập nhật được số thông báo chưa đọc.</span>
      <button type="button" disabled={unread.refreshing} onClick={unread.reload}>Thử lại</button>
    </div>}
  </div>
}
