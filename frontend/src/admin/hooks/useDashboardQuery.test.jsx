import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { useDashboardLoad } from './useDashboardQuery.js'

let auth, hidden
const wrapper = ({ children }) => <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>
const flush = () => act(async () => {})
beforeEach(() => {
  vi.useFakeTimers()
  auth = makeAuth({ role: 'Admin' })
  hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

test('minute refresh retains data and never overlaps in-flight requests', async () => {
  let finish
  const load = vi.fn().mockResolvedValueOnce({ Total: 1 }).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const { result } = renderHook(() => useDashboardLoad(load), { wrapper })
  await flush()
  expect(result.current.data.Total).toBe(1)
  await act(() => vi.advanceTimersByTimeAsync(60000))
  expect(load).toHaveBeenCalledTimes(2)
  expect(result.current.data.Total).toBe(1)
  expect(result.current.loading).toBe(false)
  expect(result.current.refreshing).toBe(true)
  await act(async () => { window.dispatchEvent(new Event('focus')); document.dispatchEvent(new Event('visibilitychange')) })
  expect(load).toHaveBeenCalledTimes(2)
  await act(async () => finish({ Total: 2 }))
  expect(result.current.data.Total).toBe(2)
  expect(result.current.refreshing).toBe(false)
})

test('hidden pages pause and returning during the same day refreshes once', async () => {
  const load = vi.fn().mockResolvedValue({ Total: 1 })
  renderHook(() => useDashboardLoad(load), { wrapper })
  await flush()
  hidden.mockReturnValue(true)
  await act(() => vi.advanceTimersByTimeAsync(120000))
  expect(load).toHaveBeenCalledTimes(1)
  hidden.mockReturnValue(false)
  await act(async () => { document.dispatchEvent(new Event('visibilitychange')); window.dispatchEvent(new Event('focus')) })
  expect(load).toHaveBeenCalledTimes(2)
})

test('financial queries refresh on focus without running an interval', async () => {
  const load = vi.fn().mockResolvedValue({ Revenue: '1000' })
  renderHook(() => useDashboardLoad(load, true, 0), { wrapper })
  await flush()
  await act(() => vi.advanceTimersByTimeAsync(120000))
  expect(load).toHaveBeenCalledTimes(1)
  await act(async () => window.dispatchEvent(new Event('focus')))
  expect(load).toHaveBeenCalledTimes(2)
})

test('changing the query aborts the old request and ignores its late response', async () => {
  let finish, signal
  const oldLoad = vi.fn((token, currentSignal) => { signal = currentSignal; return new Promise((resolve) => { finish = resolve }) })
  const newLoad = vi.fn().mockResolvedValue({ Total: 2 })
  const { result, rerender, unmount } = renderHook(({ load }) => useDashboardLoad(load), { initialProps: { load: oldLoad }, wrapper })
  rerender({ load: newLoad })
  await flush()
  expect(signal.aborted).toBe(true)
  await act(async () => finish({ Total: 999 }))
  expect(result.current.data.Total).toBe(2)
  unmount()
  await act(() => vi.advanceTimersByTimeAsync(120000))
  expect(newLoad).toHaveBeenCalledTimes(1)
})

test('failures preserve the last success as stale data and expose the error', async () => {
  const load = vi.fn().mockResolvedValueOnce({ Total: 3 }).mockRejectedValueOnce(new Error('Mất kết nối'))
  const { result } = renderHook(() => useDashboardLoad(load), { wrapper })
  await flush()
  await act(() => vi.advanceTimersByTimeAsync(60000))
  expect(result.current.data.Total).toBe(3)
  expect(result.current.error).toBe('Mất kết nối')
})

test('disabled queries never send requests', async () => {
  const load = vi.fn()
  const { result } = renderHook(() => useDashboardLoad(load, false), { wrapper })
  await flush()
  await act(() => vi.advanceTimersByTimeAsync(120000))
  expect(load).not.toHaveBeenCalled()
  expect(result.current.loading).toBe(false)
})
