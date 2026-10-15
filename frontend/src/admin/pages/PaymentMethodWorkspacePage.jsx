import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import useAdminQuery from '../hooks/useAdminQuery.js'
import { createPaymentMethod, updatePaymentMethod } from '../services/payment-methods.js'
import { PAYMENT_PAGE_TITLES, paymentListSearch, paymentValidation } from '../lib/payment-methods.js'
import PaymentMethodEditor from '../components/PaymentMethodEditor.jsx'
import PaymentResultDialog from '../components/PaymentResultDialog.jsx'

function PaymentWorkspace({ mode, method, onClose }) {
  const auth = useInternalAuth(), [busy, setBusy] = useState(false), [validation, setValidation] = useState(''), [failure, setFailure] = useState(null), [success, setSuccess] = useState(false)
  const writing = useRef(false), lastAttempt = useRef(null), mounted = useRef(true), succeeded = useRef(false)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const permitted = auth.user.Role === 'Admin' && auth.permissions.includes('payment_methods:view') && auth.permissions.includes('payment_methods:' + (mode === 'new' ? 'create' : 'update'))
  async function save(body) {
    if (!permitted || writing.current || succeeded.current) return
    const invalid = paymentValidation(body, mode === 'new')
    if (invalid) { setValidation(invalid); return }
    writing.current = true; lastAttempt.current = body; setBusy(true); setValidation('')
    try {
      await auth.withAccessToken((token) => mode === 'new' ? createPaymentMethod(token, body) : updatePaymentMethod(token, method.PaymentMethodId, body))
      succeeded.current = true
      if (mounted.current) { setFailure(null); setSuccess(true) }
    } catch (error) { if (mounted.current) setFailure(error.message) }
    finally { writing.current = false; if (mounted.current) setBusy(false) }
  }
  return <section aria-label={PAYMENT_PAGE_TITLES[mode]} className="flex min-h-[590px] w-full max-w-[570px] flex-col gap-3 rounded-xl border border-admin-border bg-white p-[22px] shadow-[0px_8px_24px_0px_rgba(0,0,0,0.14)]">
    <h2 className="m-0 text-[17px] leading-[21px] font-bold">{PAYMENT_PAGE_TITLES[mode]}</h2>
    <PaymentMethodEditor method={method} busy={busy || success || failure !== null} validation={validation} onCancel={onClose} onSave={(body) => void save(body)} />
    {failure !== null && <PaymentResultDialog message={failure} busy={busy} onClose={() => setFailure(null)} onRetry={() => void save(lastAttempt.current)} />}
    {success && <PaymentResultDialog success onClose={onClose} />}
  </section>
}

export default function PaymentMethodWorkspacePage({ mode }) {
  const auth = useInternalAuth(), { methodId } = useParams(), navigate = useNavigate(), [params] = useSearchParams()
  const permitted = auth.user.Role === 'Admin' && auth.permissions.includes('payment_methods:view') && auth.permissions.includes('payment_methods:' + (mode === 'new' ? 'create' : 'update'))
  const detail = useAdminQuery('/payment-methods/' + encodeURIComponent(methodId ?? ''), {}, permitted && mode !== 'new')
  const close = () => navigate('/admin/payments' + paymentListSearch(params))
  if (!permitted) return <ErrorState message="Bạn không có quyền quản lý phương thức thanh toán." />
  if (mode !== 'new' && detail.loading) return <LoadingState label="Đang tải phương thức thanh toán…" />
  if (mode !== 'new' && detail.error) return <><ErrorState message={detail.error} onRetry={detail.refresh} /><button type="button" className="cursor-pointer text-xs text-admin-blue underline" onClick={close}>Về danh sách phương thức thanh toán</button></>
  if (mode !== 'new' && !detail.data) return null
  return <PaymentWorkspace key={mode + '-' + methodId} mode={mode} method={mode === 'new' ? null : detail.data} onClose={close} />
}
