import { useNavigate } from 'react-router-dom'
import { monthLabel } from '../../lib/dashboard-periods.js'
import ReportChart from './ReportChart.jsx'

export default function RevenueChart({ months, state, today }) {
  const navigate = useNavigate()
  const points = months.map((month) => {
    const data = state.data?.find((point) => point.month === month)
    return { ...data?.data, DateFrom: month + '-01', Label: monthLabel(month) }
  })
  return <ReportChart title="Doanh số và lãi gộp 6 tháng" points={points} loading={state.loading} error={state.error} onRetry={state.refresh} currentMonth={today.slice(0, 7)}
    onPoint={(point) => navigate('/admin/reports?period=month&month=' + point.DateFrom.slice(0, 7))} />
}
