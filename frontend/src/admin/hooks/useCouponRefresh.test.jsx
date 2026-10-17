import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import useCouponRefresh, { useCouponClock } from './useCouponRefresh.js'
import { couponStatus } from '../lib/coupons.js'
import { CouponStatus } from '../components/CouponUi.jsx'

afterEach(() => { cleanup(); vi.useRealTimers() })
function LiveStatus({ row, program }) { return <CouponStatus value={couponStatus(row, program, useCouponClock())} /> }
function Refresh({ refresh, enabled }) { useCouponRefresh(refresh, enabled); return null }

test('computer clock does not override a persisted server status; the next API response updates it', () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-17T00:00:00Z'))
  const row = { Status: 'Active', IsActive: true, UsedCount: 0, UsageLimit: 100 }
  const program = { Status: 'Active', StartDate: '2026-10-01T00:00:00Z', EndDate: '2026-10-17T00:00:00Z' }
  const view = render(<LiveStatus row={row} program={program} />)
  expect(screen.getByText('Đang áp dụng')).toBeInTheDocument()
  act(() => vi.advanceTimersByTime(1000))
  expect(screen.getByText('Đang áp dụng')).toBeInTheDocument()
  view.rerender(<LiveStatus row={{ ...row, Status: 'Ended', IsActive: false }} program={program} />)
  expect(screen.getByText('Hết chương trình')).toBeInTheDocument()
  expect(row.IsActive).toBe(true)
})

test('periodic reads and focus refresh are disabled while an editor is open', () => {
  vi.useFakeTimers()
  const refresh = vi.fn(), view = render(<Refresh refresh={refresh} enabled={false} />)
  act(() => { vi.advanceTimersByTime(60000); window.dispatchEvent(new Event('focus')) })
  expect(refresh).not.toHaveBeenCalled()
  view.rerender(<Refresh refresh={refresh} enabled />)
  act(() => vi.advanceTimersByTime(30000))
  expect(refresh).toHaveBeenCalledTimes(1)
  act(() => window.dispatchEvent(new Event('focus')))
  expect(refresh).toHaveBeenCalledTimes(2)
  view.rerender(<Refresh refresh={refresh} enabled={false} />)
  act(() => vi.advanceTimersByTime(60000))
  expect(refresh).toHaveBeenCalledTimes(2)
})
