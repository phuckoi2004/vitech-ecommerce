import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import useAdminQuery from '../hooks/useAdminQuery.js'
import { activateBanner, createBanner, deactivateBanner, updateBanner } from '../services/banners.js'
import { BANNER_PAGE_TITLES, BANNER_STATUSES, bannerPagePath, bannerSearch, bannerValidation } from '../lib/banners.js'
import BannerEditor from '../components/BannerEditor.jsx'
import BannerDetail from '../components/BannerDetail.jsx'
import NewsErrorDialog from '../components/NewsErrorDialog.jsx'

const contentFields = (banner) => ({ Title: banner.Title, ImageUrl: banner.ImageUrl, LinkUrl: banner.LinkUrl ?? null, DisplayOrder: banner.DisplayOrder, StartDate: banner.StartDate ?? null, EndDate: banner.EndDate ?? null })

function BannerWorkspace({ mode, banner, onClose, onDone, onEdit }) {
  const auth = useInternalAuth(), canEdit = auth.permissions.includes('banners:update')
  const [snapshot, setSnapshot] = useState(banner), [busy, setBusy] = useState(false), [uploading, setUploading] = useState(false), [failure, setFailure] = useState(null), [validation, setValidation] = useState(''), [notice, setNotice] = useState('')
  const saved = useRef(banner), lastBody = useRef(banner ? JSON.stringify(contentFields(banner)) : ''), writing = useRef(false), mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const permitted = auth.permissions.includes('banners:view') && (mode === 'view' || auth.permissions.includes('banners:' + (mode === 'new' ? 'create' : 'update')))
  async function save(body, active) {
    if (!permitted || writing.current || uploading || failure) return
    const invalid = bannerValidation(body)
    if (invalid) { setValidation(invalid); return }
    if (active !== (saved.current?.IsActive ?? true) && !canEdit) { setValidation('Bạn không có quyền thay đổi trạng thái banner.'); return }
    writing.current = true; setBusy(true); setValidation('')
    let committed = false
    try {
      if (!saved.current) {
        saved.current = await auth.withAccessToken((token) => createBanner(token, body))
        lastBody.current = JSON.stringify(body); committed = true
      } else if (lastBody.current !== JSON.stringify(body)) {
        saved.current = await auth.withAccessToken((token) => updateBanner(token, saved.current.BannerId, body))
        lastBody.current = JSON.stringify(body); committed = true
      }
      if (mounted.current) setSnapshot(saved.current)
      if (saved.current.IsActive !== active) {
        saved.current = await auth.withAccessToken((token) => active ? activateBanner(token, saved.current.BannerId) : deactivateBanner(token, saved.current.BannerId))
      }
      if (mounted.current) onDone(mode === 'new' ? 'Đã thêm banner.' : 'Đã cập nhật banner.')
    } catch (error) {
      if (mounted.current) setFailure({ title: mode === 'new' ? 'Không thể lưu banner' : 'Không thể cập nhật banner', message: committed ? 'Trạng thái đã lưu: ' + BANNER_STATUSES[saved.current.IsActive ? 'active' : 'inactive'] + '. ' + error.message : error.message, partial: committed })
    } finally { writing.current = false; if (mounted.current) setBusy(false) }
  }
  async function changeStatus() {
    if (!permitted || !canEdit || !saved.current || writing.current || failure) return
    writing.current = true; setBusy(true)
    const active = !saved.current.IsActive
    try {
      saved.current = await auth.withAccessToken((token) => active ? activateBanner(token, saved.current.BannerId) : deactivateBanner(token, saved.current.BannerId))
      if (mounted.current) { setSnapshot(saved.current); setNotice(active ? 'Đã bật banner.' : 'Đã ngừng hoạt động banner.') }
    } catch (error) { if (mounted.current) setFailure({ title: 'Không thể cập nhật banner', message: error.message }) }
    finally { writing.current = false; if (mounted.current) setBusy(false) }
  }
  return <section aria-label={BANNER_PAGE_TITLES[mode]} className={'flex w-full flex-col gap-3 rounded-xl border border-admin-border bg-white p-[22px] shadow-[0px_8px_24px_0px_rgba(0,0,0,0.14)] ' + (mode === 'view' ? 'min-h-[690px] max-w-[610px]' : 'min-h-[740px] max-w-[630px]')}>
    <h2 className="m-0 text-[17px] leading-[21px] font-bold">{BANNER_PAGE_TITLES[mode]}</h2>
    {notice && <p role="status" className="m-0 text-[10px] text-green-700">{notice}</p>}
    {validation && <p role="alert" className="m-0 text-[10px] text-admin-red">{validation}</p>}
    {mode === 'view' ? <BannerDetail banner={snapshot} busy={busy} canEdit={canEdit} onEdit={onEdit} onClose={onClose} onStatus={() => void changeStatus()} /> : <BannerEditor banner={banner} canChangeStatus={canEdit} busy={busy || uploading} onUploadBusy={setUploading} onCancel={onClose} onSave={(body, active) => void save(body, active)} />}
    {failure && <NewsErrorDialog failure={failure} entity="banner" onClose={() => setFailure(null)} />}
  </section>
}

export default function BannerWorkspacePage({ mode }) {
  const auth = useInternalAuth(), { bannerId } = useParams(), navigate = useNavigate(), [params] = useSearchParams()
  const detail = useAdminQuery('/admin/banners/' + encodeURIComponent(bannerId ?? ''), {}, mode !== 'new' && auth.permissions.includes('banners:view'))
  const listPath = '/admin/banners' + bannerSearch(params)
  const close = () => navigate(listPath)
  if (mode !== 'new' && detail.loading) return <LoadingState label="Đang tải banner…" />
  if (mode !== 'new' && detail.error) return <><ErrorState message={detail.error} onRetry={detail.refresh} /><button type="button" onClick={close} className="cursor-pointer text-xs text-admin-blue underline">Về danh sách banner</button></>
  if (mode !== 'new' && !detail.data) return null
  return <BannerWorkspace key={mode + '-' + bannerId} mode={mode} banner={mode === 'new' ? null : detail.data} onClose={close} onDone={(bannerNotice) => navigate(listPath, { state: { bannerNotice } })} onEdit={() => navigate(bannerPagePath('edit', bannerId, params))} />
}
