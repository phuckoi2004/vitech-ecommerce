import { ProductButton } from './ProductUi.jsx'
import { returnStatusLabel } from '../lib/returns.js'

export function ReturnButton({ className = '', ...props }) {
  return <ProductButton className={'h-[33px]! rounded-[9px]! px-[13px]! text-[11px]! ' + className} {...props} />
}
export function ReturnStatus({ status }) {
  const color = status === 'Pending' ? 'bg-[#f59e0b] text-admin-text' : ['Processing', 'Completed'].includes(status) ? 'bg-[#16a34a] text-white' : status === 'Rejected' ? 'bg-admin-red text-white' : status === 'Cancelled' ? 'bg-admin-page text-admin-muted' : 'bg-admin-soft text-admin-blue'
  return <span className={'inline-block rounded-full px-[9px] py-[5px] text-[10px] leading-[normal] font-semibold ' + color}>{returnStatusLabel(status)}</span>
}
