import { expect, test } from 'vitest'
import { filterShippingMethods, shippingBody, shippingFilters, shippingPagePath } from './shipping-methods.js'

test('search combines accent-insensitive code/name, active status and same-day delivery', () => {
  const rows = [{ Code: 'FAST', Name: 'Giao hàng hỏa tốc', IsActive: true, EstimatedDays: 0 }, { Code: 'OLD', Name: 'Hỏa tốc cũ', IsActive: false, EstimatedDays: 1 }]
  const filter = shippingFilters(new URLSearchParams('keyword=hoa+toc&status=active&days=0&page=2'))
  expect(filterShippingMethods(rows, filter)).toEqual([rows[0]])
  expect(shippingPagePath('edit', 'id/one', new URLSearchParams('keyword=FAST&days=0&dialog=delete&method=old'))).toBe('/admin/shipping-methods/id%2Fone/edit?keyword=FAST&days=0')
  expect(shippingFilters(new URLSearchParams('status=unknown&days=31&page=-2'))).toMatchObject({ status: '', days: '', page: 1 })
})

test('write payload matches shipping schema, keeps whole-VND money and excludes system IDs', () => {
  const form = { ShippingMethodId: 'cannot-send', Code: ' CODE ', Name: ' Trong ngày ', BaseFee: '123456789', EstimatedDays: '0', IsActive: false }
  expect(shippingBody(form)).toEqual({ Code: 'CODE', Name: 'Trong ngày', BaseFee: '123456789', EstimatedDays: 0, IsActive: false })
  // A fee read back from the API ("30000.00") is still a whole amount.
  expect(shippingBody({ ...form, BaseFee: '30000.00' }).BaseFee).toBe('30000.00')
  for (const invalid of [{ Code: ' ' }, { Name: ' ' }, { BaseFee: '-1' }, { BaseFee: '1.123' }, { BaseFee: '123456789.12' }, { BaseFee: '1.5' }, { EstimatedDays: '1.5' }, { EstimatedDays: '31' }, { IsActive: 'false' }]) {
    expect(() => shippingBody({ ...form, ...invalid })).toThrow()
  }
  expect(() => shippingBody({ ...form, BaseFee: '30000.50' })).toThrow('số nguyên VND')
})
