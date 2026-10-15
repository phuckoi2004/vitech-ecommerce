import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getSupportInbox, getSupportPage } from '../services/support.js'
import useSupportPoll from '../hooks/useSupportPoll.js'
import { supportName, supportPreview, supportTime } from '../lib/support.js'
import { SupportError, SupportStatus } from '../components/SupportUi.jsx'
import SupportConversation from '../components/SupportConversation.jsx'

export default function SupportPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'active' ? 'active' : 'waiting'
  const requestedPage = Number(params.get('page'))
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1
  const load = useCallback(async (token, signal) => {
    const inbox = await getSupportInbox(token, signal)
    if (page > 1) inbox[tab] = await getSupportPage(token, tab, page, signal)
    return inbox
  }, [tab, page])
  const state = useSupportPoll(load), [drafts, setDrafts] = useState({}), [reload, setReload] = useState(0)
  const rows = state.data?.[tab]?.Items ?? []
  const selected = params.get('conversation') || rows[0]?.ConversationId
  const explicitSelection = params.get('conversation'), firstId = rows[0]?.ConversationId
  useEffect(() => {
    if (!explicitSelection && firstId) setParams((previous) => {
      const next = new URLSearchParams(previous)
      if (!next.has('conversation')) next.set('conversation', firstId)
      return next
    }, { replace: true })
  }, [explicitSelection, firstId, setParams])
  const lastPage = state.data ? Math.max(1, Math.ceil(state.data[tab].Total / 100)) : null
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
    <div className="flex h-10 shrink-0 items-center"><div><h2 className="m-0 text-xl leading-[normal] font-bold">Trung tâm hỗ trợ khách hàng</h2><p className="mt-0.5 mb-0 text-[10px] leading-[normal] text-admin-muted">Tiếp nhận và trao đổi trực tiếp với khách hàng qua hệ thống chat</p></div></div>
    <div className="flex items-center justify-between gap-3">
      <div role="tablist" aria-label="Trạng thái hỗ trợ" className="flex gap-1.5">{[['waiting', 'Đang chờ'], ['active', 'Đang hỗ trợ']].map(([key, label]) => <button key={key} id={'support-tab-' + key} type="button" role="tab" aria-label={label + (state.data ? ' ' + state.data[key].Total : '')} aria-selected={tab === key} aria-controls="support-workspace" onClick={() => navigate({ tab: key === 'active' ? key : '', conversation: '', page: '' })} className={'flex cursor-pointer items-center gap-[7px] rounded-lg px-3.5 py-[9px] text-[10px] leading-[normal] ' + (tab === key ? 'bg-admin-blue font-semibold text-white' : 'bg-admin-page font-medium text-admin-muted')}>
        {label}{state.data && <span className={'rounded-full px-1.5 py-0.5 text-[8px] leading-[normal] font-bold ' + (tab === key ? 'bg-white text-admin-blue' : 'bg-admin-border text-admin-muted')}>{state.data[key].Total}</span>}
      </button>)}</div>
      <button type="button" onClick={refresh} disabled={state.loading} className="cursor-pointer text-[10px] text-admin-muted hover:text-admin-blue disabled:opacity-50">Làm mới</button>
    </div>
    {state.error && <SupportError message={state.error} onRetry={state.refresh} />}
    <div id="support-workspace" role="tabpanel" aria-labelledby={'support-tab-' + tab} className="flex h-[735px] min-w-0 overflow-hidden rounded-xl border border-admin-border bg-white">
      <aside aria-label="Danh sách cuộc trò chuyện" className="flex h-full w-[340px] shrink-0 flex-col gap-2.5 border-r border-admin-border p-3.5">
        <h3 className="m-0 flex h-[22px] shrink-0 items-center text-xs leading-[normal] font-semibold">{tab === 'waiting' ? 'Yêu cầu đang chờ' : 'Cuộc trò chuyện đang hỗ trợ'}</h3>
        <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto">
          {!state.data && !state.error && <p role="status" className="text-[11px] text-admin-muted">Đang tải danh sách…</p>}
          {state.data && !rows.length && <p className="text-[11px] text-admin-muted">{tab === 'waiting' ? 'Không có cuộc trò chuyện đang chờ.' : 'Bạn chưa có cuộc trò chuyện đang hỗ trợ.'}</p>}
          {rows.map((conversation) => <button type="button" key={conversation.ConversationId} aria-label={'Mở cuộc trò chuyện với ' + supportName(conversation)} aria-current={selected === conversation.ConversationId ? 'true' : undefined} onClick={() => navigate({ conversation: conversation.ConversationId })} className={'flex min-h-[105px] shrink-0 cursor-pointer flex-col items-start gap-1.5 rounded-[10px] border p-3 text-left ' + (selected === conversation.ConversationId ? 'border-admin-blue bg-admin-soft' : 'border-transparent bg-white hover:bg-admin-page')}>
            <span className="flex h-5 w-full items-center justify-between gap-2"><span className="truncate text-xs leading-[normal] font-semibold">{supportName(conversation)}</span><time className="shrink-0 text-[10px] leading-[normal] text-admin-muted" dateTime={conversation.LastMessage?.SentAt || conversation.CreatedAt}>{supportTime(conversation.LastMessage?.SentAt || conversation.CreatedAt)}</time></span>
            <span className="block w-full truncate text-[11px] leading-[normal] text-admin-muted">{supportPreview(conversation)}</span><SupportStatus status={tab} />
          </button>)}
        </div>
        {state.data && state.data[tab].Total > 100 && <nav aria-label="Trang hội thoại" className="flex items-center justify-between gap-2 text-[10px]"><button disabled={page === 1 || state.loading} onClick={() => navigate({ page: String(page - 1), conversation: '' })} className="cursor-pointer disabled:opacity-40">Trước</button><span>Trang {page} / {Math.ceil(state.data[tab].Total / 100)}</span><button disabled={page * 100 >= state.data[tab].Total || state.loading} onClick={() => navigate({ page: String(page + 1), conversation: '' })} className="cursor-pointer disabled:opacity-40">Sau</button></nav>}
      </aside>
      {selected ? <SupportConversation key={selected} id={selected} reload={reload} draft={drafts[selected] ?? ''} onDraft={(value) => setDrafts((previous) => ({ ...previous, [selected]: value }))} onClaimed={(id) => navigate({ tab: 'active', conversation: id, page: '' })} onChanged={state.refresh} /> : <div className="grid min-w-0 flex-1 place-items-center p-[18px] text-xs text-admin-muted">Chọn một cuộc trò chuyện để xem nội dung.</div>}
    </div>
  </section>
}
