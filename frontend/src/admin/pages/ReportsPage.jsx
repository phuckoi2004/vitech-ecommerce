import { useState } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import useAdminQuery, { useAdminLoad } from '../hooks/useAdminQuery.js'
import { formatReport, getReportOptions } from '../services/reports.js'
import { defaultReportFilters, REPORT_PAGE_SIZE, reportQuery } from '../lib/reports.js'
import ReportsWorkspace from '../components/ReportsWorkspace.jsx'

export default function ReportsPage() {
  const { visit } = useOutletContext()
  // Selecting the sidebar again starts fresh; changing tabs preserves the applied filters.
  return <ReportsPageContent key={visit} />
}

function ReportsPageContent() {
  const { permissions } = useInternalAuth(), [params, setParams] = useSearchParams()
  const tabs = ['revenue', 'orders'].filter((id) => permissions.includes((id === 'revenue' ? 'revenue' : 'order') + '_reports:view'))
  const tab = tabs.includes(params.get('tab')) ? params.get('tab') : tabs[0]
  const [filter, setFilter] = useState(defaultReportFilters)
  const [paging, setPaging] = useState({ tab, page: 1 })
  const page = paging.tab === tab ? paging.page : 1
  const setPage = (value) => setPaging({ tab, page: value })
  const options = useAdminLoad(getReportOptions)
  // Recompute preset calendar dates on render so applying/refreshing follows the computer's clock.
  const query = useAdminQuery('/admin/statistics/reports/' + tab, { ...reportQuery(filter), page, page_size: REPORT_PAGE_SIZE }, !!tab)
  const state = { ...query, data: formatReport(query.data, tab) }
  const lastPage = Math.max(1, Math.ceil((state.data?.Total ?? 0) / REPORT_PAGE_SIZE))
  if (state.data && !state.loading && !state.error && page > lastPage) setPage(lastPage)
  function onTab(next) {
    setPage(1)
    setParams((previous) => { const nextParams = new URLSearchParams(previous); if (next === 'revenue') nextParams.delete('tab'); else nextParams.set('tab', next); return nextParams })
  }
  return <ReportsWorkspace tab={tab} tabs={tabs} filter={filter} onTab={onTab}
    onApply={(next) => { setFilter(next); setPage(1) }} options={options} state={state} page={page} onPage={setPage} />
}
