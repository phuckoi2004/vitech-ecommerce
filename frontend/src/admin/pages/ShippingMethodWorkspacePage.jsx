import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import useAdminQuery from '../hooks/useAdminQuery.js'
import { createShippingMethod, updateShippingMethod } from '../services/shipping-methods.js'
import { shippingBody, shippingListSearch, SHIPPING_PAGE_TITLES } from '../lib/shipping-methods.js'
import ShippingMethodEditor from '../components/ShippingMethodEditor.jsx'
import Modal from '../components/Modal.jsx'
import ShippingMethodsPage from './ShippingMethodsPage.jsx'

export default function ShippingMethodWorkspacePage({ mode }) {
  const auth = useInternalAuth(), { methodId } = useParams(), [params] = useSearchParams(), navigate = useNavigate()
  const [busy, setBusy] = useState(false), [failure, setFailure] = useState('')
  const writing = useRef(false), mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const permitted = auth.user.Role === 'Admin' && auth.permissions.includes('shipping_methods:' + (mode === 'new' ? 'create' : 'update'))
  const detail = useAdminQuery('/shipping-methods/' + encodeURIComponent(methodId ?? ''), {}, mode !== 'new' && permitted)
  const close = (notice) => navigate('/admin/shipping-methods' + shippingListSearch(params), { state: notice ? { shippingNotice: notice } : null })
  async function save(form) {
    if (writing.current || !permitted) return
    let body
    try { body = shippingBody(form) }
    catch (error) { setFailure(error.message); return }
    writing.current = true; setBusy(true); setFailure('')
    try {
      await auth.withAccessToken((token) => mode === 'new' ? createShippingMethod(token, body) : updateShippingMethod(token, methodId, body))
      if (mounted.current) close(mode === 'new' ? 'Đã thêm phương thức vận chuyển.' : 'Đã cập nhật phương thức vận chuyển.')
    } catch (error) { if (mounted.current) setFailure(error.message) }
    finally { writing.current = false; if (mounted.current) setBusy(false) }
  }
  if (!permitted) return <ErrorState message="Bạn không có quyền quản lý phương thức vận chuyển." />
  return <>
    <ShippingMethodsPage />
    <Modal variant="shipping-editor" open title={SHIPPING_PAGE_TITLES[mode]} description={mode === 'new' ? 'Nhập thông tin phương thức mới' : 'Cập nhật thông tin phương thức đang chọn'} busy={busy} onClose={() => close()} className="w-[560px]! shadow-[0px_10px_30px_0px_rgba(15,45,107,0.12)]!">
      {mode !== 'new' && detail.loading ? <div className="min-h-[556px] p-6"><LoadingState label="Đang tải phương thức vận chuyển…" /></div> : mode !== 'new' && detail.error ? <div className="min-h-[556px] p-6"><ErrorState message={detail.error} onRetry={detail.refresh} /></div> : (mode === 'new' || detail.data) && <ShippingMethodEditor key={mode + '-' + methodId} method={mode === 'new' ? null : detail.data} busy={busy} error={failure} onCancel={() => close()} onSave={(form) => void save(form)} />}
    </Modal>
  </>
}
