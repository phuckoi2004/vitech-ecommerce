import { useEffect, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { StaffChat } from '../pages/ChatPage.jsx'
import { CHAT_PATH } from '../routes/paths.js'
import './CustomerChat.css'

function ChatIcon() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
    <path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H5l-3 2v-10a8.5 8.5 0 0 1 17-2" /><path d="M7 11h9M7 15h6" />
  </svg>
}

function AiIcon() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true">
    <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5zM20 2v4M18 4h4" />
  </svg>
}

// One employee-chat entry. Opening the window starts/reuses the real customer conversation.
// AI is intentionally a coming-soon view and never creates a conversation or sends a message.
export default function CustomerChat() {
  const { user } = useCustomerSession()
  // Reset only the chat window when the customer changes, preserving the page and route guard.
  return <CustomerChatWindow key={user?.UserId ?? 'anonymous'} />
}

function CustomerChatWindow() {
  const { ready, user } = useCustomerSession()
  const navigate = useNavigate()
  const [kind, setKind] = useState(null)
  const panel = useRef(null)
  const employeeButton = useRef(null)
  const aiButton = useRef(null)
  const panelId = useId()
  const titleId = useId()
  const activeKind = kind === 'Staff' && !user ? null : kind

  useEffect(() => {
    if (activeKind) panel.current?.focus()
  }, [activeKind])

  function close() {
    setKind(null)
    const launcher = activeKind === 'Staff' ? employeeButton : aiButton
    launcher.current?.focus()
  }

  function openEmployee() {
    if (!user) { navigate(CHAT_PATH); return }
    setKind((current) => current === 'Staff' ? null : 'Staff')
  }

  // Product consultation opens the existing employee chat without creating another chat UI.
  useEffect(() => {
    function openConsultation() {
      if (!ready) return
      if (!user) { navigate(CHAT_PATH); return }
      setKind('Staff')
    }
    window.addEventListener('vietech-open-staff-chat', openConsultation)
    return () => window.removeEventListener('vietech-open-staff-chat', openConsultation)
  }, [ready, user, navigate])

  return <>
    {activeKind && <section ref={panel} id={panelId} className={`shop-chat-panel shop-chat-panel-${activeKind.toLowerCase()}`} role="dialog"
      aria-modal="false" aria-labelledby={titleId} tabIndex={-1}
      onKeyDown={(event) => { if (event.key === 'Escape') { event.stopPropagation(); close() } }}>
      {activeKind === 'Staff' ? <StaffChat onDismiss={close} titleId={titleId} /> : <>
      <header className="shop-chat-panel-header">
        <div className="shop-chat-panel-title">
          <span className="shop-chat-panel-symbol"><AiIcon /></span>
          <div><h2 id={titleId}>Chat với AI</h2>
            <p>Trợ lý VieTech</p>
          </div>
        </div>
        <button type="button" className="shop-chat-close" aria-label="Đóng cửa sổ chat" onClick={close}>×</button>
      </header>
      <div className="shop-chat-panel-content">
        <div className="shop-chat-coming-soon">
          <span className="shop-chat-ai-symbol"><AiIcon /></span>
          <h3>Sắp ra mắt</h3>
          <p>Trợ lý AI của VieTech đang được hoàn thiện. Bạn có thể chat với nhân viên để được hỗ trợ ngay.</p>
        </div>
      </div>
      </>}
    </section>}
    <div className="shop-chat-actions" aria-label="Hỗ trợ trực tuyến">
      <button ref={employeeButton} type="button" className="shop-chat-button" disabled={!ready}
        aria-haspopup="dialog" aria-controls={activeKind === 'Staff' ? panelId : undefined}
        aria-expanded={activeKind === 'Staff'} onClick={openEmployee}>
        <ChatIcon /><span>Chat với nhân viên</span>
      </button>
      <button ref={aiButton} type="button" className="shop-chat-button shop-chat-button-ai"
        aria-haspopup="dialog" aria-controls={activeKind === 'AI' ? panelId : undefined}
        aria-expanded={activeKind === 'AI'} onClick={() => setKind((current) => current === 'AI' ? null : 'AI')}>
        <AiIcon /><span>Chat với AI</span>
      </button>
    </div>
  </>
}
