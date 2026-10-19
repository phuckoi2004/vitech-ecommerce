import detailIcon from '../assets/coupon-detail-source.svg'
import editIcon from '../assets/coupon-edit-source.svg'
import trashIcon from '../assets/coupon-trash-source.svg'
import { COUPON_STATUSES } from '../lib/coupons.js'

export function CouponStatus({ value }) {
  const color = { active: 'bg-[#16a34a] text-white', upcoming: 'bg-admin-soft text-admin-blue', exhausted: 'bg-admin-page text-admin-muted', expired: 'bg-admin-page text-admin-muted' }[value] ?? 'bg-admin-page text-admin-muted'
  return <span className={'inline-block rounded-full px-2.5 py-1.5 text-[11px] leading-[normal] font-semibold whitespace-nowrap ' + color}>{COUPON_STATUSES[value] ?? value}</span>
}
export function CouponAction({ kind, row, disabled, onClick }) {
  const label = { view: 'Chi tiết', edit: 'Sửa', delete: 'Xóa' }[kind]
  const source = { view: detailIcon, edit: editIcon, delete: trashIcon }[kind]
  return <button type="button" disabled={disabled} title={label + ' mã'} aria-label={label + ' mã ' + row.Code} onClick={onClick} className={'inline-grid size-[35px] shrink-0 cursor-pointer place-items-center rounded-[9px] border bg-white p-0 enabled:hover:bg-admin-page disabled:cursor-not-allowed disabled:opacity-40 ' + (kind === 'delete' ? 'border-admin-red' : 'border-admin-border')}><span className="relative block size-6 shrink-0" aria-hidden="true"><img src={source} alt="" data-coupon-icon={kind} className={'absolute max-w-none ' + (kind === 'view' ? 'top-[3px] left-[3px]' : kind === 'edit' ? 'top-[2.416px] left-[3.906px]' : 'top-0 left-0')} /></span></button>
}
