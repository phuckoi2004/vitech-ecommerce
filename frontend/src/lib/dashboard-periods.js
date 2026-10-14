// The browser's local clock chooses the months. API boundaries remain explicit calendar dates.
export function browserMonth(now = new Date()) {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

export function recentMonths(month, count = 5) {
  const [year, number] = month.split('-').map(Number)
  return Array.from({ length: count }, (_, index) => {
    const date = new Date(year, number - count + index, 1)
    return browserMonth(date)
  })
}

export function monthPeriod(month) {
  const [year, number] = month.split('-').map(Number)
  return { date_from: `${month}-01`, date_to: `${month}-${new Date(year, number, 0).getDate()}` }
}

export function growth(current, previous) {
  if (current == null || previous == null || Number(previous) <= 0) return null
  const percent = (Number(current) - Number(previous)) / Number(previous) * 100
  return Number.isFinite(percent) ? percent : null
}

export function monthLabel(month) {
  return `Tháng ${Number(month.slice(5))}/${month.slice(0, 4)}`
}
