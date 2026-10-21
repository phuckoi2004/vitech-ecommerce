import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import useSupportThread from '../hooks/useSupportThread.js'
import { claimSupportConversation, closeSupportConversation, markSupportRead, sendSupportMessage } from '../services/support.js'
import { supportAgent, supportName, supportTime } from '../lib/support.js'
import { NewsButton } from './NewsUi.jsx'
import { SupportError, SupportStatus } from './SupportUi.jsx'
import Modal from './Modal.jsx'
import SupportSendErrorDialog from './SupportSendErrorDialog.jsx'

function Message({ message, operator, active }) {
  const staff = message.SenderType === 'Staff'
  // The API intentionally uses SenderType=Staff for both internal roles.
  // Only label the signed-in Admin's own messages as Admin.
  const sender = staff ? message.SenderUserId === operator.UserId && operator.Role === 'Admin' ? 'Admin' : 'Nhân viên' : message.SenderType === 'AI' ? 'Trợ lý AI' : 'Khách hàng'
  const imageUrl = message.MessageType === 'Image' && message.Metadata?.ImageUrl
  const safeImage = imageUrl && /^https:\/\//i.test(imageUrl)
  return <div className={'flex w-full shrink-0 items-start ' + (active ? 'min-h-[76px] ' : '') + (staff ? 'justify-end' : 'justify-start')}><article aria-label={'Tin nhắn ' + message.MessageId} className={'flex w-[470px] max-w-full shrink-0 flex-col gap-1 rounded-[10px] px-[11px] py-[9px] ' + (active ? 'min-h-[66px] ' : '') + (staff ? 'bg-admin-blue text-white' : 'border border-admin-border bg-admin-page')}>
    {safeImage && <a href={imageUrl} target="_blank" rel="noopener noreferrer"><img src={imageUrl} alt={message.Content || 'Ảnh khách hàng gửi'} className="max-h-56 max-w-full rounded-md object-contain" loading="lazy" /></a>}
    {message.MessageType === 'Product' && <p className="m-0 text-xs font-semibold">{message.Metadata?.ProductName || 'Sản phẩm'}</p>}
    {message.Content && <p className={'m-0 text-xs leading-[normal] whitespace-pre-wrap wrap-anywhere ' + (staff ? 'font-semibold' : '')}>{message.Content}</p>}
    <p className={'m-0 text-[10px] leading-[normal] ' + (staff ? 'text-white' : 'text-admin-muted')}>{sender} • <time dateTime={message.SentAt}>{supportTime(message.SentAt)}</time>{message.SenderType === 'Customer' && <span> • {message.IsRead ? 'Đã đọc' : 'Chưa đọc'}</span>}</p>
  </article></div>
}

export default function SupportConversation({ id, draft, onDraft, onClaimed, onChanged, onInteract, reload, visible = true, onBack }) {
  const { user, permissions, withAccessToken } = useInternalAuth()
  const state = useSupportThread(id, reload, visible)
  const [busy, setBusy] = useState(''), [error, setError] = useState(''), [confirmClose, setConfirmClose] = useState(false)
  const [sendFailure, setSendFailure] = useState(null)
  const [readIds, setReadIds] = useState([]), [readError, setReadError] = useState(''), [readAttempt, setReadAttempt] = useState(0)
  const lock = useRef(false), mounted = useRef(false), scroll = useRef(null), nearBottom = useRef(true)
  const historyAnchor = useRef(null)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const conversation = state.data
  const messages = (conversation?.Messages ?? []).map(message => readIds.includes(message.MessageId) ? { ...message, IsRead: true } : message)
  const lastId = messages.at(-1)?.MessageId
  useEffect(() => {
    if (!historyAnchor.current && nearBottom.current && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight
  }, [lastId])
  useLayoutEffect(() => {
    if (historyAnchor.current && scroll.current) {
      scroll.current.scrollTop = historyAnchor.current.top + scroll.current.scrollHeight - historyAnchor.current.height
      historyAnchor.current = null
    }
  }, [messages.length])
  const open = conversation?.Status === 'Open'
  const mine = !!conversation?.AssignedStaffId && conversation.AssignedStaffId === user.UserId
  const waiting = open && conversation.Mode === 'Staff' && !conversation.AssignedStaffId
  const canWrite = permissions.includes('chat:create')
  const disabled = !!busy || state.loading || !!state.error
  function loadOlder() {
    if (scroll.current) historyAnchor.current = { height: scroll.current.scrollHeight, top: scroll.current.scrollTop }
    nearBottom.current = false
    void state.loadOlder().then(count => { if (!count) historyAnchor.current = null })
  }
  const unreadKey = messages.filter(message => message.SenderType === 'Customer' && !message.IsRead).slice(0, 100).map(message => message.MessageId).join(',')
  useEffect(() => {
    if (!visible || !mine || !unreadKey || document.hidden) return
    const controller = new AbortController(), ids = unreadKey.split(',')
    withAccessToken(token => markSupportRead(token, id, ids)).then(() => {
      if (controller.signal.aborted) return
      setReadIds(previous => [...new Set([...previous, ...ids])]); setReadError(''); onChanged()
    }).catch(failure => { if (!controller.signal.aborted) setReadError(failure.message) })
    return () => controller.abort()
  }, [id, visible, mine, unreadKey, readAttempt, withAccessToken, onChanged])

  async function act(action, retryContent) {
    const retry = action === 'send' && typeof retryContent === 'string'
    if (lock.current || busy || state.loading || (state.error && !retry) || !canWrite || (action === 'claim' ? !waiting : !mine || !open)) return
    if (sendFailure && !retry) return
    const content = (retry ? retryContent : draft).trim()
    if (action === 'send' && (!content || content.length > 5000)) return
    onInteract?.()
    lock.current = true; setBusy(action); setError('')
    try {
      await withAccessToken((token) => action === 'claim' ? claimSupportConversation(token, id) : action === 'send' ? sendSupportMessage(token, id, content) : closeSupportConversation(token, id))
      if (!mounted.current) return
      if (action === 'claim') onClaimed(id)
      if (action === 'send') { onDraft(''); setSendFailure(null); nearBottom.current = true }
      if (action === 'close') setConfirmClose(false)
      state.refresh(); onChanged()
    } catch (failure) {
      if (!mounted.current) return
      if (action === 'send') setSendFailure({ content, message: failure.message, status: failure.status })
      else setError(failure.message || 'Thao tác chưa thành công. Vui lòng tải lại để kiểm tra.')
      // A competitor may have claimed or the customer may have closed the chat.
      // Re-read ownership; never retry a message POST automatically.
      setConfirmClose(false); state.refresh(); onChanged()
    } finally {
      lock.current = false
      if (mounted.current) setBusy('')
    }
  }

  if (!conversation) return <div className="support-thread flex min-w-0 flex-1 flex-col gap-3 p-[18px]"><button className="support-back" onClick={onBack}>← Danh sách hội thoại</button>{state.error ? <SupportError message={state.error} onRetry={state.refresh} /> : <p role="status" className="text-xs text-admin-muted">Đang tải cuộc trò chuyện…</p>}</div>
  const status = !open ? 'closed' : conversation.Mode === 'AI' ? 'ai' : waiting ? 'waiting' : 'active'
  return <section aria-label="Nội dung cuộc trò chuyện" className="support-thread flex h-full min-w-0 flex-1 flex-col">
    <header className="support-thread-header flex shrink-0 items-center justify-between gap-3 border-b border-admin-border px-[18px] py-3.5">
      <button type="button" className="support-back" onClick={onBack} aria-label="Quay lại danh sách hội thoại">←</button>
      <div className="min-w-0"><h3 className="m-0 truncate text-xs leading-[normal] font-semibold">{supportName(conversation)}</h3><p className={'mt-[3px] mb-0 truncate leading-[normal] text-admin-muted ' + (status === 'active' ? 'text-[9px]' : 'text-[10px]')}>Khách hàng{conversation.CustomerEmail ? ' • ' + conversation.CustomerEmail : ''}{supportAgent(conversation, user) ? ' • Người hỗ trợ: ' + supportAgent(conversation, user) : ''}</p></div>
      <div className="flex shrink-0 items-center gap-3"><SupportStatus status={status} />{mine && open && canWrite && <button type="button" disabled={disabled} onClick={() => setConfirmClose(true)} className="cursor-pointer text-[10px] text-admin-muted hover:text-admin-red disabled:opacity-50">Kết thúc hỗ trợ</button>}</div>
    </header>
    <div ref={scroll} onScroll={() => { const element = scroll.current; nearBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 70 }} className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-[18px]" role="log" aria-label="Tin nhắn" aria-live="polite" aria-relevant="additions">
      {state.error && <SupportError message={state.error} onRetry={state.refresh} />}
      {readError && <SupportError message={'Chưa đánh dấu được tin nhắn đã đọc: ' + readError} onRetry={() => setReadAttempt(value => value + 1)} />}
      {state.olderError && <SupportError message={state.olderError} onRetry={loadOlder} />}
      {conversation.HasOlder && <button type="button" className="shrink-0 self-center rounded-lg px-3 py-2 text-sm text-admin-blue hover:bg-admin-soft disabled:opacity-50" disabled={state.olderLoading} onClick={loadOlder}>{state.olderLoading ? 'Đang tải…' : 'Xem tin nhắn cũ hơn'}</button>}
      {error && <div role="alert" className="shrink-0 rounded-lg border border-red-200 bg-red-50 p-3 text-[11px] text-admin-red">{error}<button type="button" aria-label="Đóng thông báo" onClick={() => setError('')} className="float-right ml-2 cursor-pointer">×</button></div>}
      {!messages.length && <p className="m-0 text-[11px] text-admin-muted">Chưa có tin nhắn.</p>}
      {messages.map((message) => <Message key={message.MessageId} message={message} operator={user} active={status === 'active'} />)}
      {waiting && <div className="min-h-[72px] shrink-0 rounded-[10px] border border-admin-border bg-admin-page px-3.5 py-3"><p className="m-0 text-[10px] leading-[normal] font-semibold">Cuộc trò chuyện đang chờ tiếp nhận</p></div>}
      {!open && <p className="text-[11px] text-admin-muted">Cuộc trò chuyện đã kết thúc.</p>}
    </div>
    <footer className="flex min-h-[124px] shrink-0 items-center gap-3 border-t border-admin-border px-[18px] py-3.5">
      {waiting ? <><div className="min-w-0 flex-1"><p className="m-0 text-[10px] leading-[normal] font-semibold">Sẵn sàng hỗ trợ khách hàng?</p><p className="mt-1 mb-0 text-[9px] leading-[normal] text-admin-muted">Sau khi tiếp nhận, bạn có thể gửi và nhận tin nhắn trong cuộc trò chuyện này.</p></div>{canWrite && <NewsButton disabled={disabled} onClick={() => act('claim')}>{busy === 'claim' ? 'Đang tiếp nhận…' : 'Tiếp nhận cuộc trò chuyện'}</NewsButton>}</> : mine && open && canWrite ? <form className="flex w-full items-center gap-2.5" onSubmit={(event) => { event.preventDefault(); void act('send') }}>
        <label htmlFor="support-reply" className="sr-only">Tin nhắn trả lời</label><textarea id="support-reply" value={draft} onChange={(event) => onDraft(event.target.value)} disabled={!!busy} maxLength={5000} rows={2} placeholder="Nhập tin nhắn phản hồi khách hàng..." className="support-composer block min-w-0 shrink resize-none rounded-[9px] border border-admin-border bg-white px-3 py-3 text-sm text-admin-text placeholder:text-admin-muted focus:border-admin-blue focus:outline-none disabled:opacity-60" />
        <NewsButton type="submit" aria-label="Gửi tin nhắn" className="shrink-0" disabled={disabled || !draft.trim()}>{busy === 'send' ? 'Đang gửi…' : 'Gửi'}</NewsButton>
      </form> : <p className="m-0 text-[11px] text-admin-muted">{!open ? 'Cuộc trò chuyện đã kết thúc.' : conversation.Mode === 'AI' ? 'Hội thoại với AI chỉ được xem tại đây.' : !mine ? `Cuộc trò chuyện đang do ${conversation.AssignedStaffName || 'nhân viên khác'} phụ trách.` : 'Bạn chưa có quyền gửi tin nhắn.'}</p>}
    </footer>
    <Modal open={confirmClose} title="Kết thúc cuộc trò chuyện?" variant="news-delete" className="w-[470px]" busy={!!busy} onClose={() => setConfirmClose(false)} footer={<><NewsButton secondary disabled={!!busy} onClick={() => setConfirmClose(false)}>Hủy</NewsButton><NewsButton disabled={disabled} onClick={() => act('close')}>{busy === 'close' ? 'Đang kết thúc…' : 'Xác nhận kết thúc'}</NewsButton></>}><p className="m-0 text-xs text-admin-muted">Bạn và khách hàng sẽ không thể gửi thêm tin nhắn trong cuộc trò chuyện này.</p></Modal>
    {sendFailure && <SupportSendErrorDialog failure={sendFailure} busy={busy === 'send'} canRetry={!state.loading && mine && open && canWrite} onClose={() => setSendFailure(null)} onRetry={() => act('send', sendFailure.content)} />}
  </section>
}
