import { formatDate } from '../../lib/format.js'
import { purchaseCreateBody } from './purchases.js'

export const purchaseFormDate = (value) => formatDate(value).split('/').reverse().join('-')
export const emptyPurchaseLine = (key) => ({ key, ProductVariantId: '', OrderedQuantity: '', UnitPrice: '', Note: '' })
export const purchaseFormDraft = (po) => ({ SupplierId: po?.SupplierId ?? '', CreatedDate: purchaseFormDate(po?.CreatedAt ?? new Date()), Note: po?.Note ?? '', Items: po ? po.Items.map((item) => ({ ...item, key: item.PurchaseOrderItemId })) : [emptyPurchaseLine('new-0'), emptyPurchaseLine('new-1')] })

// Integer cents keep quantity × price exact, including large numeric(15,2) amounts.
export function purchaseLineCents(line) {
  const quantity = String(line.OrderedQuantity).trim(), price = String(line.UnitPrice).trim()
  if (!/^\d{1,10}$/.test(quantity) || !/^\d{1,13}(\.\d{1,2})?$/.test(price)) return 0n
  const [whole, fraction = ''] = price.split('.')
  return BigInt(quantity) * (BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0')))
}
export function purchaseCentsText(cents) { return (cents / 100n).toString() + '.' + (cents % 100n).toString().padStart(2, '0') }
export function purchaseFormTotal(lines) { return lines.reduce((total, line) => total + purchaseLineCents(line), 0n) }

export function purchaseFormBody(form) {
  // Leave an untouched placeholder row out of the request; partially filled rows must validate.
  const Items = form.Items.filter((item) => item.ProductVariantId || String(item.OrderedQuantity).trim() || String(item.UnitPrice).trim() || item.Note?.trim())
  const body = purchaseCreateBody({ ...form, Items })
  if (purchaseFormTotal(Items) > 999999999999999n) throw new Error('Tổng tiền vượt giới hạn lưu trữ 9.999.999.999.999,99đ.')
  return body
}

export function purchaseEditPlan(po, body) {
  const byVariant = new Map(po.Items.map((item) => [item.ProductVariantId, item]))
  const wanted = new Set(body.Items.map((item) => item.ProductVariantId))
  const operations = []
  // Update retained lines, remove redundant lines while retaining one, then add new variants.
  // Each result is saved as a checkpoint so a retry never repeats a successful add/delete.
  for (const line of body.Items) {
    const existing = byVariant.get(line.ProductVariantId)
    if (!existing) continue
    const patch = {}
    if (existing.OrderedQuantity !== line.OrderedQuantity) patch.OrderedQuantity = line.OrderedQuantity
    if (purchaseLineCents({ ...existing, OrderedQuantity: 1 }) !== purchaseLineCents({ ...line, OrderedQuantity: 1 })) patch.UnitPrice = line.UnitPrice
    if ((existing.Note ?? '').trim() !== (line.Note ?? '')) patch.Note = line.Note
    if (Object.keys(patch).length) operations.push({ kind: 'updateItem', id: existing.PurchaseOrderItemId, body: patch })
  }
  const removals = po.Items.filter((item) => !wanted.has(item.ProductVariantId))
  // When replacing every variant, retain one old line until at least one new line exists.
  const deferred = removals.length === po.Items.length ? removals.pop() : null
  for (const item of removals) operations.push({ kind: 'removeItem', id: item.PurchaseOrderItemId })
  for (const line of body.Items) if (!byVariant.has(line.ProductVariantId)) operations.push({ kind: 'addItem', body: line })
  if (deferred) operations.push({ kind: 'removeItem', id: deferred.PurchaseOrderItemId })
  const header = {}
  if (po.SupplierId !== body.SupplierId) header.SupplierId = body.SupplierId
  if ((po.Note ?? '').trim() !== (body.Note ?? '')) header.Note = body.Note
  if (Object.keys(header).length) operations.push({ kind: 'header', body: header })
  return operations
}
