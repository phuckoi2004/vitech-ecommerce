import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import Button from '../../components/shared/Button.jsx'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import useApiData from '../../hooks/useApiData.js'
import useCustomerRequest from '../../hooks/useCustomerRequest.js'
import { formatDateTime } from '../../lib/format.js'
import useChatDraft, { useDraftHandoff } from '../chat-drafts.js'
import { productPath } from '../routes/paths.js'
import './ShoppingPages.css'
import './ChatPage.css'

function ChatMessageContent({ message, onImageLoad }) {
  const imageUrl = message.Metadata?.ImageUrl || message.Content
  const safeImage = typeof imageUrl === 'string' && /^https:\/\//i.test(imageUrl)
  const slug = message.Metadata?.Slug
  const productName = message.Metadata?.ProductName || 'Sản phẩm được tư vấn'
  const [imageFailed, setImageFailed] = useState(false)
  return <>
    {message.MessageType === 'Image' && (safeImage
      ? <a className="chat-attachment" href={imageUrl} target="_blank" rel="noreferrer" aria-label="Xem ảnh đính kèm">
        {!imageFailed && <img src={imageUrl} alt={message.Content || 'Ảnh đính kèm'} loading="lazy" onLoad={onImageLoad} onError={() => setImageFailed(true)} />}
        <span>Xem ảnh đính kèm</span>
      </a> : <p>Ảnh đính kèm không khả dụng.</p>)}
    {message.MessageType === 'Product' && (typeof slug === 'string' && slug.trim()
      ? <Link className="chat-product-link" to={productPath(slug)}>{productName}</Link>
      : <p className="chat-product-link">{productName}</p>)}
    {message.Content && <p>{message.Content}</p>}
  </>
}

function ChatThread({ conversationId, send, onClosed, paused = false }) {
  const [detail, setDetail] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState(null)
  const [text, setText, clearDraft] = useChatDraft(conversationId)
  const [busy, setBusy] = useState('')
  const [version, setVersion] = useState(0)
  const scroll = useRef(null)
  const nearBottom = useRef(true)
  const actionLock = useRef(false)
  const composer = useRef(null)
  const active = detail?.ConversationId === conversationId ? detail : null
  const messages = [...(active?.Messages ?? [])].sort((left, right) => Date.parse(left.SentAt) - Date.parse(right.SentAt))
  const count = messages.length
  const canSend = !!text.trim()
  const showStop = !canSend && messages.at(-1)?.SenderType === 'Customer'

  useEffect(() => {
    if (paused) return undefined
    const controller = new AbortController()
    let fetching = false
    async function refresh() {
      if (fetching || document.hidden || controller.signal.aborted) return
      fetching = true
      try {
        const response = await send(`/conversations/${encodeURIComponent(conversationId)}`, { signal: controller.signal })
        if (!controller.signal.aborted) { setDetail(response); setLoadError('') }
      } catch (failure) { if (!controller.signal.aborted) setLoadError(failure.message) }
      finally { fetching = false }
    }
    refresh()
    const timer = window.setInterval(refresh, 5000)
    document.addEventListener('visibilitychange', refresh)
    return () => { controller.abort(); window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh) }
  }, [conversationId, send, version, paused])

  function followLatest() {
    if (nearBottom.current && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight
  }
  useLayoutEffect(() => { followLatest() }, [count])
  useEffect(() => {
    if (!composer.current) return
    composer.current.style.height = 'auto'
    composer.current.style.height = `${Math.min(128, Math.max(46, composer.current.scrollHeight))}px`
  }, [text, active?.Status])
  useEffect(() => { if (!paused && !busy && active?.Status === 'Open') composer.current?.focus() }, [busy, active?.Status, paused])

  async function sendMessage(draft) {
    const content = draft.trim()
    if (!content || actionLock.current) return
    actionLock.current = true
    setBusy('send'); setActionError(null)
    try {
      const message = await send(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
        method: 'POST', body: { MessageType: 'Text', Content: content },
      })
      nearBottom.current = true
      setDetail((current) => ({ ...current, Messages: [...(current?.Messages ?? []).filter((item) => item.MessageId !== message.MessageId), message] }))
      clearDraft(draft); setVersion((value) => value + 1)
    } catch (failure) { setActionError({ operation: 'send', message: failure.message, draft }) }
    finally { actionLock.current = false; setBusy('') }
  }

  function submit(event) {
    event.preventDefault()
    sendMessage(text)
  }

  async function close() {
    if (actionLock.current) return
    actionLock.current = true
    setBusy('close'); setActionError(null)
    try {
      const closed = await send(`/conversations/${encodeURIComponent(conversationId)}/close`, { method: 'POST' })
      setDetail((current) => ({ ...current, ...closed, Status: 'Closed' }))
      onClosed(closed)
    }
    catch (failure) { setActionError({ operation: 'close', message: failure.message }) }
    finally { actionLock.current = false; setBusy('') }
  }

  return <section className="chat-thread" aria-label="Hội thoại với nhân viên">
    {active?.Status === 'Closed' && <p className="chat-closed-status" role="status">Hội thoại đã kết thúc</p>}
    {loadError && <p className="shopping-notice" role="alert">{loadError} <button type="button" onClick={() => setVersion((value) => value + 1)}>Thử lại</button></p>}
    {actionError && <div className="shopping-notice" role="alert">
      {actionError.message}
      {actionError.operation === 'send' && <p className="chat-failed-text">Tin chưa gửi: {actionError.draft}</p>}
      <button type="button" disabled={!!busy || active?.Status !== 'Open'} onClick={() => actionError.operation === 'send' ? sendMessage(actionError.draft) : close()}>Thử lại</button>
    </div>}
    {!active ? !loadError && <LoadingState /> : <>
      <div ref={scroll} className="chat-messages" role="log" aria-label="Tin nhắn" aria-live="polite"
        onScroll={(event) => {
          const node = event.currentTarget
          nearBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight <= 64
        }}>
        {messages.length ? messages.map((message) => <article key={message.MessageId}
          className={`chat-message ${message.SenderType === 'Customer' ? 'is-mine' : ''}`}>
          <strong>{message.SenderType === 'Customer' ? 'Bạn' : message.SenderType === 'Staff' ? 'Nhân viên VieTech' : 'Trợ lý'}</strong>
          <ChatMessageContent message={message} onImageLoad={followLatest} />
          <time dateTime={message.SentAt}>{formatDateTime(message.SentAt)}</time>
        </article>) : <div className="chat-welcome">
          <span className="chat-welcome-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M4 14v-2a8 8 0 0 1 16 0v5c0 2-2 3-5 3" /><rect x="3" y="12" width="4" height="6" rx="2" /><rect x="17" y="12" width="4" height="6" rx="2" /><path d="M11 20h4" />
          </svg></span>
          <strong>Bạn cần hỗ trợ gì?</strong>
          <p>Gửi lời nhắn để nhân viên VieTech tiếp nhận và hỗ trợ bạn.</p>
        </div>}
      </div>
      {active?.Status === 'Open' && <form className="chat-compose" aria-label="Soạn tin nhắn" onSubmit={submit}>
        <label htmlFor="staff-message" className="sr-only">Nội dung tin nhắn</label>
        <div className="chat-compose-field">
          <textarea ref={composer} id="staff-message" value={text} onChange={(event) => setText(event.target.value)} maxLength={5000}
            placeholder="Nhắn tin cho nhân viên…" rows={1} disabled={!!busy}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) submit(event)
            }} />
          <button type={showStop ? 'button' : 'submit'} className={`chat-compose-action ${showStop ? 'is-stop' : 'is-send'}`}
            disabled={!!busy || (!canSend && !showStop)} aria-busy={!!busy || undefined} aria-label={showStop ? 'Dừng hội thoại' : 'Gửi tin nhắn'}
            title={showStop ? 'Dừng hội thoại' : 'Gửi tin nhắn'} onClick={showStop ? close : undefined}>
            {busy ? <span className="spinner" aria-hidden="true" /> : <svg viewBox="0 0 24 24" aria-hidden="true">
              {showStop ? <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
                : <path d="M12 19V5m-6 6 6-6 6 6" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />}
            </svg>}
          </button>
        </div>
      </form>}
    </>}
  </section>
}

// Mounted only after a customer opens chat (or returns here after signing in).
// The server reuses an open Staff conversation; initialization only closes an AI conversation that has no messages.
export function StaffChat({ onDismiss, titleId, expanded, onToggleExpand, initialConversationId = '' }) {
  const send = useCustomerRequest()
  const handOffDraft = useDraftHandoff()
  const [historyPage, setHistoryPage] = useState(1)
  const conversations = useApiData(`my-conversations:${historyPage}`, (signal) => send('/conversations', { query: { page: historyPage, page_size: 20 }, signal }))
  const { reload: reloadHistory } = conversations
  const [selected, setSelected] = useState(null)
  const [session, setSession] = useState(null)
  const [attempt, setAttempt] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const historyId = useId()
  const menuButton = useRef(null)
  const historyPanel = useRef(null)
  const creation = useRef(null)
  const items = conversations.data?.Items ?? []
  const current = session?.conversation
  const currentId = selected?.ConversationId || current?.ConversationId
  const history = historyPage === 1 && current && !items.some((item) => item.ConversationId === current.ConversationId)
    ? [current, ...items].slice(0, 20) : items
  const totalPages = Math.max(1, Math.ceil((conversations.data?.Total ?? 0) / 20))

  useEffect(() => {
    const controller = new AbortController()
    async function openChat() {
      try {
        if (initialConversationId) {
          const conversation = await send(`/conversations/${encodeURIComponent(initialConversationId)}`, { signal: controller.signal })
          if (!controller.signal.aborted) {
            setSession(conversation.Mode === 'Staff' ? { conversation } : { blocked: conversation })
            reloadHistory()
          }
          return
        }
        const response = await send('/conversations', { query: { status: 'Open', page_size: 1 }, signal: controller.signal })
        if (controller.signal.aborted) return
        const open = response.Items?.[0]
        const conversation = open?.Mode === 'Staff' ? open : await send('/conversations', {
          method: 'POST', body: { Mode: 'Staff' }, signal: controller.signal,
        })
        if (conversation !== open) handOffDraft(open, conversation)
        if (!controller.signal.aborted) { setSession({ conversation }); reloadHistory() }
      } catch (failure) {
        if (!controller.signal.aborted) setSession(failure.code === 'open_conversation_exists' ? { blocked: true } : { error: failure.message })
      }
    }
    openChat()
    return () => controller.abort()
  }, [send, attempt, reloadHistory, initialConversationId, handOffDraft])

  useEffect(() => () => creation.current?.abort(), [])
  useEffect(() => {
    if (menuOpen) { historyPanel.current?.focus(); reloadHistory() }
  }, [menuOpen, reloadHistory])

  function restart() {
    setSession(null); setSelected(null); setError(''); setAttempt((value) => value + 1)
  }

  async function createNew() {
    if (creation.current || !session) return
    const controller = new AbortController()
    creation.current = controller
    setBusy(true); setError('')
    try {
      const response = await send('/conversations', { query: { status: 'Open', page_size: 1 }, signal: controller.signal })
      const open = response.Items?.[0]
      if (open) {
        try {
          await send(`/conversations/${encodeURIComponent(open.ConversationId)}/close`, { method: 'POST', signal: controller.signal })
        } catch (failure) {
          if (failure.code !== 'conversation_closed') throw failure
        }
        controller.signal.throwIfAborted()
        setSession((previous) => previous?.conversation?.ConversationId === open.ConversationId
          ? { conversation: { ...previous.conversation, Status: 'Closed' } } : previous)
        setSelected((previous) => previous?.ConversationId === open.ConversationId ? { ...previous, Status: 'Closed' } : previous)
        reloadHistory()
      }
      const conversation = await send('/conversations', { method: 'POST', body: { Mode: 'Staff' }, signal: controller.signal })
      controller.signal.throwIfAborted()
      setSelected(null); setSession({ conversation }); setHistoryPage(1); reloadHistory(); setMenuOpen(false)
    } catch (failure) { if (!controller.signal.aborted) setError(failure.message) }
    finally { if (creation.current === controller) { creation.current = null; if (!controller.signal.aborted) setBusy(false) } }
  }

  return <div className="staff-chat" onKeyDown={(event) => {
    if (event.key === 'Escape' && menuOpen) { event.stopPropagation(); setMenuOpen(false); menuButton.current?.focus() }
  }}>
    <header className="staff-chat-header">
      <button ref={menuButton} className="staff-chat-menu-toggle" type="button" aria-label="Danh sách hội thoại"
        aria-expanded={menuOpen} aria-controls={historyId} disabled={busy} onClick={() => setMenuOpen((value) => !value)}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
      </button>
      <div className="staff-chat-heading"><h2 id={titleId}>Chat với nhân viên</h2><p>Hỗ trợ từ VieTech</p></div>
      {onToggleExpand && <button type="button" className="staff-chat-expand" aria-label={expanded ? 'Thu nhỏ cửa sổ chat' : 'Phóng to cửa sổ chat'}
        title={expanded ? 'Thu nhỏ' : 'Phóng to'} aria-pressed={Boolean(expanded)} onClick={onToggleExpand}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M10 20H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4" /><rect x="13" y="13" width="7" height="7" rx="1.5" />
          <path d={expanded ? 'm8 8 4 4m0-4v4H8' : 'M12 12 8 8m0 4V8h4'} />
        </svg>
      </button>}
      {onDismiss && <button type="button" className="staff-chat-dismiss" aria-label="Đóng cửa sổ chat" onClick={onDismiss}>×</button>}
    </header>
    <div className="staff-chat-body">
      <div className={`staff-chat-view ${menuOpen ? 'is-obscured' : ''}`} aria-hidden={menuOpen || undefined} inert={menuOpen || undefined}>
        {error && !menuOpen && <p role="alert" className="shopping-notice">{error}</p>}
        {currentId ? <ChatThread key={currentId} conversationId={currentId} send={send} paused={menuOpen || busy} onClosed={(closed) => {
          if (currentId === current?.ConversationId) setSession({ conversation: { ...current, ...closed, Status: 'Closed' } })
          setSelected((previous) => previous?.ConversationId === currentId ? { ...previous, ...closed, Status: 'Closed' } : previous)
          reloadHistory()
        }} /> : !session ? <LoadingState label="Đang mở hội thoại…" /> : session.error ? <ErrorState
          title="Chưa mở được hội thoại" message={session.error} onRetry={restart} /> : session.blocked ?
          <section className="shopping-panel"><p>Bạn có hội thoại với trợ lý đang mở. Chọn “Tạo hội thoại mới” trong menu để chuyển sang chat với nhân viên.</p></section> : null}
      </div>
      {menuOpen && <section ref={historyPanel} id={historyId} className="staff-chat-history" aria-label="Danh sách hội thoại" tabIndex={-1}>
        <div className="staff-chat-history-header"><h3>Hội thoại của bạn</h3>
          <Button variant="outline" size="sm" className="staff-chat-new" loading={busy} disabled={!session} onClick={createNew}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
            Tạo hội thoại mới
          </Button>
        </div>
        {error && <p role="alert" className="shopping-notice">{error}</p>}
        <div className="staff-chat-history-list">
          {conversations.loading ? <LoadingState label="Đang tải hội thoại…" /> : conversations.error ? <ErrorState
            title="Không tải được danh sách hội thoại" message={conversations.error} onRetry={reloadHistory} /> :
            history.filter((item) => item.Mode === 'Staff').length ? <ul>
              {history.filter((item) => item.Mode === 'Staff').map((item) => <li key={item.ConversationId}>
                <button type="button" className="staff-chat-history-item" aria-pressed={item.ConversationId === currentId}
                  disabled={busy} onClick={() => { setSelected(item); setMenuOpen(false); setError('') }}>
                  <span className="staff-chat-history-item-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M20 11a8 8 0 0 1-8 8H5l-3 2V11a8 8 0 0 1 16 0" /><path d="M7 10h8M7 14h5" /></svg></span>
                  <span><strong>{formatDateTime(item.CreatedAt)}</strong><span className={`staff-chat-history-status ${item.Status === 'Open' ? 'is-open' : ''}`}>
                    {item.Status === 'Open' ? 'Đang mở' : 'Đã kết thúc'}
                  </span></span>
                </button>
              </li>)}
            </ul> : <p className="staff-chat-history-empty">Chưa có hội thoại với nhân viên trên trang này.</p>}
        </div>
        {totalPages > 1 && <nav className="staff-chat-history-pages" aria-label="Trang lịch sử hội thoại">
          <button type="button" disabled={historyPage <= 1 || conversations.loading || busy} onClick={() => setHistoryPage((value) => value - 1)}>Trước</button>
          <span>Trang {historyPage} / {totalPages}</span>
          <button type="button" disabled={historyPage >= totalPages || conversations.loading || busy} onClick={() => setHistoryPage((value) => value + 1)}>Sau</button>
        </nav>}
      </section>}
    </div>
  </div>
}

export default function ChatPage() {
  const [params] = useSearchParams()
  const id = params.get('conversation') || ''
  return <div className="shopping-page chat-page"><h1 className="sr-only">Chat với nhân viên</h1>
    <StaffChat key={id} initialConversationId={id} />
  </div>
}
