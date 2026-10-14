// @vitest-environment node
import { expect, test } from 'vitest'
import { filterPurchases, purchaseCreateBody, purchaseCsv, purchaseFilters, purchaseReceiveBody } from './purchases.js'

const variants = [{ ProductVariantId: 'v1', ProductId: 'p1', Name: 'Điện thoại', VariantName: 'Đen', Sku: 'DEN-01', IsSerialTracked: true }, { ProductVariantId: 'v2', ProductId: 'p1', Name: 'Điện thoại', VariantName: 'Trắng', Sku: 'TRANG-01', IsSerialTracked: false }]
const po = { PurchaseOrderId: 'po1', PurchaseOrderCode: 'PN-THAT', SupplierId: 's1', CreatedByUserId: 'u1', CreatedAt: '2026-10-13T17:30:00Z', Status: 'Receiving', TotalAmount: '200.00', Items: [{ PurchaseOrderItemId: 'i1', ProductVariantId: 'v1', OrderedQuantity: 2, ReceivedQuantity: 1 }] }

test('date filters use the same Vietnam calendar day as the displayed order date, inclusively', () => {
  const filter = purchaseFilters(new URLSearchParams('from=2026-10-14&to=2026-10-14&keyword=dien+thoai&product=p1&supplier=s1'))
  expect(filterPurchases([po], filter, variants)).toEqual([po])
  expect(filterPurchases([po], { ...filter, to: '2026-10-13' }, variants)).toEqual([])
  expect(purchaseFilters(new URLSearchParams('from=2026-99-99&to=2026-02-30&page=-1'))).toMatchObject({ from: '', to: '', page: 1 })
})

test('processed history includes backend receiving/completed/closed/cancelled states and excludes pending', () => {
  const rows = ['Pending', 'Approved', 'Rejected', 'Receiving', 'Completed', 'Closed', 'Cancelled'].map((Status) => ({ ...po, Status }))
  expect(filterPurchases(rows, { status: 'history' }, variants).map((row) => row.Status)).toEqual(['Approved', 'Rejected', 'Receiving', 'Completed', 'Closed', 'Cancelled'])
})

test('create DTO sends variant IDs, quantities and exact decimal strings without server-owned fields', () => {
  const body = purchaseCreateBody({ SupplierId: 's1', Note: ' ghi chú ', Items: [{ ProductVariantId: 'v1', OrderedQuantity: '2', UnitPrice: '123456789.12', Note: ' ' }, { ProductVariantId: 'v2', OrderedQuantity: '1', UnitPrice: '0', Note: 'màu trắng' }] })
  expect(body).toEqual({ SupplierId: 's1', Note: 'ghi chú', Items: [{ ProductVariantId: 'v1', OrderedQuantity: 2, UnitPrice: '123456789.12', Note: null }, { ProductVariantId: 'v2', OrderedQuantity: 1, UnitPrice: '0', Note: 'màu trắng' }] })
  expect(() => purchaseCreateBody({ SupplierId: 's1', Note: '', Items: [body.Items[0], body.Items[0]] })).toThrow('Mỗi biến thể')
})

test('receiving validates remaining quantities, tracking rules and exact serial case without changing placed quantities', () => {
  expect(purchaseReceiveBody(po, { i1: { Quantity: '1', SerialNumbers: 'SN-THAT' } }, variants, ' lần nhận ')).toEqual({ Items: [{ PurchaseOrderItemId: 'i1', Quantity: 1, SerialNumbers: ['SN-THAT'] }], Note: 'lần nhận' })
  expect(() => purchaseReceiveBody(po, { i1: { Quantity: '2', SerialNumbers: 'A\nB' } }, variants, '')).toThrow('không vượt số còn thiếu')
  expect(() => purchaseReceiveBody(po, { i1: { Quantity: '1', SerialNumbers: '' } }, variants, '')).toThrow('đúng một Serial/IMEI')
  expect(() => purchaseReceiveBody({ ...po, Items: [{ ...po.Items[0], ProductVariantId: 'v2' }] }, { i1: { Quantity: '1', SerialNumbers: 'A' } }, variants, '')).toThrow('không quản lý Serial/IMEI')
  expect(() => purchaseReceiveBody(po, {}, variants, '')).toThrow('ít nhất một sản phẩm thực nhận')
})

test('CSV exports every supplied result with UTF-8 BOM, escaped quotes and spreadsheet-formula protection', () => {
  const rows = Array.from({ length: 7 }, (_, index) => ({ ...po, PurchaseOrderCode: 'PN-' + index }))
  const text = purchaseCsv(rows, { s1: '=HYPERLINK("x")' }, { u1: 'Người thật' })
  expect(text.startsWith('\uFEFF')).toBe(true)
  expect(text.split('\r\n')).toHaveLength(8)
  expect(text).toContain('PN-6')
  expect(text).toContain('"\'=HYPERLINK(""x"")"')
  expect(text).toContain('"200.00"')
})
