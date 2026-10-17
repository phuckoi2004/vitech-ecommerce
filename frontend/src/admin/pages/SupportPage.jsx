import { useCallback, useEffect, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { getSupportInbox, getSupportPage } from '../services/support.js'
import useSupportPoll from '../hooks/useSupportPoll.js'
import { supportName, supportPreview, supportTime } from '../lib/support.js'
import { SupportError, SupportStatus } from '../components/SupportUi.jsx'
import SupportConversation from '../components/SupportConversation.jsx'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import './SupportPage.css'

export default function SupportPage() {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const { user } = useInternalAuth()
  const tabs = [['waiting', 'Đang chờ'], ['active', 'Đang hỗ trợ'], ['closed', 'Đã kết thúc'], ...(user.Role === 'Admin' ? [['all', 'Tất cả hội thoại']] : [])]
  const tab = tabs.some(([key]) => key === params.get('tab')) ? params.get('tab') : 'waiting'
  const [listLocation, setListLocation] = useState(null)
  const listOpen = !params.has('conversation') || listLocation === location.key
  function setListOpen(open) { setListLocation(open ? location.key : null) }
  const [compact, setCompact] = useState(() => window.matchMedia?.('(max-width: 1100px)').matches ?? false)
  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 1100px)')
    if (!media) return
    const update = () => setCompact(media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  const requestedPage = Number(params.get('page'))
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1
  const load = useCallback(async (token, signal) => {
    const inbox = await getSupportInbox(token, signal)
    if (page > 1 || ['closed', 'all'].includes(tab)) inbox[tab] = await getSupportPage(token, tab, page, signal, user.Role)
    return inbox
  }, [tab, page, user.Role])
  const state = useSupportPoll(load), [drafts, setDrafts] = useState({}), [reload, setReload] = useState(0)
  const rows = state.data?.[tab]?.Items ?? []
  const selected = params.get('conversation') || rows[0]?.ConversationId
  const lastPage = state.data ? Math.max(1, Math.ceil((state.data[tab]?.Total ?? 0) / 100)) : null
  useEffect(() => {
    if (lastPage !== null && page > lastPage) setParams((previous) => {
      const next = new URLSearchParams(previous)
      if (lastPage === 1) next.delete('page')
      else next.set('page', String(lastPage))
      return next
    }, { replace: true })
  }, [lastPage, page, setParams])
  function refresh() { state.refresh(); setReload((value) => value + 1) }
  function navigate(values) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      for (const [key, value] of Object.entries(values)) {
        if (value) next.set(key, value)
        else next.delete(key)
      }
      return next
    })
  }
  return <section aria-label="Trung tâm hỗ trợ" className="-my-1 flex min-w-0 flex-col gap-3.5 font-admin text-admin-text">
    <div><h2 className="m-0 text-xl leading-[normal] font-bold">Trung tâm hỗ trợ khách hàng</h2><p className="mt-1 mb-0 text-sm text-admin-muted">Tiếp nhận và trao đổi trực tiếp với khách hàng qua hệ thống chat</p></div>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div role="tablist" aria-label="Trạng thái hỗ trợ" className="flex flex-wrap gap-1.5">{tabs.map(([key, label]) => <button key={key} id={'support-tab-' + key} type="button" role="tab" aria-label={label + (state.data?.[key] ? ' ' + state.data[key].Total : '')} aria-selected={tab === key} aria-controls="support-workspace" onClick={() => { setListOpen(true); navigate({ tab: key === 'waiting' ? '' : key, conversation: '', page: '' }) }} className={'flex cursor-pointer items-center gap-[7px] rounded-lg px-3.5 py-[9px] text-sm ' + (tab === key ? 'bg-admin-blue font-semibold text-white' : 'bg-admin-page font-medium text-admin-muted')}>
        {label}{state.data?.[key] && <span className={'rounded-full px-1.5 py-0.5 text-xs font-bold ' + (tab === key ? 'bg-white text-admin-blue' : 'bg-admin-border text-admin-muted')}>{state.data[key].Total}</span>}
      </button>)}</div>
      <button type="button" onClick={refresh} disabled={state.loading} className="cursor-pointer text-[10px] text-admin-muted hover:text-admin-blue disabled:opacity-50">Làm mới</button>
    </div>
    {state.error && <SupportError message={state.error} onRetry={state.refresh} />}
    <div id="support-workspace" role="tabpanel" aria-labelledby={'support-tab-' + tab} data-mobile-view={listOpen ? 'list' : 'thread'} className="support-workspace flex min-w-0 overflow-hidden rounded-xl border border-admin-border bg-white">
      <aside aria-label="Danh sách cuộc trò chuyện" className="support-sidebar flex h-full w-[300px] shrink-0 flex-col gap-2.5 border-r border-admin-border p-3.5">
        <h3 className="m-0 shrink-0 text-sm font-semibold">{tab === 'waiting' ? 'Yêu cầu đang chờ' : tab === 'closed' ? 'Lịch sử hỗ trợ' : tab === 'all' ? 'Tất cả hội thoại' : 'Cuộc trò chuyện đang hỗ trợ'}</h3>
        <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto">
          {!state.data && !state.error && <p role="status" className="text-[11px] text-admin-muted">Đang tải danh sách…</p>}
          {state.data && !rows.length && <p className="text-[11px] text-admin-muted">{tab === 'waiting' ? 'Không có cuộc trò chuyện đang chờ.' : tab === 'active' ? 'Bạn chưa có cuộc trò chuyện đang hỗ trợ.' : 'Chưa có cuộc trò chuyện.'}</p>}
          {rows.map((conversation) => <button type="button" key={conversation.ConversationId} aria-label={'Mở cuộc trò chuyện với ' + supportName(conversation)} aria-current={selected === conversation.ConversationId ? 'true' : undefined} onClick={() => { setListOpen(false); navigate({ conversation: conversation.ConversationId }) }} className={'flex min-h-[105px] min-w-0 shrink-0 cursor-pointer flex-col items-start gap-1.5 rounded-[10px] border p-3 text-left ' + (selected === conversation.ConversationId ? 'border-admin-blue bg-admin-soft' : 'border-transparent bg-white hover:bg-admin-page')}>
            <span className="flex h-5 w-full items-center justify-between gap-2"><span className="truncate text-xs leading-[normal] font-semibold">{supportName(conversation)}</span><time className="shrink-0 text-[10px] leading-[normal] text-admin-muted" dateTime={conversation.LastMessage?.SentAt || conversation.CreatedAt}>{supportTime(conversation.LastMessage?.SentAt || conversation.CreatedAt)}</time></span>
            <span className="block w-full truncate text-[11px] leading-[normal] text-admin-muted">{supportPreview(conversation)}</span><span className="flex w-full items-center justify-between gap-2"><SupportStatus status={conversation.Status === 'Closed' ? 'closed' : conversation.Mode === 'AI' ? 'ai' : conversation.AssignedStaffId ? 'active' : 'waiting'} />{conversation.UnreadCount > 0 && <span className="rounded-full bg-admin-blue px-2 py-0.5 text-xs font-semibold text-white" aria-label={conversation.UnreadCount + ' tin nhắn chưa đọc'}>{conversation.UnreadCount} mới</span>}</span>
          </button>)}
        </div>
        {state.data && state.data[tab].Total > 100 && <nav aria-label="Trang hội thoại" className="flex items-center justify-between gap-2 text-[10px]"><button disabled={page === 1 || state.loading} onClick={() => navigate({ page: String(page - 1), conversation: '' })} className="cursor-pointer disabled:opacity-40">Trước</button><span>Trang {page} / {Math.ceil(state.data[tab].Total / 100)}</span><button disabled={page * 100 >= state.data[tab].Total || state.loading} onClick={() => navigate({ page: String(page + 1), conversation: '' })} className="cursor-pointer disabled:opacity-40">Sau</button></nav>}
      </aside>
      {selected ? <SupportConversation key={selected} id={selected} reload={reload} visible={!compact || !listOpen} onBack={() => setListOpen(true)} onInteract={() => navigate({ conversation: selected })} draft={drafts[selected] ?? ''} onDraft={(value) => setDrafts((previous) => ({ ...previous, [selected]: value }))} onClaimed={(id) => { setListOpen(false); navigate({ tab: 'active', conversation: id, page: '' }) }} onChanged={state.refresh} /> : <div className="support-thread grid min-w-0 flex-1 place-items-center p-[18px] text-xs text-admin-muted">Chọn một cuộc trò chuyện để xem nội dung.</div>}
    </div>
  </section>
}
