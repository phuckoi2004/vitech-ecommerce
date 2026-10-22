import { createContext, useCallback, useContext } from 'react'

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

// Opening one mode makes the server close an open conversation of the other mode that has no messages;
// its unsent draft waits for the next conversation of that mode instead of being lost.
export function useDraftHandoff() {
  const { setDrafts } = useContext(ChatDraftContext)
  return useCallback(function handOff(replaced, opened) {
    setDrafts((current) => {
      const next = new Map(current)
      const unsent = replaced && next.get(replaced.ConversationId)
      if (unsent) { next.delete(replaced.ConversationId); next.set(`unsent:${replaced.Mode}`, unsent) }
      const carried = next.get(`unsent:${opened.Mode}`)
      if (carried) {
        next.delete(`unsent:${opened.Mode}`)
        if (!next.has(opened.ConversationId)) next.set(opened.ConversationId, carried)
      }
      return next
    })
  }, [setDrafts])
}
