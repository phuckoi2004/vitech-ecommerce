import { orderStatusLabel } from '../lib/orders.js'

const COLORS = {
  Pending: 'bg-[#fff7e6] text-[#f59e0b]',
  Confirmed: 'bg-admin-soft text-admin-blue',
  Processing: 'bg-admin-soft text-admin-blue',
  Shipping: 'bg-admin-page text-admin-muted',
  Delivered: 'bg-[#ecfdf5] text-[#16a34a]',
  Completed: 'bg-[#ecfdf5] text-[#16a34a]',
  Cancelled: 'bg-[#fff1f2] text-admin-red',
}

export default function OrderBadge({ value, className = '' }) {
  return <span className={'inline-block rounded-full px-2.5 py-1.5 text-[11px] font-semibold whitespace-nowrap ' + (COLORS[value] ?? 'bg-admin-page text-admin-muted') + ' ' + className}>{orderStatusLabel(value)}</span>
}
