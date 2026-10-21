import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import useAdminQuery, { useAdminLoad } from '../hooks/useAdminQuery.js'
import useReportingDate from '../hooks/useReportingDate.js'
import { formatReport, getReportOptions } from '../services/reports.js'
import { REPORT_PAGE_SIZE, reportFilters, reportQuery, reportSearch } from '../lib/reports.js'
import ReportsWorkspace from '../components/ReportsWorkspace.jsx'
import ReportProductDetails from '../components/ReportProductDetails.jsx'
import ReportOrderDetails from '../components/ReportOrderDetails.jsx'

export default function ReportsPage() {
  const { permissions } = useInternalAuth(), [params, setParams] = useSearchParams()
  const today = useReportingDate()
  const tabs = ['revenue', 'orders', 'purchases'].filter((id) => id === 'purchases'
    ? permissions.includes('order_reports:view') && permissions.includes('purchases:view')
    : permissions.includes((id === 'revenue' ? 'revenue' : 'order') + '_reports:view'))
  const tab = tabs.includes(params.get('tab')) ? params.get('tab') : tabs[0]
  const filter = reportFilters(params), rawPage = Number(params.get('page')), page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1
  const orderKind = tab !== 'orders' ? null : params.get('delivered') === '1' ? 'delivered' : params.get('cancelled') === '1' ? 'cancelled' : null
  const rawOrderPage = Number(params.get(orderKind + '_page')), orderPage = Number.isSafeInteger(rawOrderPage) && rawOrderPage > 0 ? rawOrderPage : 1
  let query = {}, validation = ''
  try { query = reportQuery(filter, new Date(today + 'T12:00:00+07:00'), tab) } catch (failure) { validation = failure.message }
  const options = useAdminLoad(getReportOptions)
  const request = useAdminQuery('/admin/statistics/reports/' + tab, { ...query, ...(tab === 'revenue' ? { sort: filter.sort, group_by: 'variant' } : {}), page, page_size: REPORT_PAGE_SIZE }, !!tab && !validation)
  const orderRequest = useAdminQuery('/admin/statistics/reports/orders/' + (orderKind || 'cancelled'), { ...query, page: orderPage, page_size: REPORT_PAGE_SIZE }, !!orderKind && !validation)
  const state = { ...request, error: validation || request.error, data: formatReport(request.data, tab), refresh: () => { request.refresh(); orderRequest.refresh() } }
  const lastPage = Math.max(1, Math.ceil((state.data?.Total ?? 0) / REPORT_PAGE_SIZE))
  const lastOrderPage = Math.max(1, Math.ceil((orderRequest.data?.Total ?? 0) / REPORT_PAGE_SIZE))
  const search = params.toString()
  useEffect(() => {
    if (request.data && !request.loading && !request.error && page > lastPage) {
      const next = new URLSearchParams(search); next.set('page', String(lastPage)); setParams(next, { replace: true })
    }
  }, [request.data, request.loading, request.error, page, lastPage, search, setParams])
  useEffect(() => {
    if (orderKind && orderRequest.data && !orderRequest.loading && !orderRequest.error && orderPage > lastOrderPage) {
      const next = new URLSearchParams(search); next.set(orderKind + '_page', String(lastOrderPage)); setParams(next, { replace: true })
    }
  }, [orderKind, orderRequest.data, orderRequest.loading, orderRequest.error, orderPage, lastOrderPage, search, setParams])
  function update(change) { const next = new URLSearchParams(params); change(next); setParams(next) }
  function clearOrderDetails(next) {
    for (const key of ['cancelled', 'cancelled_page', 'delivered', 'delivered_page']) next.delete(key)
  }
  function closeOrderDetails() {
    document.getElementById('report-' + orderKind + '-trigger')?.focus()
    update(clearOrderDetails)
  }
  function toggleOrderDetails(kind) {
    if (orderKind === kind) return closeOrderDetails()
    update((next) => { clearOrderDetails(next); next.set(kind, '1') })
  }
  const detail = tab === 'revenue' ? params.get('detail') : null
  const detailVariant = tab === 'revenue' ? params.get('variant') : null
  const product = detail ? state.data?.Items?.find((row) => row.ProductId === detail && (row.ProductVariantId ?? null) === detailVariant) ?? (!detailVariant ? state.data?.TopProducts?.find((row) => row.ProductId === detail) : null) ?? { ProductId: detail, ProductVariantId: detailVariant, ProductName: options.data?.Products?.find((p) => p.Id === detail)?.Name ?? 'Chi tiết sản phẩm' } : null
  return <>
    <ReportsWorkspace tab={tab} tabs={tabs} filter={filter} options={options} state={state} page={page} canViewPurchases={permissions.includes('purchases:view')}
      onTab={(nextTab) => update((next) => { next.set('tab', nextTab); next.delete('page'); next.delete('detail'); next.delete('variant'); if (nextTab !== 'purchases') next.delete('supplier_id'); clearOrderDetails(next) })}
      onApply={(next) => { const search = reportSearch(next, tab); if (orderKind) search.set(orderKind, '1'); setParams(search) }}
      onPage={(nextPage) => update((next) => next.set('page', String(nextPage)))}
      onSort={(sort) => update((next) => { next.set('sort', sort); next.delete('page') })}
      onProduct={(row) => update((next) => { next.set('detail', row.ProductId); if (row.ProductVariantId) next.set('variant', row.ProductVariantId); else next.delete('variant') })}
      cancelledOpen={orderKind === 'cancelled'} onCancelled={() => toggleOrderDetails('cancelled')}
      deliveredOpen={orderKind === 'delivered'} onDelivered={() => toggleOrderDetails('delivered')}>
      {orderKind && !validation && <ReportOrderDetails key={orderKind} kind={orderKind} state={{ ...orderRequest, refresh: state.refresh }} query={query} page={orderPage} onPage={(nextPage) => update((next) => next.set(orderKind + '_page', String(nextPage)))} onClose={closeOrderDetails} canViewOrders={permissions.includes('orders:view')} />}
    </ReportsWorkspace>
    {product && !validation && <ReportProductDetails key={detail + ':' + detailVariant + JSON.stringify(query)} product={product} query={query} onClose={() => update((next) => { next.delete('detail'); next.delete('variant') })} />}
  </>
}
