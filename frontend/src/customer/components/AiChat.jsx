import { useEffect, useId, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import useCustomerRequest from '../../hooks/useCustomerRequest.js'
import useApiData from '../../hooks/useApiData.js'
import { formatDate, formatDateTime } from '../../lib/format.js'
import { LOGIN_PATH } from '../routes/paths.js'
import { useDraftHandoff } from '../chat-drafts.js'
import AiChatThread from './AiChatThread.jsx'
import AiChatIcon from './AiChatIcon.jsx'
import './AiChat.css'

function ChatHeader({ titleId, onDismiss, onHistory, menu, historyId, loading, historyButton }) {
  return <header className="ai-chat-header">
    <button ref={historyButton} type="button" className="ai-chat-icon-button" aria-label="Lịch sử AI" title="Lịch sử trò chuyện"
      aria-expanded={Boolean(menu)} aria-controls={historyId} disabled={!onHistory || loading} onClick={onHistory}><AiChatIcon name="history" /></button>
    <span className="ai-chat-avatar ai-chat-header-avatar"><AiChatIcon name="sparkles" /></span>
    <div className="ai-chat-heading"><h2 id={titleId}>Chat với AI</h2><p>Trợ lý mua sắm VieTech</p></div>
    <div className="ai-chat-header-actions">
      <button type="button" className="ai-chat-icon-button" aria-label="Đóng cửa sổ chat" title="Đóng cửa sổ" onClick={onDismiss}><AiChatIcon name="close" /></button>
    </div>
  </header>
}

export default function AiChat({ titleId, onDismiss }) {
  const { ready, user } = useCustomerSession()
  const location = useLocation()
  const headerProps = { titleId, onDismiss }
  return <div className="ai-chat">
    {ready && user ? <AiChatSession key={user.UserId} userId={user.UserId} headerProps={headerProps} /> : <>
      <ChatHeader {...headerProps} />
      {!ready ? <div className="ai-chat-empty" role="status">Đang kiểm tra đăng nhập…</div>
        : <div className="ai-chat-empty ai-chat-guest"><span className="ai-chat-avatar ai-chat-welcome-avatar"><AiChatIcon name="sparkles" /></span>
          <span className="ai-chat-eyebrow">VIETECH AI</span><h3>Đăng nhập để chat với AI</h3>
          <p>Một chút gợi ý, một lựa chọn phù hợp.<br />Cùng tìm sản phẩm dành cho bạn.</p>
          <Link className="ai-chat-primary" to={`${LOGIN_PATH}?next=${encodeURIComponent(location.pathname + location.search + location.hash)}`}>Đăng nhập <AiChatIcon name="chevron" /></Link>
          <small>Hội thoại được lưu trong tài khoản của bạn.</small>
        </div>}
    </>}
  </div>
}

function groupHistory(items) {
  const today = formatDate(Date.now())
  const yesterday = formatDate(Date.now() - 86400000)
  const groups = new Map()
  for (const item of items) {
    const date = formatDate(item.CreatedAt)
    const label = date === today ? 'Hôm nay' : date === yesterday ? 'Hôm qua' : 'Trước đó'
    if (!groups.has(label)) groups.set(label, [])
    groups.get(label).push(item)
  }
  return [...groups]
}

function AiChatSession({ userId, headerProps }) {
  const send = useCustomerRequest()
  const handOffDraft = useDraftHandoff()
  const [conversation, setConversation] = useState(null)
  const [blocked, setBlocked] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [threadVersion, setThreadVersion] = useState(0)
  const [locked, setLocked] = useState(false)
  const [menu, setMenu] = useState(false)
  const [page, setPage] = useState(1)
  const [titles, setTitles] = useState({})
  const action = useRef(null)
  const historyPanel = useRef(null)
  const historyButton = useRef(null)
  const historyId = useId()
  const historyQuery = useApiData(menu ? `ai-history:${userId}:${page}` : null,
    (signal) => send('/conversations', { query: { mode: 'AI', page, page_size: 20 }, signal }))
  const history = historyQuery.data
  const basePath = (id) => `/conversations/${encodeURIComponent(id)}`

  function showConversation(detail) {
    setConversation(detail); setThreadVersion((value) => value + 1)
    const firstQuestion = detail.Messages?.find((message) => message.SenderType === 'Customer' && message.MessageType === 'Text')?.Content
    if (firstQuestion) setTitles((current) => ({ ...current, [detail.ConversationId]: firstQuestion }))
  }

  useEffect(() => {
    const controller = new AbortController()
    async function initialize() {
      setLoading(true); setError(''); setBlocked(false)
      try {
        const response = await send('/conversations', { query: { status: 'Open', page_size: 1 }, signal: controller.signal })
        controller.signal.throwIfAborted()
        let current = response.Items?.[0]
        // The server closes an open staff conversation only while it has no messages; otherwise it refuses.
        if (current?.Mode !== 'AI') {
          const replaced = current
          try { current = await send('/conversations', { method: 'POST', body: { Mode: 'AI' }, signal: controller.signal }) }
          catch (failure) {
            if (failure.code !== 'open_conversation_exists') throw failure
            setBlocked(true); setConversation(null); return
          }
          handOffDraft(replaced, current)
        }
        const detail = await send(basePath(current.ConversationId), { signal: controller.signal })
        controller.signal.throwIfAborted()
        showConversation(detail)
      } catch (failure) { if (!controller.signal.aborted) setError(failure.message) }
      finally { if (!controller.signal.aborted) setLoading(false) }
    }
    initialize()
    return () => controller.abort()
  }, [send, attempt, handOffDraft])

  useEffect(() => () => action.current?.abort(), [])
  useEffect(() => { if (menu) historyPanel.current?.focus() }, [menu])

  function closeHistory() { setMenu(false); historyButton.current?.focus() }
  async function select(item) {
    if (action.current || locked) return
    const controller = new AbortController(); action.current = controller
    setLoading(true); setError('')
    try {
      const detail = await send(basePath(item.ConversationId), { signal: controller.signal })
      controller.signal.throwIfAborted()
      showConversation(detail); setBlocked(false); closeHistory()
    } catch (failure) { if (!controller.signal.aborted) setError(failure.message) }
    finally { if (action.current === controller) { action.current = null; if (!controller.signal.aborted) setLoading(false) } }
  }

  async function createNew({ allowOther = false } = {}) {
    if (action.current || locked || loading) return
    const controller = new AbortController(); action.current = controller
    setLoading(true); setError('')
    try {
      const response = await send('/conversations', { query: { status: 'Open', page_size: 1 }, signal: controller.signal })
      controller.signal.throwIfAborted()
      const current = response.Items?.[0]
      if (current && current.Mode !== 'AI' && !allowOther) {
        setBlocked(true); setConversation(null); setMenu(false); return
      }
      if (current) {
        try { await send(`${basePath(current.ConversationId)}/close`, { method: 'POST', signal: controller.signal }) }
        catch (failure) { if (failure.code !== 'conversation_closed') throw failure }
        controller.signal.throwIfAborted()
        setConversation((previous) => previous?.ConversationId === current.ConversationId ? { ...previous, Status: 'Closed' } : previous)
      }
      const next = await send('/conversations', { method: 'POST', body: { Mode: 'AI' }, signal: controller.signal })
      const detail = await send(basePath(next.ConversationId), { signal: controller.signal })
      controller.signal.throwIfAborted()
      showConversation(detail); setBlocked(false); setMenu(false); setPage(1)
    } catch (failure) { if (!controller.signal.aborted) { setError(failure.message); setMenu(false) } }
    finally { if (action.current === controller) { action.current = null; if (!controller.signal.aborted) setLoading(false) } }
  }

  const aiHistory = history?.Items.filter((item) => item.Mode === 'AI') ?? []
  return <>
    <ChatHeader {...headerProps} onHistory={() => { setMenu(!menu); historyQuery.reload() }}
      menu={menu} historyId={historyId} loading={loading} historyButton={historyButton} />
    <div className="ai-chat-workspace" onKeyDown={(event) => { if (event.key === 'Escape' && menu) { event.stopPropagation(); closeHistory() } }}>
      <div className="ai-chat-main" inert={menu || undefined} aria-hidden={menu || undefined}>
        {error && <div className="ai-chat-error"><p role="alert">{error}</p><button type="button" disabled={loading} onClick={() => setAttempt((value) => value + 1)}>Tải lại hội thoại</button></div>}
        {loading && !conversation && <div className="ai-chat-empty" role="status"><span className="ai-chat-avatar"><AiChatIcon name="sparkles" /></span><p>Đang chuẩn bị cuộc trò chuyện…</p></div>}
        {blocked ? <div className="ai-chat-empty"><span className="ai-chat-avatar ai-chat-welcome-avatar"><AiChatIcon name="message" /></span>
          <h3>Bạn đang có phiên tư vấn khác</h3><p>Kết thúc phiên đang mở để bắt đầu trò chuyện với AI. Lịch sử của bạn vẫn được lưu.</p>
          <button className="ai-chat-primary" type="button" disabled={loading} onClick={() => createNew({ allowOther: true })}>Kết thúc phiên hiện tại và mở AI</button>
        </div> : conversation && <AiChatThread key={`${conversation.ConversationId}:${conversation.Status}:${threadVersion}`}
          conversation={conversation} userId={userId} onLockedChange={setLocked} disabled={loading}
          onNew={createNew} onQuestion={(content) => setTitles((current) => current[conversation.ConversationId] ? current : { ...current, [conversation.ConversationId]: content })} />}
      </div>
      {menu && <div className="ai-chat-history-layer">
        <button className="ai-chat-history-scrim" type="button" aria-label="Trở lại trò chuyện" tabIndex={-1} onClick={closeHistory} />
        <section ref={historyPanel} id={historyId} className="ai-chat-history" aria-label="Lịch sử chat AI" tabIndex={-1}>
          <div className="ai-chat-history-heading"><div><h3>Cuộc trò chuyện</h3><p>Mọi gợi ý, ở cùng một nơi.</p></div>
            <button className="ai-chat-icon-button" type="button" aria-label="Đóng lịch sử" onClick={closeHistory}><AiChatIcon name="close" /></button></div>
          <button className="ai-chat-new-button" type="button" disabled={loading || locked || blocked} onClick={createNew}><AiChatIcon name="new" />Cuộc trò chuyện mới</button>
          <div className="ai-chat-history-list">
            {historyQuery.error ? <div className="ai-chat-error"><p role="alert">{historyQuery.error}</p><button type="button" onClick={historyQuery.reload}>Tải lại lịch sử</button></div>
              : !history ? <p className="ai-chat-note" role="status">Đang tải lịch sử…</p> : aiHistory.length ? groupHistory(aiHistory).map(([group, items]) => <div className="ai-chat-history-group" key={group}>
                <h4>{group}</h4><ul>{items.map((item) => <li key={item.ConversationId}>
                  <button className="ai-chat-history-item" type="button" disabled={loading || locked} onClick={() => select(item)} aria-pressed={item.ConversationId === conversation?.ConversationId}>
                    <AiChatIcon name="message" /><span><strong>{item.Title || titles[item.ConversationId] || 'Tư vấn mua sắm'}</strong>
                      <small>{formatDateTime(item.CreatedAt)}<span className={item.Status === 'Open' ? 'is-open' : ''}>{item.Status === 'Open' ? 'Đang mở' : 'Đã kết thúc'}</span></small></span>
                  </button></li>)}</ul></div>) : <div className="ai-chat-history-empty"><AiChatIcon name="message" /><p>Chưa có cuộc trò chuyện nào trên trang này.</p></div>}
          </div>
          {history && history.Total > 20 && <nav className="ai-chat-pages" aria-label="Trang lịch sử AI"><button type="button" disabled={page <= 1 || loading} onClick={() => setPage(page - 1)}>Trước</button>
            <span>{page} / {Math.ceil(history.Total / 20)}</span><button type="button" disabled={page * 20 >= history.Total || loading} onClick={() => setPage(page + 1)}>Sau</button></nav>}
          <div className="ai-chat-history-footer"><AiChatIcon name="sparkles" /><span>VieTech AI<small>Giúp bạn chọn, theo cách của bạn.</small></span></div>
        </section>
      </div>}
    </div>
  </>
}
