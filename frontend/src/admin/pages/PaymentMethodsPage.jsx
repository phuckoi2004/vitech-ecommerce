import { useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { useAdminLoad } from '../hooks/useAdminQuery.js'
import { getPaymentMethods } from '../services/payment-methods.js'
import AdminTable from '../components/AdminTable.jsx'
import PaymentMethodDialog from '../components/PaymentMethodDialog.jsx'
import PaymentResultDialog from '../components/PaymentResultDialog.jsx'
import { paymentPagePath } from '../lib/payment-methods.js'
import { PaymentAction, PaymentButton, PaymentStatus } from '../components/PaymentMethodUi.jsx'
import AdminResourcePage from './AdminResourcePage.jsx'

export default function PaymentMethodsPage() {
  const auth = useInternalAuth(), [params, setParams] = useSearchParams(), navigate = useNavigate(), [success, setSuccess] = useState(false)
  const legacyTransactions = params.get('tab') === '1'
  const can = (action) => auth.user.Role === 'Admin' && auth.permissions.includes('payment_methods:' + action)
  const list = useAdminLoad(getPaymentMethods, !legacyTransactions && auth.permissions.includes('payment_methods:view'))
  function open(dialog, id) {
    if (['new', 'edit'].includes(dialog)) { navigate(paymentPagePath(dialog, id, params)); return }
    setParams((previous) => { const next = new URLSearchParams(previous); if (dialog) next.set('dialog', dialog); else next.delete('dialog'); if (id) next.set('method', id); else next.delete('method'); return next })
  }
  function done() { list.refresh(); open(null); setSuccess(true) }
  const mode = params.get('dialog'), id = params.get('method'), permission = ({ new: 'create', edit: 'update', delete: 'delete' })[mode]
  const columns = [
    { key: 'Code', label: 'Mã', className: 'w-[13.30%]', render: (value) => <span className="break-words">{value}</span> },
    { key: 'Name', label: 'Tên phương thức', className: 'w-[19.06%]', render: (value) => <span className="break-words">{value}</span> },
    { key: 'Description', label: 'Mô tả / hướng dẫn', className: 'w-[34.57%]', render: (value) => <span className="break-words whitespace-pre-wrap">{value || '—'}</span> },
    { key: 'IsActive', label: 'Trạng thái', className: 'w-[12.41%]', render: (value) => <PaymentStatus active={value} /> },
    { key: 'DisplayOrder', label: 'Thứ tự', className: 'w-[9.75%]' },
    { key: 'actions', label: 'Thao tác', className: 'w-[10.91%]', render: (_, row) => <div className="flex items-center gap-1.5">{can('update') && <PaymentAction action="edit" name={row.Name} onClick={() => open('edit', row.PaymentMethodId)} />}{can('delete') && <PaymentAction action="delete" name={row.Name} onClick={() => open('delete', row.PaymentMethodId)} />}{!can('update') && !can('delete') && <span className="text-admin-muted">—</span>}</div> },
  ]
  // Keep the previous transaction-list bookmark; the default view follows the payment-method design.
  if (legacyTransactions) return <AdminResourcePage section={{ id: 'payments', label: 'Thanh toán' }} />
  if (permission && can(permission) && ['new', 'edit'].includes(mode) && (mode === 'new' || id)) return <Navigate to={paymentPagePath(mode, id, params)} replace />
  return <section aria-label="Quản lý thanh toán" className="-mt-1 flex min-w-0 flex-col gap-3.5">
    <header className="flex min-h-11 items-center justify-between"><div><h2 className="m-0 text-xl leading-6 font-bold">Phương thức thanh toán</h2><p className="mt-0.5 mb-0 text-[10px] leading-3 text-admin-muted">Thêm, sửa hoặc xóa các phương thức thanh toán khách hàng có thể lựa chọn</p></div><div className="flex"><PaymentButton secondary className="text-admin-text!" disabled={list.loading} onClick={list.refresh}>Làm mới</PaymentButton>{can('create') && <PaymentButton onClick={() => open('new')}>+ Thêm phương thức</PaymentButton>}</div></header>
    <section aria-label="Danh sách phương thức thanh toán" className="overflow-hidden rounded-xl border border-admin-border bg-white">
      <header className="flex items-center justify-between px-3.5 py-[13px]"><h3 className="m-0 text-[13px] leading-4 font-semibold">Danh sách phương thức thanh toán</h3><span className="text-[9px] text-admin-muted">{list.loading || list.error ? '—' : (list.data ?? []).length} phương thức</span></header>
      <AdminTable columns={columns} rows={list.data ?? []} rowKey="PaymentMethodId" label="Bảng phương thức thanh toán" loading={list.loading} error={list.error} onRetry={list.refresh} emptyText="Chưa có phương thức thanh toán." className="min-w-[1000px] table-fixed [&_th]:h-[46px]! [&_th]:border-b-0! [&_th]:px-2! [&_th]:text-[8px]! [&_th]:font-semibold! [&_td]:h-[76px]! [&_td]:px-2! [&_td]:py-0! [&_td]:text-[9px]! [&_tr:last-child_td]:border-b-0!" />
    </section>
    <aside aria-label="Quy tắc quản lý thanh toán" className="flex flex-col gap-1 rounded-[10px] border border-admin-border bg-admin-page px-3.5 py-3"><h3 className="m-0 text-[10px] leading-3 font-semibold">Quy tắc quản lý</h3><p className="m-0 text-[9px] leading-[11px] text-admin-muted">Những thay đổi được lưu vào hệ thống và phương thức đang hoạt động sẽ là lựa chọn khả dụng cho khách hàng khi thanh toán.</p></aside>
    {mode === 'delete' && can('delete') && id && <PaymentMethodDialog key={id} methodId={id} onClose={() => open(null)} onDone={done} />}
    {success && <PaymentResultDialog success onClose={() => setSuccess(false)} />}
  </section>
}
