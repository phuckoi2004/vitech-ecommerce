import { useSyncExternalStore } from 'react'
import { formatMoney } from '../../lib/format.js'

const query = '(max-width: 600px)'
const snapshot = () => window.matchMedia?.(query)?.matches ?? false
const subscribe = (listener) => {
  const media = window.matchMedia?.(query)
  media?.addEventListener('change', listener)
  return () => media?.removeEventListener('change', listener)
}
const serverSnapshot = () => false
function shortMoney(value) {
  const amount = Number(value), absolute = Math.abs(amount)
  const unit = absolute >= 1e9 ? 1e9 : absolute >= 1e6 ? 1e6 : 1
  return unit === 1 ? formatMoney(value) : (amount / unit).toLocaleString('vi-VN', { maximumFractionDigits: 2 }) + (unit === 1e9 ? ' tỷ ₫' : ' tr ₫')
}

export default function ReportMetric({ value, money }) {
  const compact = useSyncExternalStore(subscribe, snapshot, serverSnapshot)
  return <span title={String(value)} aria-label={String(value)}>{compact && money != null ? shortMoney(money) : value}</span>
}
