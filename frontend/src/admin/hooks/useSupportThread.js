import { useCallback, useEffect, useRef, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { getSupportConversation, getSupportMessages } from '../services/support.js'
import useSupportPoll from './useSupportPoll.js'

const merge = (left, right) => [...new Map([...left, ...right].map(message => [message.MessageId, message])).values()]
  .sort((a, b) => Date.parse(a.SentAt) - Date.parse(b.SentAt) || a.MessageId.localeCompare(b.MessageId))
const cursor = (direction, message) => ({ [`${direction}_sent_at`]: message.SentAt, [`${direction}_message_id`]: message.MessageId })

export default function useSupportThread(id, reload, visible) {
  const { withAccessToken } = useInternalAuth()
  const cache = useRef([]), exhausted = useRef(false), historyLock = useRef(false), controller = useRef(null)
  const [olderLoading, setOlderLoading] = useState(false), [olderError, setOlderError] = useState('')
  useEffect(() => () => controller.current?.abort(), [])
  const load = useCallback(async (token, signal) => {
    const last = cache.current.at(-1)
    const [conversation, page] = await Promise.all([
      getSupportConversation(token, id, signal),
      getSupportMessages(token, id, last ? { ...cursor('after', last), limit: 100 } : { latest: true }, signal),
    ])
    signal.throwIfAborted()
    if (!last) exhausted.current = page.Items.length < 50
    cache.current = merge(cache.current, page.Items)
    return { ...conversation, Messages: cache.current, HasOlder: !exhausted.current && cache.current.length < page.Total }
  }, [id])
  const state = useSupportPoll(load, reload, visible)
  async function loadOlder() {
    const first = cache.current[0]
    if (!first || historyLock.current) return
    const request = new AbortController()
    controller.current = request; historyLock.current = true
    setOlderLoading(true); setOlderError('')
    try {
      const page = await withAccessToken(token => getSupportMessages(token, id, cursor('before', first), request.signal))
      request.signal.throwIfAborted()
      cache.current = merge(page.Items, cache.current)
      exhausted.current = page.Items.length < 50
      state.refresh()
      return page.Items.length
    } catch (error) { if (!request.signal.aborted) setOlderError(error.message); return 0 }
    finally {
      historyLock.current = false
      if (!request.signal.aborted) setOlderLoading(false)
    }
  }
  return { ...state, loadOlder, olderLoading, olderError }
}
