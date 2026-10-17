import { useRef } from 'react'
import { act, renderHook } from '@testing-library/react'
import { expect, test } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import useChatDraft from '../chat-drafts.js'
import ChatDraftProvider from './ChatDraftProvider.jsx'

test('ending a session clears its drafts without remounting children or accepting late updates after signing in again', () => {
  const customer = makeAuth({ role: 'Customer' })
  let auth = customer
  function Wrapper({ children }) {
    return <AuthContext.Provider value={auth}><ChatDraftProvider>{children}</ChatDraftProvider></AuthContext.Provider>
  }
  const { result, rerender } = renderHook(() => ({
    draft: useChatDraft('conversation-1'),
    identity: useRef(Symbol()).current,
  }), { wrapper: Wrapper })
  const identity = result.current.identity
  const oldUpdate = result.current.draft[1]
  act(() => oldUpdate('Bản nháp riêng tư'))
  expect(result.current.draft[0]).toBe('Bản nháp riêng tư')

  auth = makeAuth()
  rerender()
  expect(result.current.draft[0]).toBe('')
  expect(result.current.identity).toBe(identity)

  auth = customer
  rerender()
  expect(result.current.draft[0]).toBe('')
  act(() => oldUpdate('Phản hồi muộn của phiên đã kết thúc'))
  expect(result.current.draft[0]).toBe('')
  act(() => result.current.draft[1]('Bản nháp phiên mới'))
  expect(result.current.draft[0]).toBe('Bản nháp phiên mới')
  expect(result.current.identity).toBe(identity)
})
