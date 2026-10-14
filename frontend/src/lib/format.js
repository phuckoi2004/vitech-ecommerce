// Display formats for Vietnamese users. Times are shown in Vietnam time whatever the browser's time zone.

export const VIETNAM_TIME_ZONE = 'Asia/Ho_Chi_Minh'
const FALLBACK = '—'

const moneyFormat = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 })
const dateTimeFormat = new Intl.DateTimeFormat('vi-VN', {
  timeZone: VIETNAM_TIME_ZONE, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})
const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/

// Money from the API is numeric(15,2) sent as a string ("15000000.00") or a number: "15.000.000 ₫".
export function formatMoney(value, { fallback = FALLBACK } = {}) {
  if (value === null || value === undefined || value === '') return fallback
  const amount = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(amount) ? moneyFormat.format(amount) : fallback
}

const oneDecimal = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 })

// Short counts for product cards: 950 → "950", 1200 → "1,2k", 2_500_000 → "2,5tr".
export function formatCompactCount(value) {
  const count = Math.max(0, Math.floor(Number(value) || 0))
  if (count < 1000) return String(count)
  if (count < 1_000_000) return `${oneDecimal.format(Math.floor(count / 100) / 10)}k`
  return `${oneDecimal.format(Math.floor(count / 100_000) / 10)}tr`
}

// Average rating with one decimal, Vietnamese style: "4.80" → "4,8".
export function formatRating(value) {
  const rating = Number(value)
  return Number.isFinite(rating) ? rating.toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : ''
}

function vietnamParts(value) {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return Object.fromEntries(dateTimeFormat.formatToParts(date).map((part) => [part.type, part.value]))
}

// "dd/MM/yyyy". A date-only value ("2004-05-17", e.g. DateOfBirth) is a calendar date and is not shifted by time zones.
export function formatDate(value, { fallback = FALLBACK } = {}) {
  if (value === null || value === undefined || value === '') return fallback
  const dateOnly = typeof value === 'string' ? DATE_ONLY.exec(value) : null
  if (dateOnly) return `${dateOnly[3]}/${dateOnly[2]}/${dateOnly[1]}`
  const parts = vietnamParts(value)
  return parts ? `${parts.day}/${parts.month}/${parts.year}` : fallback
}

// "HH:mm dd/MM/yyyy" in Vietnam time, for timestamps such as OrderedAt.
export function formatDateTime(value, { fallback = FALLBACK } = {}) {
  if (value === null || value === undefined || value === '') return fallback
  const parts = vietnamParts(value)
  return parts ? `${parts.hour}:${parts.minute} ${parts.day}/${parts.month}/${parts.year}` : fallback
}
