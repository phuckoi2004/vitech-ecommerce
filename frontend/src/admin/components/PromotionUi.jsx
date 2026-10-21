import detailIcon from '../assets/promotion-detail-source.svg'
import editIcon from '../assets/promotion-edit-source.svg'
import trashIcon from '../assets/promotion-trash-source.svg'
import { PROMOTION_STATUSES } from '../lib/promotions.js'
import { formatStatus } from '../../lib/status-labels.js'
import { ProductButton } from './ProductUi.jsx'

export { ProductButton as PromotionButton } from './ProductUi.jsx'
export function PromotionPopupButton({ secondary = false, danger = false, className = '', ...props }) {
  return <ProductButton secondary={secondary} className={'h-[37px]! px-[15px]! leading-[normal]! ' + (secondary ? danger ? 'border-admin-red! text-admin-red! enabled:hover:bg-red-50!' : 'text-admin-text!' : 'border-admin-red! bg-admin-red! enabled:hover:bg-admin-red/90!') + ' ' + className} {...props} />
}
export function PromotionStatus({ value }) {
  const color = { Draft: 'bg-admin-page text-admin-muted', Scheduled: 'bg-[#f59e0b] text-admin-text', Active: 'bg-[#16a34a] text-white', Expired: 'bg-admin-soft text-admin-blue', Cancelled: 'bg-red-50 text-admin-red' }[value] ?? 'bg-admin-page text-admin-muted'
  return <span className={'inline-block rounded-full px-2.5 py-1.5 text-[10px] leading-[normal] font-semibold whitespace-nowrap ' + color}>{formatStatus(value, PROMOTION_STATUSES)}</span>
}
export function PromotionAction({ kind, name, onClick }) {
  const label = { view: 'Chi tiết', edit: 'Sửa', delete: 'Xóa' }[kind]
  return <button type="button" aria-label={label + ' ' + name} title={label} onClick={onClick} className={'inline-grid size-[35px] shrink-0 cursor-pointer place-items-center rounded-[9px] border bg-white p-0 hover:bg-admin-page ' + (kind === 'delete' ? 'border-admin-red' : 'border-admin-border')}>
    <span className="relative block size-6 shrink-0" aria-hidden="true"><img alt="" data-promotion-icon={kind} src={kind === 'view' ? detailIcon : kind === 'edit' ? editIcon : trashIcon} className={'absolute max-w-none ' + (kind === 'view' ? 'top-[3px] left-[3px]' : kind === 'edit' ? 'top-[2.416px] left-[3.906px]' : 'top-0 left-0')} /></span>
  </button>
}
