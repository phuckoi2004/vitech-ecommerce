import { useEffect, useRef, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import { deleteBanner } from '../services/banners.js'
import useAdminQuery from '../hooks/useAdminQuery.js'
import Modal from './Modal.jsx'
import { BannerButton } from './BannerUi.jsx'

// Only deletion is a dialog. Reading and editing are routed pages.
export default function BannerDialog({ bannerId, onClose, onDone }) {
  const auth = useInternalAuth(), permitted = auth.permissions.includes('banners:view') && auth.permissions.includes('banners:delete')
  const detail = useAdminQuery('/admin/banners/' + encodeURIComponent(bannerId), {}, permitted)
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const writing = useRef(false), mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  async function remove() {
    if (!permitted || writing.current || !detail.data || detail.loading || detail.error) return
    writing.current = true; setBusy(true); setError('')
    try { await auth.withAccessToken((token) => deleteBanner(token, bannerId)); if (mounted.current) onDone('Đã xóa banner.') }
    catch (failure) { if (mounted.current) setError(failure.message) }
    finally { writing.current = false; if (mounted.current) setBusy(false) }
  }
  if (!permitted) return null
  return <Modal variant="news-delete" open title="Xóa banner?" className="min-h-[270px] w-[460px]" busy={busy} onClose={onClose}>
    {detail.loading ? <LoadingState label="Đang tải banner…" /> : detail.error ? <ErrorState message={detail.error} onRetry={detail.refresh} /> : detail.data ? <>
      <p className="m-0 text-[10px] leading-3 break-words text-admin-muted">Bạn có chắc chắn muốn xóa banner “{detail.data.Title}” không?</p>
      {error && <p role="alert" className="mt-2 mb-0 text-[10px] text-admin-red">{error}</p>}
      <div className="mt-3 flex justify-end"><BannerButton secondary className="text-admin-text!" disabled={busy} onClick={onClose}>Hủy</BannerButton><BannerButton secondary className="border-admin-red! text-admin-red! hover:bg-red-50!" loading={busy} onClick={() => void remove()}>Xác nhận xóa</BannerButton></div>
    </> : <p>Không tìm thấy banner.</p>}
  </Modal>
}
