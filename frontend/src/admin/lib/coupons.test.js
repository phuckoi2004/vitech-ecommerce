import { expect, test } from 'vitest'
import { couponBody, couponForm, couponPatch, couponFilters, filterCoupons, couponUsage, couponValidity, couponStatus } from './coupons.js'

const row = { CouponId: 'c1', PromotionId: 'p1', Code: 'PHONE10', Name: 'Ưu đãi điện thoại', UsageLimit: 10, UsedCount: 7, IsActive: true, Promotion: { Name: 'Tháng 10', Status: 'Active', StartDate: '2000-01-01T00:00:00Z', EndDate: '2100-01-01T00:00:00Z' } }
test('unlimited is null, zero is zero and only editable coupon fields are submitted', () => {
  const form = { ...couponForm(null, 'p1'), Code: ' NEW10 ', Name: ' Ưu đãi ' }
  expect(couponBody(form)).toEqual({ Code: 'NEW10', Name: 'Ưu đãi', PromotionId: 'p1', UsageLimit: null })
  expect(couponBody({ ...form, UsageLimit: '0' }).UsageLimit).toBe(0)
  expect(couponForm(row).UsageLimit).toBe('10')
})
test('usage limits respect consumed counts and PostgreSQL integer bounds', () => {
  for (const limit of ['6', '-1', '1.5', '2147483648', '1e3']) expect(() => couponBody({ ...couponForm(row), UsageLimit: limit }, row.UsedCount)).toThrow()
  expect(couponBody({ ...couponForm(row), UsageLimit: '7' }, 7).UsageLimit).toBe(7)
  expect(couponBody({ ...couponForm(row), UsageLimit: '' }, 7).UsageLimit).toBeNull()
})
test('patch never resets server-owned usage counters and can remove a previous limit', () => {
  expect(couponPatch(couponForm(row), row)).toEqual({})
  expect(couponPatch({ ...couponForm(row), Name: 'Mới', UsageLimit: '' }, row)).toEqual({ Name: 'Mới', UsageLimit: null })
})
test('search, promotion and enabled filters combine without treating enabled as effective eligibility', () => {
  expect(filterCoupons([row], couponFilters(new URLSearchParams('keyword=dien+thoai&promotion=p1&status=active')))).toEqual([row])
  expect(filterCoupons([row], couponFilters(new URLSearchParams('promotion=p2')))).toEqual([])
  expect(couponFilters(new URLSearchParams('status=paused')).status).toBe('')
})

test('usage display is used/limit, preserving real zero values and unlimited quotas', () => {
  expect(couponUsage({ UsedCount: 0, UsageLimit: 100 })).toBe('0/100')
  expect(couponUsage({ UsedCount: 12, UsageLimit: 100 })).toBe('12/100')
  expect(couponUsage({ UsedCount: 0, UsageLimit: 0 })).toBe('0/0')
  expect(couponUsage({ UsedCount: 3, UsageLimit: null })).toBe('3/∞')
})

test('program validity respects inclusive dates and scheduled activation', () => {
  const promotion = { StartDate: '2026-10-01T00:00:00Z', EndDate: '2026-10-31T23:59:59Z', Status: 'Active' }
  expect(couponValidity(promotion, Date.parse(promotion.StartDate))).toBe('current')
  expect(couponValidity(promotion, Date.parse(promotion.EndDate))).toBe('current')
  expect(couponValidity(promotion, Date.parse(promotion.EndDate) + 1)).toBe('expired')
  expect(couponValidity(promotion, Date.parse(promotion.StartDate) - 1)).toBe('upcoming')
  expect(couponValidity({ ...promotion, Status: 'Scheduled' }, Date.parse(promotion.StartDate))).toBe('current')
  expect(couponValidity({ ...promotion, Status: 'Cancelled' }, Date.parse(promotion.StartDate))).toBe('inactive')
})

test('backend status is authoritative regardless of computer clock or legacy IsActive', () => {
  const now = Date.parse('2300-01-01T00:00:00Z')
  expect(couponStatus({ ...row, Status: 'Active', IsActive: false }, row.Promotion, now)).toBe('active')
  expect(couponStatus({ ...row, Status: 'Upcoming' }, row.Promotion)).toBe('upcoming')
  expect(couponStatus({ ...row, Status: 'Exhausted' }, row.Promotion)).toBe('exhausted')
  expect(couponStatus({ ...row, Status: 'Ended' }, row.Promotion)).toBe('expired')
})

test('reaching a finite quota means exhausted; zero quota is exhausted while unlimited is not', () => {
  expect(couponStatus({ ...row, UsedCount: 10 })).toBe('exhausted')
  expect(couponStatus({ ...row, UsedCount: 11 })).toBe('exhausted')
  expect(couponStatus({ ...row, UsageLimit: 0, UsedCount: 0 })).toBe('exhausted')
  expect(couponStatus({ ...row, UsageLimit: null, UsedCount: 1000 })).toBe('active')
  expect(couponStatus({ ...row, UsedCount: 9 })).toBe('active')
})

test('form previews follow parent dates without sending state to the backend', () => {
  const now = Date.parse('2026-10-17T00:00:00Z')
  const scheduled = { ...row.Promotion, Status: 'Scheduled' }
  expect(couponStatus(row, scheduled, now)).toBe('active')
  expect(couponStatus(row, row.Promotion, now)).toBe('active')
  expect(couponStatus(row, { ...row.Promotion, StartDate: '2026-10-18T00:00:00Z' }, now)).toBe('upcoming')
  expect(couponStatus(row, { ...row.Promotion, Status: 'Cancelled' }, now)).toBe('expired')
  expect(scheduled.Status).toBe('Scheduled')
})
