import { getAdminData } from '../../services/api/admin.js'
import { request } from '../../services/api/client.js'
import { getPromotionDirectory } from './promotions.js'
import { purchaseReadBatch } from './purchases.js'

const couponPath = (id) => '/admin/coupons/' + encodeURIComponent(id)

// The existing API lists coupons within a promotion. Read every promotion page and
// join its coupons; reject failed reads rather than showing incomplete counts.
export async function getCouponDirectory(token, signal) {
  const promotions = await getPromotionDirectory(token, signal)
  const groups = await purchaseReadBatch(promotions, async (promotion) => {
    const rows = await getAdminData(token, '/admin/promotions/' + encodeURIComponent(promotion.PromotionId) + '/coupons', {}, signal)
    return rows.map((row) => ({ ...row, Promotion: promotion }))
  }, signal)
  const items = [...new Map(groups.flat().map((row) => [row.CouponId, row])).values()]
    .sort((left, right) => new Date(right.CreatedAt) - new Date(left.CreatedAt) || left.Code.localeCompare(right.Code, 'vi'))
  return { promotions, items }
}

export const createCoupon = (token, body) => request('/admin/coupons', { method: 'POST', accessToken: token, body })
export const updateCoupon = (token, id, body) => request(couponPath(id), { method: 'PATCH', accessToken: token, body })
export const deleteCoupon = (token, id) => request(couponPath(id), { method: 'DELETE', accessToken: token })
