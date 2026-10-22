// Only the unfinished turn is retained in this tab. Tokens and API keys never live here.
const prefix = 'vietech.ai-turn:'

export function turnStorageKey(userId, conversationId) {
  return `${prefix}${userId}:${conversationId}`
}

export function readTurn(key) {
  try {
    const turn = JSON.parse(sessionStorage.getItem(key))
    return typeof turn?.id === 'string' && typeof turn.content === 'string' ? turn : null
  } catch { return null }
}

export function storeTurn(key, turn) {
  try {
    if (turn) sessionStorage.setItem(key, JSON.stringify(turn))
    else sessionStorage.removeItem(key)
  } catch { /* History on the server still recovers accepted requests if storage is unavailable. */ }
}

export function mergeMessages(current, incoming) {
  const records = new Map(current.map((message) => [message.MessageId, message]))
  for (const message of incoming) if (message?.MessageId) records.set(message.MessageId, message)
  return [...records.values()].sort((a, b) => Date.parse(a.SentAt) - Date.parse(b.SentAt))
}

export function unfinishedTurn(messages, stored) {
  const latest = messages.filter((message) => message.SenderType === 'Customer' && message.Metadata?.ClientRequestId).at(-1)
  if (latest?.Metadata.AiProcessingStatus === 'Pending') {
    return { ...(stored?.id === latest.Metadata.ClientRequestId ? stored : {}), id: latest.Metadata.ClientRequestId, content: latest.Content }
  }
  // Never revive a local marker whose completion or cancellation is already in server history.
  if (stored && messages.some((message) => message.Metadata?.ClientRequestId === stored.id
      && ['Completed', 'Cancelled'].includes(message.Metadata.AiProcessingStatus))) return null
  if (stored) return stored
  return null
}
