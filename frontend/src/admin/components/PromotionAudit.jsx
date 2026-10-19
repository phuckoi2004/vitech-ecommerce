import useInternalAuth from '../../hooks/useInternalAuth.js'
import { promotionDateTime } from '../lib/promotions.js'

export default function PromotionAudit({ row }) {
  const { user } = useInternalAuth()
  const creator = row.CreatedByName || (row.CreatedByUserId && row.CreatedByUserId === user?.UserId ? user.FullName : row.CreatedByUserId) || '—'
  const createdAt = row.CreatedAt && Number.isFinite(new Date(row.CreatedAt).getTime()) ? promotionDateTime(row.CreatedAt) : '—'
  return <dl aria-label="Thông tin tạo" className="m-0 grid grid-cols-[180px_minmax(0,1fr)] gap-x-2 gap-y-3 rounded-lg bg-admin-page p-3 text-xs">
    <dt className="font-medium text-admin-muted">Người tạo</dt><dd className="m-0 break-words font-semibold">{creator}</dd>
    <dt className="font-medium text-admin-muted">Ngày tạo</dt><dd className="m-0 font-semibold">{createdAt}</dd>
  </dl>
}
