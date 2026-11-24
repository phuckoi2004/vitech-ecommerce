export const PREPAYMENT_THRESHOLD = 10_000_000
export const requiresPrepayment = (total) => Number(total) > PREPAYMENT_THRESHOLD
export const prepaymentAmount = (total) => Math.ceil(Number(total) / 5)
export const hasPrepayment = (order) => Number(order?.PrepaymentAmount ?? 0) > 0
export const remainingAmount = (order) => Number(order.RemainingAmount ?? order.TotalAmount)
