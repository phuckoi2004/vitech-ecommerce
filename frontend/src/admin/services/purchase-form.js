import { updatePurchase } from './purchases.js'

// The server locks the purchase and commits its header and full line set together.
// Repeating the same desired set after a lost response does not append duplicate lines.
export function savePurchaseDraft(token, id, body) {
  return updatePurchase(token, id, body)
}
