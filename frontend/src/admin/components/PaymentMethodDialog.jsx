import { useEffect, useRef, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import useAdminQuery from '../hooks/useAdminQuery.js'
import { deletePaymentMethod } from '../services/payment-methods.js'
import Modal from './Modal.jsx'
import PaymentResultDialog from './PaymentResultDialog.jsx'
import { PaymentButton } from './PaymentMethodUi.jsx'

// Forms are routed pages. Only confirmation and result notifications are dialogs.
export default function PaymentMethodDialog({ methodId, onClose, onDone }) {
  const auth = useInternalAuth()
  const permitted = auth.user.Role === 'Admin' && auth.permissions.includes('payment_methods:view') && auth.permissions.includes('payment_methods:delete')
  const detail = useAdminQuery('/payment-methods/' + encodeURIComponent(methodId), {}, permitted)
  const [busy, setBusy] = useState(false), [failure, setFailure] = useState(null)
  const writing = useRef(false), mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  async function remove() {
    if (!permitted || writing.current || !detail.data || detail.loading || detail.error) return
    writing.current = true; setBusy(true)
    try {
      await auth.withAccessToken((token) => deletePaymentMethod(token, methodId))
      if (mounted.current) onDone()
    } catch (error) { if (mounted.current) setFailure(error.message) }
    finally { writing.current = false; if (mounted.current) setBusy(false) }
  }
  if (!permitted) return null
  if (failure !== null) return <PaymentResultDialog deleting message={failure} busy={busy} onClose={onClose} onRetry={() => void remove()} />
  const method = detail.data
  return <Modal variant="news-delete" open title="Xóa phương thức thanh toán?" className="min-h-[290px] w-[470px]" busy={busy} onClose={onClose}>
    {detail.loading ? <LoadingState label="Đang tải phương thức thanh toán…" /> : detail.error ? <ErrorState message={detail.error} onRetry={detail.refresh} /> : method ? <>
      <p className="m-0 text-[10px] leading-3 break-words text-admin-muted">Bạn có chắc chắn muốn xóa phương thức “{method.Name}” khỏi hệ thống không?</p>
      <div className="mt-3 flex w-fit max-w-full flex-col gap-1 rounded-lg bg-admin-page px-3 py-2.5"><p className="m-0 text-[10px] leading-3 font-semibold break-words">{method.Code} • {method.Name}</p><p className="m-0 text-[9px] leading-[11px] text-admin-muted">Trạng thái hiện tại: {method.IsActive ? 'Hoạt động' : 'Ngừng hoạt động'}</p></div>
      <div className="mt-3 flex justify-end"><PaymentButton secondary className="text-admin-text!" disabled={busy} onClick={onClose}>Hủy</PaymentButton><PaymentButton secondary className="border-admin-red! text-admin-red! hover:bg-red-50!" loading={busy} onClick={() => void remove()}>Xác nhận xóa</PaymentButton></div>
    </> : <p>Không tìm thấy phương thức thanh toán.</p>}
  </Modal>
}
