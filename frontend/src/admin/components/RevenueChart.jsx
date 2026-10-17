import { ErrorState, LoadingState } from '../../components/shared/index.js'
import { formatMoney } from '../../lib/format.js'
import { monthLabel } from '../../lib/dashboard-periods.js'
import { AdminPanel } from './AdminTable.jsx'

function axisLabel(value) {
  const magnitude = Math.abs(value)
  const unit = magnitude >= 1e9 ? 1e9 : magnitude >= 1e6 ? 1e6 : magnitude >= 1e3 ? 1e3 : 1
  return `${(value / unit).toLocaleString('vi-VN', { maximumFractionDigits: 1 })}${unit === 1e9 ? ' tỷ' : unit === 1e6 ? ' tr' : unit === 1e3 ? ' nghìn' : ''}`
}

export default function RevenueChart({ months, state }) {
  const points = months.map((month) => state.data?.find((point) => point.month === month))
  const errors = points.map((point) => point?.error).filter(Boolean)
  const values = points.map((point) => Number(point?.data?.NetRevenue ?? 0))
  const hasData = points.some((point) => point?.data?.OrderCount > 0)
  const magnitude = Math.max(...values.map(Math.abs), 1)
  const unit = 10 ** Math.floor(Math.log10(magnitude))
  const cap = Math.ceil(magnitude / unit) * unit
  const bottom = Math.min(...values) < 0 ? -cap : 0
  const top = Math.max(...values) > 0 ? cap : bottom < 0 ? 0 : cap
  const y = (value) => 190 - (value - bottom) / (top - bottom) * 160
  const ticks = hasData ? Array.from({ length: 6 }, (_, index) => bottom + (top - bottom) * index / 5) : [0]

  return <AdminPanel title="Doanh thu theo tháng" className="flex min-h-[320px] w-full flex-col" action={<span className="rounded-[10px] border border-admin-border px-3 py-2 text-xs font-semibold">5 tháng gần đây</span>} aria-label="Doanh thu theo tháng">
    {state.loading ? <LoadingState label="Đang tải doanh thu…" className="flex-1" /> : state.error || errors.length ? <ErrorState title="Không tải được doanh thu" message={state.error || errors[0]} onRetry={state.refresh} className="flex-1 py-6" /> : <figure className="min-h-0 min-w-0 flex-1 overflow-x-auto" tabIndex={0} aria-label="Biểu đồ doanh thu, có thể cuộn ngang">
      {hasData ? <svg viewBox="0 0 660 230" className="block h-auto min-w-[660px] w-full" role="img" aria-label="Biểu đồ doanh thu 5 tháng gần nhất">
        {ticks.map((tick, index) => <g key={index}><text x="48" y={y(tick) + 3} textAnchor="end" fill="currentColor" className="text-[14px] text-admin-muted">{axisLabel(tick)}</text>{hasData && <line x1="65" x2="642" y1={y(tick)} y2={y(tick)} stroke="currentColor" className="text-admin-border" strokeDasharray="3 5" />}</g>)}
        {months.map((month, index) => {
          const x = 80 + index * 112
          return <g key={month}>
            {hasData && values[index] !== 0 && <rect x={x + 14} y={Math.min(y(values[index]), y(0))} width="44" height={Math.abs(y(values[index]) - y(0))} rx="6" fill="currentColor" className="text-admin-blue focus:outline-admin-blue" tabIndex={0} role="img" aria-label={`${monthLabel(month)}: ${formatMoney(values[index])}`}><title>{monthLabel(month)}: {formatMoney(values[index])}</title></rect>}
            <text x={x + 36} y="216" textAnchor="middle" fill="currentColor" className="text-[14px] text-admin-muted">{month.slice(5)}</text>
          </g>
        })}
      </svg> : <div role="img" aria-label="Chưa có dữ liệu doanh thu trong 5 tháng gần nhất" className="flex min-h-[220px] items-center justify-center text-center text-sm text-admin-muted">Chưa có dữ liệu doanh thu.</div>}
      <figcaption className="sr-only">{months.map((month, index) => `${monthLabel(month)}: ${formatMoney(values[index])}`).join('; ')}</figcaption>
    </figure>}
  </AdminPanel>
}
