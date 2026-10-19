import { useState } from 'react'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { ChatDraftContext } from '../chat-drafts.js'

function ChatDraftScope({ userId, children }) {
  const [scope, setScope] = useState(() => ({ userId, generation: Symbol(), drafts: new Map() }))
  if (scope.userId !== userId) setScope({ userId, generation: Symbol(), drafts: new Map() })

  function setDrafts(update) {
    setScope(current => {
      // Ignore a late callback belonging to a customer who has signed out.
      if (current.generation !== scope.generation) return current
      return { ...current, drafts: typeof update === 'function' ? update(current.drafts) : update }
    })
  }
  return <ChatDraftContext.Provider value={{ drafts: scope.drafts, setDrafts }}>{children}</ChatDraftContext.Provider>
}

// Drafts live only in this customer session, across widget and conversation changes.
export default function ChatDraftProvider({ children }) {
  const { user } = useCustomerSession()
  // Clear private drafts without remounting the entire site and its route guards.
  return <ChatDraftScope userId={user?.UserId ?? 'anonymous'}>{children}</ChatDraftScope>
}
