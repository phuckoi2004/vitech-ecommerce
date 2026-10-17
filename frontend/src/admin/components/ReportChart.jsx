import { formatMoney } from '../../lib/format.js'

const SERIES = {
  revenue: [{ key: 'Revenue', label: 'Doanh thu', color: '#1677ff' }],
  orders: [{ key: 'TotalOrders', label: 'Tổng đơn', color: '#1677ff' }],
}
function axisLabel(value, revenue) {
  const unit = revenue ? (value >= 1e9 ? 1e9 : value >= 1e6 ? 1e6 : value >= 1e3 ? 1e3 : 1) : 1
  return (value / unit).toLocaleString('vi-VN', { maximumFractionDigits: 1 }) + (unit === 1e9 ? ' tỷ' : unit === 1e6 ? 'tr' : unit === 1e3 ? 'k' : '')
}

export default function ReportChart({ tab, points = [], loading, error }) {
  const series = SERIES[tab], revenue = tab === 'revenue'
  const hasData = points.some((point) => series.some(({ key }) => Number(point[key]) > 0))
  const max = Math.max(1, ...points.flatMap((point) => series.map(({ key }) => Number(point[key]) || 0)))
  const step = revenue ? 10 ** Math.floor(Math.log10(max)) : Math.max(1, 10 ** Math.floor(Math.log10(max)) / 2)
  const cap = Math.ceil(max / step) * step
  const ticks = hasData ? [...new Set(Array.from({ length: 6 }, (_, i) => revenue ? cap * i / 5 : Math.round(cap * i / 5)))] : [0]
  const y = (value) => 156 - value / cap * 148
  const groupWidth = 1000 / Math.max(points.length, 1), barWidth = Math.min(66, groupWidth / (series.length + 1.5))
  const title = revenue ? 'Doanh thu theo thời gian' : 'Số lượng đơn hàng theo thời gian'
  return <section aria-label={title} aria-busy={loading} className="min-h-[270px] min-w-0 rounded-[14px] border border-admin-border bg-white p-5">
    <header className="mb-3 flex flex-wrap items-center justify-between gap-3"><h3 className="m-0 text-base font-semibold">{title}</h3><div className="flex gap-2 text-xs text-admin-muted">{series.map((item) => <span key={item.key} className="flex items-center gap-[5px]"><span className="size-2 rounded-full" style={{ backgroundColor: revenue ? '#e11d2e' : item.color }} />{item.label}</span>)}</div></header>
    <div className="overflow-x-auto"><svg viewBox="0 0 1096 194" className="block h-[194px] min-w-[640px] w-full" role="img" aria-label={title}>
      {ticks.map((tick) => <g key={tick}><text x="0" y={y(tick) + 3} className="fill-admin-muted text-[8px]">{axisLabel(tick, revenue)}</text><line x1="52" x2="1052" y1={y(tick)} y2={y(tick)} className="stroke-admin-border" /></g>)}
      {!loading && !error && points.map((point, index) => <g key={point.DateFrom ?? index}>
        {series.map(({ key, label, color }, seriesIndex) => {
          const value = Number(point[key]) || 0, x = 52 + groupWidth * (index + 0.5) - (series.length * (barWidth + 6) - 6) / 2 + seriesIndex * (barWidth + 6)
          return value > 0 && <rect key={key} x={x} y={y(value)} width={barWidth} height={156 - y(value)} rx="5" fill={color} tabIndex={0} aria-label={`${point.Label}: ${label} ${revenue ? formatMoney(value) : value}`}><title>{point.Label}: {label} {revenue ? formatMoney(value) : value}</title></rect>
        })}
        <text x={52 + groupWidth * (index + 0.5)} y="180" textAnchor="middle" className="fill-admin-muted text-[8px]">{point.Label}</text>
      </g>)}
      {(!hasData || loading || error) && <text x="552" y="86" textAnchor="middle" className="fill-admin-muted text-[11px]">{loading ? 'Đang tải biểu đồ…' : error ? 'Không tải được biểu đồ.' : 'Chưa có dữ liệu trong kỳ đã chọn.'}</text>}
    </svg></div>
  </section>
}
