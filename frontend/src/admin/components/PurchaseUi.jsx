import { ProductButton } from './ProductUi.jsx'
import { PURCHASE_STATUSES } from '../lib/purchases.js'

export function PurchaseButton({ secondary = false, className = '', ...props }) {
  return <ProductButton secondary={secondary} className={'h-[33px]! rounded-[9px]! px-[13px]! text-[11px]! ' + (secondary ? 'text-admin-text! ' : '') + className} {...props} />
}
export function PurchaseStatus({ status }) {
  const color = status === 'Pending' ? 'bg-[#f59e0b] text-admin-text' : ['Approved', 'Completed'].includes(status) ? 'bg-[#16a34a] text-white' : ['Rejected', 'Cancelled'].includes(status) ? 'bg-admin-red text-white' : 'bg-admin-soft text-admin-blue'
  return <span className={'inline-block rounded-full px-2 py-[5px] text-[9px] leading-[normal] font-semibold whitespace-nowrap ' + color}>{PURCHASE_STATUSES[status] ?? status}</span>
}
