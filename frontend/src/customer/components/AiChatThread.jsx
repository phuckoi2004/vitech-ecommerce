import { useEffect, useEffectEvent, useId, useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Money from '../../components/shared/Money.jsx'
import useCustomerRequest from '../../hooks/useCustomerRequest.js'
import { formatDateTime } from '../../lib/format.js'
import useChatDraft from '../chat-drafts.js'
import { productPath } from '../routes/paths.js'
import StoreImage from './StoreImage.jsx'
import AiChatIcon from './AiChatIcon.jsx'
import AiChatText from './AiChatText.jsx'
import { mergeMessages, readTurn, storeTurn, turnStorageKey, unfinishedTurn } from './ai-chat-state.js'

function ProductSuggestion({ message, onLoad }) {
  const product = message.Metadata ?? {}
  if (!product.Slug || !product.ProductName) return null
  const image = typeof product.ImageUrl === 'string' && /^(https?:\/\/|\/(?!\/))/i.test(product.ImageUrl) ? product.ImageUrl : null
  return <Link className="ai-chat-product" to={productPath(product.Slug)}>
    <StoreImage src={image} alt="" loading="lazy" onLoad={onLoad} fallback={<span className="ai-chat-product-fallback" aria-hidden="true">VT</span>} />
    <span><strong>{product.Rank}. {product.ProductName}</strong><small>{product.VariantName}</small>
      <Money value={product.Price} className="ai-chat-price" />
      {Number(product.OriginalPrice) > Number(product.Price) && <del><Money value={product.OriginalPrice} /></del>}
      <small>{product.InStock ? 'Còn hàng khi tư vấn' : 'Xem tình trạng hàng'}</small>
    </span>
  </Link>
}

const suggestions = [
  { icon: 'laptop', label: 'Chọn laptop', description: 'Học tập & làm việc', prompt: 'Tư vấn giúp tôi laptop để học tập và làm việc dưới 20 triệu.' },
  { icon: 'phone', label: 'Tìm điện thoại', description: 'Đúng nhu cầu của bạn', prompt: 'Tôi cần mua điện thoại, bạn có thể giúp tôi chọn theo nhu cầu và ngân sách không?' },
  { icon: 'compare', label: 'So sánh sản phẩm', description: 'Cân nhắc trước khi chọn', prompt: 'Tôi muốn so sánh hai sản phẩm. Bạn cần những thông tin gì?' },
  { icon: 'budget', label: 'Chọn theo ngân sách', description: 'Tìm lựa chọn phù hợp', prompt: 'Giúp tôi chọn sản phẩm phù hợp với ngân sách, bạn cần biết những gì?' },
]

export default function AiChatThread({ conversation, userId, onLockedChange, disabled = false, onNew, onQuestion }) {
  const send = useCustomerRequest()
  const storageKey = turnStorageKey(userId, conversation.ConversationId)
  const path = `/conversations/${encodeURIComponent(conversation.ConversationId)}`
  const [messages, setMessages] = useState(conversation.Messages ?? [])
  const [turn, setTurn] = useState(() => conversation.Status === 'Open'
    ? unfinishedTurn(conversation.Messages ?? [], readTurn(storageKey)) : null)
  const [phase, setPhase] = useState(turn ? 'checking' : 'idle')
  const [error, setError] = useState('')
  const [retryAt, setRetryAt] = useState(turn?.retryAt ?? 0)
  const [clock, setClock] = useState(Date.now())
  const [version, setVersion] = useState(0)
  const [draft, setDraft, clearDraft] = useChatDraft(conversation.ConversationId)
  const control = useRef(null)
  const generation = useRef(0)
  const cancelling = useRef(false)
  const mounted = useRef(false)
  const log = useRef(null)
  const composer = useRef(null)
  const nearBottom = useRef(true)
  const inputId = useId()
  const hintId = useId()
  const open = conversation.Status === 'Open'
  const waiting = ['sending', 'checking', 'pending', 'stopping'].includes(phase)
  const showStop = Boolean(turn) && phase !== 'failed'
  const seconds = Math.max(0, Math.ceil((retryAt - clock) / 1000))
  const requestId = turn?.id

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; control.current?.abort() }
  }, [])
  useEffect(() => { if (!turn) storeTurn(storageKey, null) }, [turn, storageKey])
  useLayoutEffect(() => {
    if (!composer.current) return
    composer.current.style.height = 'auto'
    composer.current.style.height = `${Math.min(144, Math.max(48, composer.current.scrollHeight))}px`
  }, [draft])
  useEffect(() => { onLockedChange(waiting); return () => onLockedChange(false) }, [waiting, onLockedChange])
  useEffect(() => {
    if (retryAt <= Date.now()) return
    const timer = setInterval(() => setClock(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [retryAt])

  function scrollToBottom() {
    if (nearBottom.current && log.current) log.current.scrollTop = log.current.scrollHeight
  }
  useEffect(scrollToBottom, [messages, phase])

  function retain(next) { storeTurn(storageKey, next); setTurn(next) }
  function apply(response, request) {
    setMessages((current) => mergeMessages(current, [response.CustomerMessage, ...response.AiMessages]))
    if (response.Status === 'Completed' || response.Status === 'Cancelled') {
      clearDraft(request.draft ?? request.content)
      retain(null); setPhase('idle'); setError(''); setRetryAt(0)
    } else if (response.Status === 'Pending') setPhase('pending')
    else { setPhase('failed'); setError(request.failureMessage || 'AI chưa trả lời được câu hỏi này. Bạn có thể thử lại hoặc bỏ qua để hỏi câu khác.') }
  }

  async function timedRequest(url, options = {}) {
    const controller = new AbortController()
    control.current = controller
    const timer = setTimeout(() => controller.abort(), 135000)  // Server AI timeout (120 s) plus margin.
    try { return await send(url, { ...options, signal: controller.signal }) }
    finally { clearTimeout(timer); if (control.current === controller) control.current = null }
  }

  // Check before every retry, and after remount. A cancelled browser request can still finish on the server.
  async function recover(request, resend = false) {
    if (!request || !mounted.current || control.current) return
    if (request.cancelRequested) { await stop(request); return }
    const current = generation.current
    setPhase('checking'); setError('')
    clearDraft(request.draft ?? request.content)
    try {
      let response
      try { response = await timedRequest(`${path}/ai-messages/${encodeURIComponent(request.id)}`) }
      catch (failure) { if (failure.code !== 'ai_request_not_found') throw failure }
      if (!mounted.current || generation.current !== current) return
      if (response) {
        apply(response, request)
        if (response.Status !== 'Failed' || !resend) return
      } else if (!resend) {
        setPhase('failed'); setError(request.failureMessage || 'Chưa xác nhận được câu hỏi đã gửi. Chọn thử lại để tiếp tục.'); return
      }
      await post(request)
    } catch (failure) { if (generation.current === current) handleFailure(failure, request) }
  }

  function handleFailure(failure, request) {
    if (!mounted.current) return
    const until = failure.retryAfter ? Date.now() + failure.retryAfter * 1000 : request.retryAt ?? 0
    const failureMessage = failure.name === 'AbortError' ? 'Chờ phản hồi quá lâu. Kiểm tra lại kết quả trước khi thử gửi lại.' : failure.message
    const terminal = failure.code === 'ai_retry_limit' || failure.code === 'conversation_closed'
    retain({ ...request, retryAt: until, failureMessage, terminal }); setRetryAt(until); setClock(Date.now())
    // Reaching the retry cap is terminal. Permit another question without resending this UUID.
    setPhase(terminal ? 'failed' : 'uncertain')
    setError(failureMessage)
  }

  async function post(request) {
    const current = generation.current
    setPhase('sending'); setError('')
    try {
      const response = await timedRequest(`${path}/ai-messages`, {
        method: 'POST', body: { ClientRequestId: request.id, MessageType: 'Text', Content: request.content },
      })
      if (!mounted.current || generation.current !== current) return
      clearDraft(request.draft ?? request.content)
      apply(response, request)
    } catch (failure) {
      if (generation.current !== current) return
      handleFailure(failure, request)
      // A server-side completion may have been lost in transit. Poll status, never automatically POST again.
      if (mounted.current && !['ai_retry_limit', 'conversation_closed'].includes(failure.code)) setVersion((value) => value + 1)
    }
  }

  async function stop(request = turn) {
    if (!request || !mounted.current || cancelling.current) return
    cancelling.current = true
    const current = ++generation.current
    const cancelled = { ...request, cancelRequested: true }
    retain(cancelled); setPhase('stopping'); setError('')
    control.current?.abort()
    control.current = null
    try {
      const response = await timedRequest(`${path}/ai-messages/${encodeURIComponent(request.id)}/cancel`, {
        method: 'POST', body: { Content: request.content },
      })
      if (!mounted.current || generation.current !== current) return
      apply(response, cancelled)
    } catch {
      if (mounted.current && generation.current === current) {
        setPhase('cancel-error')
        setError('Chưa xác nhận được việc dừng trả lời. Bạn hãy thử dừng lại.')
      }
    } finally { if (generation.current === current) cancelling.current = false }
  }

  const recoverLatest = useEffectEvent(() => {
    // A failed stop waits for an explicit retry; an old recovery timer must not restart it.
    if (phase !== 'stopping' && phase !== 'cancel-error') recover(turn)
  })
  useEffect(() => {
    if (!requestId || !open) return
    let cancelled = false
    const current = generation.current
    const timer = setTimeout(() => { if (!cancelled && generation.current === current) recoverLatest() }, 0)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [requestId, version, open])

  useEffect(() => {
    if (phase !== 'pending' || !turn) return
    const timer = setTimeout(() => setVersion((value) => value + 1), 2000)
    return () => clearTimeout(timer)
  }, [phase, turn, version])

  async function submit(event) {
    event.preventDefault()
    const content = draft.trim()
    if (disabled || turn || control.current || !open || !content || content.length > 1000) return
    const request = { id: crypto.randomUUID(), content, draft }
    generation.current += 1
    clearDraft(draft)
    onQuestion?.(content)
    nearBottom.current = true
    retain(request)
    // The initial POST owns recovery until it returns; its controller prevents the mount effect racing it.
    await post(request)
  }

  const customerVisible = turn && messages.some((message) => message.Metadata?.ClientRequestId === turn.id)
  return <div className="ai-chat-thread">
    <div className="ai-chat-messages" role="log" aria-label="Tin nhắn AI" aria-live="polite" ref={log}
      onScroll={() => { const node = log.current; nearBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80 }}>
      {!messages.length && !turn && <div className="ai-chat-welcome">
        <span className="ai-chat-avatar ai-chat-welcome-avatar"><AiChatIcon name="sparkles" /></span>
        <span className="ai-chat-eyebrow">CÙNG VIETECH CHỌN ĐIỀU PHÙ HỢP</span>
        <h3>Chào bạn,<br /><span>hôm nay bạn cần gì?</span></h3>
        <p>Kể tôi nghe nhu cầu của bạn.<br />Mình cùng tìm một lựa chọn thật vừa ý.</p>
        {open && <div className="ai-chat-suggestions">{suggestions.map((suggestion) => <button key={suggestion.icon}
          type="button" disabled={disabled} onClick={() => { setDraft(suggestion.prompt); composer.current?.focus() }}>
          <AiChatIcon name={suggestion.icon} /><strong>{suggestion.label}</strong><small>{suggestion.description}</small>
        </button>)}</div>}
      </div>}
      {messages.filter((message) => message.MessageType !== 'Product').map((message) => <article key={message.MessageId}
        className={`ai-chat-message ${message.SenderType === 'Customer' ? 'is-customer' : ''}`}>
        {message.SenderType !== 'Customer' && <span className="ai-chat-avatar ai-chat-message-avatar"><AiChatIcon name="sparkles" /></span>}
        <div className="ai-chat-message-body"><small className={message.SenderType === 'Customer' ? 'sr-only' : 'ai-chat-sender'}>{message.SenderType === 'Customer' ? 'Bạn' : 'VieTech AI'}</small>
        {message.SenderType === 'AI' ? <AiChatText content={message.Content} /> : <p>{message.Content}</p>}
        {message.Metadata?.AiProcessingStatus === 'Failed' && message.Metadata.ClientRequestId !== requestId && <small>Chưa nhận được câu trả lời.</small>}
        {message.Metadata?.AiProcessingStatus === 'Cancelled' && <small>Đã dừng trả lời.</small>}
        {messages.filter((card) => card.MessageType === 'Product' && card.Metadata?.AiAnswerMessageId === message.MessageId)
          .sort((a, b) => a.Metadata.Rank - b.Metadata.Rank).slice(0, 5)
          .map((card) => <ProductSuggestion key={card.MessageId} message={card} onLoad={scrollToBottom} />)}
        <time dateTime={message.SentAt}>{formatDateTime(message.SentAt)}</time></div>
      </article>)}
      {turn && !customerVisible && <article className="ai-chat-message is-customer"><div className="ai-chat-message-body"><small className="sr-only">Bạn</small><p>{turn.content}</p></div></article>}
      {waiting && <div className="ai-chat-progress" role="status"><span className="ai-chat-avatar"><AiChatIcon name="sparkles" /></span>
        <span><span className="ai-chat-thinking"><i /><i /><i /></span><span className="sr-only">{phase === 'stopping' ? 'Đang dừng trả lời…' : phase === 'checking' ? 'Đang kiểm tra kết quả…' : 'AI đang trả lời…'}</span></span></div>}
    </div>
    {error && <div className="ai-chat-error"><p role="alert">{error}</p>
      {turn && !turn.terminal && !waiting && <button type="button" disabled={disabled || (!turn.cancelRequested && seconds > 0)} onClick={() => recover(turn, true)}>
        {turn.cancelRequested ? 'Thử dừng lại' : seconds > 0 ? `Thử lại sau ${seconds}s` : 'Kiểm tra và thử lại'}
      </button>}
      {phase === 'failed' && <button type="button" disabled={disabled} onClick={() => { retain(null); setPhase('idle'); setError(''); clearDraft(turn.draft ?? turn.content) }}>Bỏ qua câu hỏi</button>}
    </div>}
    {open ? <div className="ai-chat-compose-area"><form className="ai-chat-composer" onSubmit={submit}>
      <label className="sr-only" htmlFor={inputId}>Câu hỏi cho AI</label>
      <textarea ref={composer} id={inputId} value={draft} maxLength={1000} rows={1} placeholder="Hỏi VieTech AI bất cứ điều gì…"
        aria-describedby={hintId} disabled={disabled || Boolean(turn)} onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); submit(event) } }} />
      <div className="ai-chat-composer-bottom"><span className="ai-chat-composer-brand"><AiChatIcon name="sparkles" />VieTech AI</span>
        <small id={hintId}>{draft.length > 0 ? `${draft.length}/1.000` : 'Enter để gửi · Shift + Enter xuống dòng'}</small>
        <button className={`ai-chat-send${showStop ? ' is-stop' : ''}`} type={showStop ? 'button' : 'submit'}
          disabled={disabled || phase === 'stopping' || (!showStop && (Boolean(turn) || !draft.trim() || draft.trim().length > 1000))}
          aria-label={showStop ? 'Dừng trả lời AI' : 'Gửi câu hỏi AI'} aria-busy={phase === 'stopping' || undefined}
          title={showStop ? 'Dừng trả lời' : 'Gửi tin nhắn'} onClick={showStop ? () => stop() : undefined}>
          <AiChatIcon name={showStop ? 'stop' : 'send'} />
        </button>
      </div>
    </form></div>
      : <div className="ai-chat-closed"><p>Cuộc trò chuyện này đã kết thúc.</p><button type="button" className="ai-chat-primary" disabled={disabled} onClick={onNew}><AiChatIcon name="new" />Bắt đầu cuộc trò chuyện mới</button></div>}
  </div>
}
