// @vitest-environment node
import { expect, test } from 'vitest'
import { purchaseCentsText, purchaseEditPlan, purchaseFormBody, purchaseFormDate, purchaseFormTotal, purchaseLineCents } from './purchase-form.js'

const po = { SupplierId: 's1', Note: 'Ghi chú', CreatedAt: '2026-10-13T17:30:00Z', Items: [{ PurchaseOrderItemId: 'i1', ProductVariantId: 'v1', OrderedQuantity: 2, UnitPrice: '0.10', Note: null }] }

test('totals multiply entered quantities by entered unit prices using exact cents', () => {
  const lines = [{ OrderedQuantity: '3', UnitPrice: '0.10' }, { OrderedQuantity: '2', UnitPrice: '0.20' }]
  expect(purchaseFormTotal(lines)).toBe(70n)
  expect(purchaseCentsText(purchaseFormTotal(lines))).toBe('0.70')
  expect(purchaseLineCents({ OrderedQuantity: '7', UnitPrice: '999999999999.99' })).toBe(699999999999993n)
  expect(purchaseLineCents({ OrderedQuantity: '', UnitPrice: '' })).toBe(0n)
})

test('only entirely untouched placeholders are omitted; date, code, totals and actual received quantities never enter the DTO', () => {
  const form = { SupplierId: 's1', Note: ' ghi chú ', CreatedDate: '2026-10-14', PurchaseOrderCode: 'FAKE', TotalAmount: '1', Items: [{ ProductVariantId: 'v1', OrderedQuantity: '2', UnitPrice: '1.25', ReceivedQuantity: 99, key: 'a' }, { ProductVariantId: '', OrderedQuantity: '', UnitPrice: '', Note: '', key: 'b' }] }
  expect(purchaseFormBody(form)).toEqual({ SupplierId: 's1', Note: 'ghi chú', Items: [{ ProductVariantId: 'v1', OrderedQuantity: 2, UnitPrice: '1.25', Note: null }] })
  expect(() => purchaseFormBody({ ...form, Items: [form.Items[0], { ...form.Items[1], OrderedQuantity: '1' }] })).toThrow('chọn biến thể')
})

test('duplicate variants, invalid quantities, precision and overflowing totals are rejected before saving', () => {
  const body = { SupplierId: 's1', Note: '', Items: [{ ProductVariantId: 'v1', OrderedQuantity: '2', UnitPrice: '1.00' }] }
  expect(() => purchaseFormBody({ ...body, Items: [...body.Items, ...body.Items] })).toThrow('Mỗi biến thể')
  for (const quantity of ['0', '-1', '1.5']) expect(() => purchaseFormBody({ ...body, Items: [{ ...body.Items[0], OrderedQuantity: quantity }] })).toThrow('nguyên dương')
  expect(() => purchaseFormBody({ ...body, Items: [{ ...body.Items[0], UnitPrice: '0.123' }] })).toThrow('2 chữ số')
  expect(() => purchaseFormBody({ ...body, Items: [{ ...body.Items[0], UnitPrice: '9999999999999.99' }] })).toThrow('Tổng tiền vượt')
})

test('unchanged date and line data produce no writes; only the intended quantity/header changes enter patches', () => {
  expect(purchaseEditPlan(po, { SupplierId: 's1', Note: 'Ghi chú', Items: [{ ProductVariantId: 'v1', OrderedQuantity: 2, UnitPrice: '0.1', Note: null }] })).toEqual([])
  expect(purchaseEditPlan(po, { SupplierId: 's1', Note: null, Items: [{ ProductVariantId: 'v1', OrderedQuantity: 3, UnitPrice: '0.10', Note: null }] })).toEqual([{ kind: 'updateItem', id: 'i1', body: { OrderedQuantity: 3 } }, { kind: 'header', body: { Note: null } }])
  expect(purchaseFormDate(po.CreatedAt)).toBe('2026-10-14')
})

test('replacing the only variant adds the new SKU before removing the last existing line', () => {
  expect(purchaseEditPlan(po, { SupplierId: 's1', Note: 'Ghi chú', Items: [{ ProductVariantId: 'v2', OrderedQuantity: 1, UnitPrice: '3.00', Note: null }] }).map((operation) => operation.kind)).toEqual(['addItem', 'removeItem'])
})
