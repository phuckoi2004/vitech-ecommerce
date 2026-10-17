import { Link } from 'react-router-dom'

export default function CouponProgram({ promotion, busy = false }) {
  if (!promotion) return null
  return <Link to={'/admin/promotions?dialog=view&promotion=' + encodeURIComponent(promotion.PromotionId)} aria-disabled={busy || undefined} tabIndex={busy ? -1 : undefined} onClick={(event) => { if (busy) event.preventDefault() }} className={'self-start text-[11px] underline underline-offset-2 ' + (busy ? 'cursor-default text-admin-muted' : 'text-admin-blue')}>Xem chương trình và phạm vi áp dụng</Link>
}
