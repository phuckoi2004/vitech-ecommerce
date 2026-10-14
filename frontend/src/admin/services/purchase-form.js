import { getAdminData } from '../../services/api/admin.js'
import { purchaseEditPlan } from '../lib/purchase-form.js'
import { purchaseEditable } from '../lib/purchases.js'
import { addPurchaseItem, removePurchaseItem, updatePurchase, updatePurchaseItem } from './purchases.js'

// The existing backend writes header/items separately. Read the current order before every save/retry,
// retain successful server results, and stop at the first failure instead of reporting a complete save.
export async function savePurchaseDraft(token, id, body, onCheckpoint) {
  let current = await getAdminData(token, '/admin/purchase-orders/' + encodeURIComponent(id))
  if (!purchaseEditable(current)) throw new Error('Phiếu hiện tại không còn được phép sửa. Chỉ sửa phiếu chờ xác nhận hoặc bị từ chối.')
  const operations = purchaseEditPlan(current, body)
  let completed = 0
  try {
    for (const operation of operations) {
      if (operation.kind === 'header') current = await updatePurchase(token, id, operation.body)
      if (operation.kind === 'updateItem') current = await updatePurchaseItem(token, id, operation.id, operation.body)
      if (operation.kind === 'addItem') current = await addPurchaseItem(token, id, operation.body)
      if (operation.kind === 'removeItem') current = await removePurchaseItem(token, id, operation.id)
      completed++; onCheckpoint(current)
    }
    return current
  } catch (error) {
    if (completed) throw new Error('Đã lưu một phần thay đổi (' + completed + '/' + operations.length + ' bước). Chưa cập nhật xong phiếu. Dữ liệu đang nhập được giữ lại; bấm Cập nhật phiếu để tiếp tục. ' + error.message)
    throw error
  }
}
