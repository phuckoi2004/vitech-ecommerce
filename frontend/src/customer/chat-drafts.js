import { createContext, useContext } from 'react'

export const ChatDraftContext = createContext(null)

export default function useChatDraft(conversationId) {
  const { drafts, setDrafts } = useContext(ChatDraftContext)
  function update(value) {
    setDrafts((current) => {
      const next = new Map(current)
      if (value) next.set(conversationId, value)
      else next.delete(conversationId)
      return next
    })
  }
  function clear(expected) {
    setDrafts((current) => {
      // A late successful send must not erase a newer draft.
      if (current.get(conversationId) !== expected) return current
      const next = new Map(current)
      next.delete(conversationId)
      return next
    })
  }
  return [drafts.get(conversationId) ?? '', update, clear]
}
