import { expect, test } from 'vitest'
import { filterPromotions, localPromotionTime, promotionBody, promotionFilters, promotionForm, promotionPatch } from './promotions.js'

const row = { PromotionId: 'p1', Name: 'Ưu đãi điện thoại', Description: null, DiscountType: 'Percentage', DiscountValue: '10.00', MinOrderValue: '0.00', MaxDiscountAmount: null, StartDate: '2026-10-01T00:00:00.123Z', EndDate: '2026-10-31T23:59:59.123Z', Status: 'Scheduled', Products: [{ ProductId: 'parent' }], Categories: [] }
test('combined filters search accents and preserve only known types/status and valid page', () => {
  const filter = promotionFilters(new URLSearchParams('keyword=uu+dai+dien+thoai&type=Percentage&status=Scheduled&page=3'))
  expect(filterPromotions([row, { ...row, PromotionId: 'p2', Status: 'Active' }], filter)).toEqual([row])
  expect(promotionFilters(new URLSearchParams('status=nope&type=nope&page=-1')).page).toBe(1)
  expect(promotionFilters(new URLSearchParams('status=nope&type=nope')).status).toBe('')
})
test('creation serializes existing fields, exact decimal money, local timestamps, and parent product scope', () => {
  const form = { ...promotionForm(row), Name: ' Ưu đãi ', DiscountValue: '12.34', MaxDiscountAmount: '', ProductIds: ['parent', 'parent'] }
  const body = promotionBody(form)
  expect(body).toMatchObject({ Name: 'Ưu đãi', DiscountValue: '12.34', MaxDiscountAmount: null, ProductIds: ['parent'], CategoryIds: [] })
  expect(new Date(body.StartDate).getTime()).toBe(new Date(form.StartDate).getTime())
  expect(body).not.toHaveProperty('PromotionId')
  expect(body).not.toHaveProperty('CreatedByUserId')
  expect(body).not.toHaveProperty('CouponId')
})
test.each([{ DiscountValue: '100.01' }, { DiscountValue: '-1' }, { MinOrderValue: '1.001' }, { EndDate: '2025-01-01T00:00:00' }, { StartDate: '' }])('invalid promotion conditions are rejected: %j', (overrides) => {
  expect(() => promotionBody({ ...promotionForm(row), ...overrides })).toThrow()
})
test('PATCH does not resend unchanged timestamps or locked terms while editing an Active program', () => {
  const active = { ...row, Status: 'Active' }
  expect(promotionPatch({ ...promotionForm(active), Name: 'Tên mới', DiscountValue: '20' }, active)).toEqual({ Name: 'Tên mới' })
  expect(promotionPatch(promotionForm(row), row)).toEqual({})
  expect(localPromotionTime(row.StartDate)).toMatch(/^2026-10-\d{2}T\d{2}:\d{2}:\d{2}$/)
})
