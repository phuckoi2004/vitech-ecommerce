import { useEffect, useRef, useState } from 'react'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import { formatMoney } from '../../lib/format.js'

const ORDER_SERIES = [{ key: 'InProgressOrders', label: 'Đang xử lý', color: '#f59e0b' }, { key: 'DeliveredOrders', label: 'Đã giao', color: '#16a34a' }, { key: 'CancelledOrders', label: 'Đã hủy', color: '#e11d2e' }]
function chartMoney(value) {
  const abs = Math.abs(value), unit = abs >= 1e9 ? 1e9 : abs >= 1e6 ? 1e6 : abs >= 1e3 ? 1e3 : 1
  return (value / unit).toLocaleString('vi-VN', { maximumFractionDigits: 1 }) + (unit === 1e9 ? ' tỷ' : unit === 1e6 ? ' tr' : unit === 1e3 ? ' nghìn' : '')
}
export default function ReportChart({ tab = 'revenue', points = [], loading, error, onRetry, onPoint, currentMonth, title: givenTitle }) {
  const container = useRef(null), [chartWidth, setChartWidth] = useState(800)
  useEffect(() => {
    const element = container.current
    if (!element) return
    const update = () => setChartWidth(Math.max(240, Math.floor(element.getBoundingClientRect().width) || 800))
    update()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update)
    observer?.observe(element)
    return () => observer?.disconnect()
  }, [loading, error])
  const revenue = tab === 'revenue', title = givenTitle ?? (revenue ? 'Doanh số và lãi gộp theo thời gian' : 'Đơn đặt theo trạng thái hiện tại')
  const hasData = points.some((p) => Number(p.TotalOrders) > 0 || Number(p.Revenue) !== 0 && p.Revenue != null)
  const values = points.flatMap((p) => revenue ? [Number(p.Revenue) || 0, Number(p.Profit) || 0] : [Number(p.TotalOrders) || 0])
  const magnitude = Math.max(1, ...values.map(Math.abs)), step = 10 ** Math.floor(Math.log10(magnitude))
  const high = Math.max(1, Math.ceil(Math.max(0, ...values) / step) * step), low = Math.floor(Math.min(0, ...values) / step) * step
  const y = (value) => 210 - (value - low) / (high - low) * 180
  const plotWidth = chartWidth - 100
  const x = (i) => 78 + plotWidth / Math.max(points.length, 1) * (i + .5)
  const width = Math.min(54, plotWidth / Math.max(points.length, 1) * .6)
  const months = points.every((point) => point.Label?.startsWith('Tháng '))
  const crossYear = new Set(points.map((point) => point.DateFrom?.slice(0, 4))).size > 1
  const labelStep = Math.max(1, Math.ceil(points.length / Math.max(2, Math.floor(plotWidth / (months && chartWidth < 500 ? 32 : 55)))))
  const ticks = hasData ? [...new Set(Array.from({ length: 5 }, (_, i) => revenue ? low + (high - low) * i / 4 : Math.round(high * i / 4)))] : [0]
  const segments = []
  if (revenue) for (let i = 0; i < points.length; i++) {
    if (points[i].Profit == null) { if (segments.at(-1)?.length) segments.push([]) }
    else { if (!segments.length) segments.push([]); segments.at(-1).push([x(i), y(Number(points[i].Profit))]) }
  }
  const legend = revenue ? [{ label: 'Doanh số', color: '#1677ff' }, { label: 'Lãi gộp', color: '#16a34a' }] : ORDER_SERIES
  return <section aria-label={title} aria-busy={loading} className="min-w-0 rounded-[14px] border border-admin-border bg-white p-5">
    <header className="mb-3 flex flex-wrap items-center justify-between gap-3"><h3 className="m-0 text-base font-semibold">{title}</h3><div className="flex flex-wrap gap-4 text-xs text-admin-muted">{legend.map((s) => <span key={s.label} className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ backgroundColor: s.color }} />{s.label}</span>)}</div></header>
    {loading ? <LoadingState className="min-h-[250px]" label="Đang tải biểu đồ…" /> : error ? <ErrorState title="Không tải được biểu đồ" message={error} onRetry={onRetry} className="min-h-[250px]" /> : <figure className="m-0">
      <div ref={container} className="overflow-x-auto"><svg viewBox={'0 0 ' + chartWidth + ' 260'} className="block h-[260px] min-w-0 w-full" role="img" aria-label={title}>
        {ticks.map((tick) => <g key={tick}><text x="66" y={y(tick) + 4} textAnchor="end" className="fill-admin-muted text-[12px]">{revenue ? chartMoney(tick) : tick}</text><line x1="78" x2={chartWidth - 22} y1={y(tick)} y2={y(tick)} stroke="#e4eaf2" strokeDasharray="3 4" /></g>)}
        {low < 0 && <line x1="78" x2={chartWidth - 22} y1={y(0)} y2={y(0)} stroke="#60708a" />}
        {points.map((point, i) => {
          const total = Number(point.TotalOrders) || 0, value = Number(point.Revenue) || 0
          const partial = currentMonth && point.DateFrom?.startsWith(currentMonth)
          const description = point.Label + (partial ? ' (chưa hết tháng)' : '') + ': ' + (revenue ? formatMoney(value) + ', lãi gộp ' + (point.Profit == null ? 'chưa đủ dữ liệu' : formatMoney(point.Profit)) : total + ' đơn')
          let cumulative = 0
          return <g key={point.DateFrom ?? i} role={onPoint ? 'link' : undefined} tabIndex={onPoint ? 0 : undefined} aria-label={onPoint ? 'Xem báo cáo ' + description : undefined} onClick={onPoint ? () => onPoint(point) : undefined} onKeyDown={onPoint ? (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onPoint(point) } } : undefined} className={onPoint ? 'cursor-pointer' : ''}>
            <title>{description}</title>
            {onPoint && <rect x={x(i) - width / 2 - 10} y="20" width={width + 20} height="200" fill="transparent" />}
            {revenue ? value !== 0 && <rect x={x(i) - width / 2} y={Math.min(y(value), y(0))} width={width} height={Math.abs(y(value) - y(0))} rx="4" fill="#1677ff" opacity={partial ? .55 : 1} /> : ORDER_SERIES.map((series) => {
              const count = Number(point[series.key]) || 0
              cumulative += count
              return count > 0 && <rect key={series.key} x={x(i) - width / 2} y={y(cumulative)} width={width} height={y(0) - y(count)} fill={series.color}><title>{point.Label}: {series.label} {count}</title></rect>
            })}
            {(i === points.length - 1 || i % labelStep === 0 && (i === 0 || points.length - 1 - i >= labelStep * .65)) && <text x={x(i)} y="237" textAnchor="middle" className="fill-admin-muted text-[12px]">{months && chartWidth < 500 ? point.DateFrom?.slice(5, 7) + (crossYear ? '/' + point.DateFrom?.slice(2, 4) : '') : point.Label.replace('Tháng ', '')}{partial ? '*' : ''}</text>}
          </g>
        })}
        {hasData && revenue && segments.filter((s) => s.length).map((s, i) => <polyline key={i} points={s.map((p) => p.join(',')).join(' ')} fill="none" stroke="#16a34a" strokeWidth="3" pointerEvents="none" />)}
        {hasData && revenue && points.map((p, i) => p.Profit != null && <circle key={i} cx={x(i)} cy={y(Number(p.Profit))} r="4" fill={Number(p.Profit) < 0 ? '#e11d2e' : '#16a34a'} pointerEvents="none" />)}
        {!hasData && <text x={78 + plotWidth / 2} y="126" textAnchor="middle" className="fill-admin-muted text-sm">Chưa có dữ liệu trong kỳ đã chọn.</text>}
      </svg></div>
      <figcaption className="mt-1 text-xs text-admin-muted">{onPoint ? 'Bấm vào một tháng để xem báo cáo. * Tháng hiện tại chưa kết thúc.' : revenue ? 'Theo ngày giao hàng. Lãi gộp trước điều chỉnh trả hàng; điểm thiếu giá nhập không được nối đường.' : 'Theo ngày đặt hàng; trạng thái được cập nhật đến thời điểm xem báo cáo.'}</figcaption>
    </figure>}
  </section>
}
