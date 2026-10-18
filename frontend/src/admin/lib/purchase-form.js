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
