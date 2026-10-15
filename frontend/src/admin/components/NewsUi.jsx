import { ProductButton } from './ProductUi.jsx'
import { NEWS_STATUSES } from '../lib/news.js'
import detail from '../assets/supplier-detail.svg'
import edit from '../assets/supplier-edit.svg'
import trash from '../assets/supplier-trash.svg'

export function NewsButton({ className = '', ...props }) {
  return <ProductButton className={'h-[30px]! rounded-[9px]! px-[13px]! text-[10px]! ' + className} {...props} />
}
export function NewsStatus({ status }) {
  const color = status === 'Published' ? 'bg-admin-blue text-white' : status === 'Draft' ? 'bg-[#f59e0b] text-admin-text' : 'border border-admin-border bg-admin-page text-admin-muted'
  return <span className={'inline-block rounded-full px-2 py-[5px] text-[9px] leading-[11px] font-semibold whitespace-nowrap ' + color}>{NEWS_STATUSES[status] ?? status}</span>
}
export function NewsAction({ action, title, disabled, onClick }) {
  const [label, src] = ({ view: ['Xem', detail], edit: ['Sửa', edit], delete: ['Xóa', trash] })[action]
  return <button type="button" aria-label={label + ' ' + title} title={label} disabled={disabled} onClick={onClick} className={'grid size-[35px] shrink-0 cursor-pointer place-items-center rounded-[9px] border bg-white disabled:cursor-wait disabled:opacity-50 ' + (action === 'delete' ? 'border-admin-red hover:bg-red-50' : 'border-admin-border hover:bg-admin-soft')}><img src={src} alt="" /></button>
}
