// Calendar dates used by reporting are always Vietnam dates, regardless of the device timezone.
export function vietnamToday(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now)
  const value = (type) => parts.find((part) => part.type === type).value
  return `${value('year')}-${value('month')}-${value('day')}`
}
export const browserMonth = (now = new Date()) => vietnamToday(now).slice(0, 7)

export function recentMonths(month, count = 5) {
  const [year, number] = month.split('-').map(Number)
  return Array.from({ length: count }, (_, index) => {
    const date = new Date(Date.UTC(year, number - count + index, 1))
    return date.toISOString().slice(0, 7)
  })
}
export function monthPeriod(month) {
  const [year, number] = month.split('-').map(Number)
  return { date_from: month + '-01', date_to: month + '-' + new Date(Date.UTC(year, number, 0)).getUTCDate() }
}
export function monthToDate(today = vietnamToday()) {
  return { date_from: today.slice(0, 7) + '-01', date_to: today }
}
export function previousMonthToDate(today = vietnamToday()) {
  const previous = recentMonths(today.slice(0, 7), 2)[0]
  const end = Math.min(Number(today.slice(8)), Number(monthPeriod(previous).date_to.slice(8)))
  return { date_from: previous + '-01', date_to: previous + '-' + String(end).padStart(2, '0') }
}
export function growth(current, previous) {
  if (current == null || previous == null || Number(previous) <= 0) return null
  const percent = (Number(current) - Number(previous)) / Number(previous) * 100
  return Number.isFinite(percent) ? percent : null
}
export const monthLabel = (month) => `Tháng ${Number(month.slice(5))}/${month.slice(0, 4)}`
