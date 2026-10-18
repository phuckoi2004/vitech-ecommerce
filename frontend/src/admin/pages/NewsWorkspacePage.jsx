import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import useAdminQuery from '../hooks/useAdminQuery.js'
import { createNews, hideNews, publishNews, updateNews } from '../services/news.js'
import { NEWS_PAGE_TITLES, newsPagePath, newsSearch, newsStatusChoices } from '../lib/news.js'
import NewsEditor from '../components/NewsEditor.jsx'
import NewsDetail from '../components/NewsDetail.jsx'
import NewsErrorDialog from '../components/NewsErrorDialog.jsx'

function NewsWorkspace({ mode, article, onClose, onDone, onEdit }) {
  const auth = useInternalAuth(), canEdit = auth.permissions.includes('news:update')
  const [snapshot, setSnapshot] = useState(article), [busy, setBusy] = useState(false), [uploading, setUploading] = useState(false), [failure, setFailure] = useState(null), [validation, setValidation] = useState(''), [notice, setNotice] = useState('')
  const saved = useRef(article), writing = useRef(false), mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const permitted = auth.permissions.includes('news:view') && (mode === 'view' || auth.permissions.includes('news:' + (mode === 'new' ? 'create' : 'update')))
  async function save(body, status) {
    if (!permitted || writing.current || uploading || failure) return
    if (!body.Title || !body.Content || !/^[a-z0-9]+(-[a-z0-9]+)*$/.test(body.Slug)) { setValidation('Vui lòng nhập tiêu đề, nội dung và slug hợp lệ.'); return }
    const current = saved.current?.Status ?? 'Draft'
    if (!newsStatusChoices(current).includes(status) || (status !== current && !canEdit)) { setValidation('Bạn không thể chuyển sang trạng thái này.'); return }
    writing.current = true; setBusy(true); setValidation('')
    try {
      const payload = { ...body, Status: status }
      saved.current = await auth.withAccessToken((token) => saved.current ? updateNews(token, saved.current.NewsArticleId, payload) : createNews(token, payload))
      if (mounted.current) onDone(mode === 'new' ? 'Đã thêm tin tức.' : 'Đã cập nhật tin tức.')
    } catch (error) {
      if (mounted.current) setFailure({ title: mode === 'new' ? 'Không thể lưu tin tức' : 'Không thể cập nhật tin tức', message: error.message })
    } finally { writing.current = false; if (mounted.current) setBusy(false) }
  }
  async function changeStatus() {
    if (!permitted || !canEdit || !saved.current || writing.current || failure) return
    writing.current = true; setBusy(true)
    const publishing = saved.current.Status !== 'Published'
    try {
      saved.current = await auth.withAccessToken((token) => publishing ? publishNews(token, saved.current.NewsArticleId) : hideNews(token, saved.current.NewsArticleId))
      if (mounted.current) { setSnapshot(saved.current); setNotice(publishing ? 'Đã đăng tin tức.' : 'Đã ẩn tin tức.') }
    } catch (error) { if (mounted.current) setFailure({ message: error.message }) }
    finally { writing.current = false; if (mounted.current) setBusy(false) }
  }
  return <section aria-label={NEWS_PAGE_TITLES[mode]} className={'flex w-full flex-col gap-3 rounded-xl border border-admin-border bg-white p-[22px] shadow-[0px_8px_24px_0px_rgba(0,0,0,0.14)] ' + (mode === 'view' ? 'min-h-[720px] max-w-[620px]' : 'min-h-[790px] max-w-[650px]')}>
    <h2 className="m-0 text-[17px] leading-[21px] font-bold">{NEWS_PAGE_TITLES[mode]}</h2>
    {notice && <p role="status" className="m-0 text-[10px] text-green-700">{notice}</p>}
    {validation && <p role="alert" className="m-0 text-[10px] text-admin-red">{validation}</p>}
    {mode === 'view' ? <NewsDetail article={snapshot} busy={busy} canEdit={canEdit} onEdit={onEdit} onClose={onClose} onStatus={() => void changeStatus()} /> : <NewsEditor article={article} currentStatus={snapshot?.Status ?? 'Draft'} canChangeStatus={canEdit} busy={busy || uploading} onUploadBusy={setUploading} onCancel={onClose} onSave={(body, status) => void save(body, status)} />}
    {failure && <NewsErrorDialog failure={failure} onClose={() => setFailure(null)} />}
  </section>
}

export default function NewsWorkspacePage({ mode }) {
  const auth = useInternalAuth(), { articleId } = useParams(), navigate = useNavigate(), [params] = useSearchParams()
  const detail = useAdminQuery('/admin/news/' + encodeURIComponent(articleId ?? ''), {}, mode !== 'new' && auth.permissions.includes('news:view'))
  const listPath = '/admin/news' + newsSearch(params)
  const close = () => navigate(listPath)
  if (mode !== 'new' && detail.loading) return <LoadingState label="Đang tải tin tức…" />
  if (mode !== 'new' && detail.error) return <><ErrorState message={detail.error} onRetry={detail.refresh} /><button type="button" onClick={close} className="cursor-pointer text-xs text-admin-blue underline">Về danh sách tin tức</button></>
  if (mode !== 'new' && !detail.data) return null
  return <NewsWorkspace key={mode + '-' + articleId} mode={mode} article={mode === 'new' ? null : detail.data} onClose={close} onDone={(newsNotice) => navigate(listPath, { state: { newsNotice } })} onEdit={() => navigate(newsPagePath('edit', articleId, params))} />
}
