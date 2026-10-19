import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { Pagination } from '../../components/shared/index.js'
import { formatMoney } from '../../lib/format.js'
import { useAdminLoad } from '../hooks/useAdminQuery.js'
import { getShippingMethods, updateShippingMethod } from '../services/shipping-methods.js'
import { filterShippingMethods, shippingDays, shippingFilters, SHIPPING_PAGE_SIZE, shippingPagePath } from '../lib/shipping-methods.js'
import AdminTable from '../components/AdminTable.jsx'
import { ShippingAction, ShippingButton, ShippingStatus } from '../components/ShippingUi.jsx'

export default function ShippingMethodsPage() {
  const auth = useInternalAuth(), navigate = useNavigate(), location = useLocation(), [params, setParams] = useSearchParams(), [notice, setNotice] = useState(location.state?.shippingNotice ?? '')
  const can = (action) => auth.user.Role === 'Admin' && auth.permissions.includes('shipping_methods:' + action)
  const [busy, setBusy] = useState(false), [failure, setFailure] = useState('')
  const writing = useRef(false), mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const list = useAdminLoad(getShippingMethods), filter = shippingFilters(params)
  const rows = filterShippingMethods(list.data ?? [], filter), days = [...new Set((list.data ?? []).map((row) => row.EstimatedDays))].sort((a, b) => a - b)
  const page = Math.min(filter.page, Math.max(1, Math.ceil(rows.length / SHIPPING_PAGE_SIZE)))
  function change(key, value) {
    setParams((previous) => { const next = new URLSearchParams(previous); if (value) next.set(key, value); else next.delete(key); next.delete('page'); return next }, { replace: true })
  }
  function open(mode, id) { navigate(shippingPagePath(mode, id, params)) }
  async function toggle(row) {
    if (writing.current || list.loading || !can('update')) return
    writing.current = true; setBusy(true); setFailure(''); setNotice('')
    try {
      await auth.withAccessToken((token) => updateShippingMethod(token, row.ShippingMethodId, { IsActive: !row.IsActive }))
      if (mounted.current) { list.refresh(); setNotice(row.IsActive ? 'Đã ngừng hoạt động phương thức vận chuyển.' : 'Đã kích hoạt phương thức vận chuyển.') }
    } catch (error) { if (mounted.current) setFailure(error.message) }
    finally { writing.current = false; if (mounted.current) setBusy(false) }
  }
  const columns = [
    { key: 'Code', label: 'Mã', className: 'w-[14.65%]', render: (code) => <span className="inline-block max-w-full rounded-[7px] bg-admin-soft px-2 py-1.5 text-[11px] font-bold break-words text-admin-blue">{code}</span> },
    { key: 'Name', label: 'Tên phương thức', className: 'w-[26.56%]', render: (name) => <span className="font-medium break-words">{name}</span> },
    { key: 'BaseFee', label: 'Phí cơ bản', className: 'w-[17.40%]', render: formatMoney },
    { key: 'EstimatedDays', label: 'Số ngày giao dự kiến', className: 'w-[17.40%]', render: shippingDays },
    { key: 'IsActive', label: 'Trạng thái', className: 'w-[13.28%] text-center', render: (active) => <ShippingStatus active={active} /> },
    { key: 'actions', label: 'Thao tác', className: 'w-[10.71%] text-center', render: (_, row) => can('update') && <div className="flex items-center justify-center gap-[3px] pr-1.5"><ShippingAction kind="edit" name={row.Name} disabled={busy} onClick={() => open('edit', row.ShippingMethodId)} /><ShippingAction kind="toggle" name={row.Name} active={row.IsActive} disabled={busy || list.loading} onClick={() => void toggle(row)} /></div> },
  ]
  const control = 'h-[42px] shrink-0 rounded-[10px] border border-admin-border bg-admin-page px-3.5 text-xs text-admin-text placeholder:text-admin-muted'
  return <section aria-label="Quản lý phương thức vận chuyển" className="flex min-w-0 flex-col gap-[18px] font-admin text-admin-text">
    <header className="flex h-[46px] items-center justify-between gap-3"><h2 className="m-0 text-xl leading-[normal] font-bold">Danh sách phương thức vận chuyển</h2>{can('create') && <ShippingButton className="w-40" onClick={() => open('new')}>+ Thêm phương thức</ShippingButton>}</header>
    <form role="search" aria-label="Lọc phương thức vận chuyển" onSubmit={(event) => event.preventDefault()} className="flex h-[66px] items-center gap-2.5 rounded-[14px] border border-admin-border bg-white p-3">
      <input type="search" aria-label="Tìm mã hoặc tên phương thức" placeholder="Tìm mã hoặc tên phương thức..." className={control + ' w-[360px]'} maxLength={255} value={filter.keyword} onChange={(event) => change('keyword', event.target.value)} />
      <select aria-label="Trạng thái" className={control + ' w-[180px]'} value={filter.status} onChange={(event) => change('status', event.target.value)}><option value="">Tất cả</option><option value="active">Đang hoạt động</option><option value="inactive">Ngừng hoạt động</option></select>
      <select aria-label="Thời gian giao dự kiến" className={control + ' w-[220px]'} value={filter.days} onChange={(event) => change('days', event.target.value)}><option value="">Tất cả</option>{days.map((day) => <option key={day} value={day}>{shippingDays(day)}</option>)}</select>
      <ShippingButton secondary className="ml-auto w-[84px]" onClick={() => setParams(new URLSearchParams(), { replace: true })}>Đặt lại</ShippingButton>
    </form>
    {notice && <p role="status" className="m-0 rounded-lg bg-green-50 p-3 text-xs text-green-700">{notice}</p>}
    {failure && <p role="alert" className="m-0 rounded-lg bg-red-50 p-3 text-xs text-admin-red">{failure}</p>}
    <section aria-label="Phương thức vận chuyển" className="admin-table-inset flex min-h-[588px] min-w-0 flex-col gap-3 rounded-[14px] border border-admin-border bg-white p-[18px]">
      <header className="flex h-9 items-center gap-2.5"><h3 className="m-0 text-[15px] leading-[normal] font-semibold">Phương thức vận chuyển</h3><span className="rounded-full bg-admin-soft px-[9px] py-[5px] text-[11px] font-semibold text-admin-blue">{list.loading || list.error ? '—' : rows.length} phương thức</span></header>
      <AdminTable variant="products" label="Danh sách phương thức vận chuyển" columns={columns} rows={rows.slice((page - 1) * SHIPPING_PAGE_SIZE, page * SHIPPING_PAGE_SIZE)} rowKey="ShippingMethodId" loading={list.loading} error={list.error} onRetry={list.refresh} emptyText={filter.keyword || filter.status || filter.days ? 'Không có phương thức vận chuyển phù hợp.' : 'Chưa có phương thức vận chuyển.'} className="min-w-[1020px] table-fixed [&_th]:h-[46px]! [&_th]:px-2.5! [&_th]:text-[13px]! [&_th]:font-semibold! [&_td]:h-[68px]! [&_td]:px-2.5! [&_td]:text-xs! [&_td:last-child]:px-0!" />
      {!list.loading && !list.error && <div className="mt-auto flex min-h-[42px] items-center [&>div]:w-full"><Pagination variant="admin" itemLabel="phương thức vận chuyển" label="Phân trang phương thức vận chuyển" page={page} pageSize={SHIPPING_PAGE_SIZE} total={rows.length} onPageChange={(value) => setParams((previous) => { const next = new URLSearchParams(previous); next.set('page', String(value)); return next })} /></div>}
    </section>
  </section>
}
