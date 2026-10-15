import { ProductButton } from './ProductUi.jsx'
import { warrantyStage, warrantyStageLabel } from '../lib/warranties.js'

export function WarrantyButton({ className = '', ...props }) {
  return <ProductButton className={'h-[33px]! rounded-[9px]! px-[13px]! text-[11px]! ' + className} {...props} />
}
export function WarrantyStatus({ item }) {
  const stage = warrantyStage(item)
  const color = stage === 'New' ? 'bg-[#f59e0b] text-admin-text' : ['Finished', 'Returned'].includes(stage) ? 'bg-[#16a34a] text-white' : stage === 'Rejected' ? 'bg-admin-red text-white' : stage === 'Cancelled' ? 'bg-admin-page text-admin-muted' : 'bg-admin-soft text-admin-blue'
  return <span className={'inline-block rounded-full px-[9px] py-[5px] text-[10px] leading-[normal] font-semibold ' + color}>{warrantyStageLabel(stage)}</span>
}
