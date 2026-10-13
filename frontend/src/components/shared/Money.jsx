import { formatMoney } from '../../lib/format.js'

// A VND amount from the API ("15000000.00" or a number), e.g. "15.000.000 ₫".
export default function Money({ value, className = '' }) {
  return <span className={`tabular-nums ${className}`}>{formatMoney(value)}</span>
}
