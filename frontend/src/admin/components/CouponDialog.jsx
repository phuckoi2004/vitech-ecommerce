import { useCallback, useEffect, useRef, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import useAdminQuery, { useAdminLoad } from '../hooks/useAdminQuery.js'
import { getPromotionDirectory } from '../services/promotions.js'
import { createCoupon, deleteCoupon, updateCoupon } from '../services/coupons.js'
import { couponBody, couponError, couponPatch, couponStatus, couponUsage } from '../lib/coupons.js'
import { PROMOTION_TYPES, promotionDateTime, promotionMoney, promotionValue } from '../lib/promotions.js'
import useCouponRefresh, { useCouponClock } from '../hooks/useCouponRefresh.js'
import CouponEditor from './CouponEditor.jsx'
import { PromotionPopupButton } from './PromotionUi.jsx'
import CouponProgram from './CouponProgram.jsx'
import { CouponStatus } from './CouponUi.jsx'
import Modal from './Modal.jsx'
import PromotionAudit from './PromotionAudit.jsx'

function CouponDetails({ row, promotions, now, can, onEdit, onDelete, onClose }) {
  const program = promotions.find((item) => item.PromotionId === row.PromotionId)
  const fields = [
    ['Tên mã giảm giá', row.Name], ['Mã giảm giá', row.Code], ['Chương trình mẹ', program?.Name ?? '—'],
    ['Loại giảm giá', program ? PROMOTION_TYPES[program.DiscountType] : '—'],
    ['Giá trị giảm', program ? promotionValue(program) : '—'],
    ['Đơn hàng tối thiểu', program ? promotionMoney(program.MinOrderValue) : '—'],
    ['Thời gian bắt đầu', program ? promotionDateTime(program.StartDate) : '—'],
    ['Thời gian kết thúc', program ? promotionDateTime(program.EndDate) : '—'],
    ['Giảm tối đa', program?.MaxDiscountAmount == null ? 'Không giới hạn' : promotionMoney(program.MaxDiscountAmount)],
    ['Lượt sử dụng', <span key="usage" className="flex flex-wrap items-center gap-x-3 gap-y-1"><span>{couponUsage(row)}</span>{row.UsageLimit != null && <span className="text-[11px] font-normal text-admin-muted">Còn {Math.max(0, row.UsageLimit - row.UsedCount)} lượt</span>}</span>],
  ]
  return <div className="flex flex-col gap-[15px] text-xs leading-[normal]">
    <dl className="m-0 flex flex-col gap-[15px]">{fields.map(([label, value]) => <div key={label} className="grid grid-cols-[180px_minmax(0,1fr)] items-start gap-x-2"><dt className="font-medium text-admin-muted">{label}</dt><dd className="m-0 font-semibold break-words">{value}</dd></div>)}</dl>
    <div className="flex items-center justify-between gap-3"><span className="font-medium text-admin-muted">Trạng thái</span><CouponStatus value={couponStatus(row, program, now)} /></div>
    <div className="flex flex-col gap-[7px]"><h3 className="m-0 text-xs font-medium text-admin-muted">Mô tả chương trình</h3><p className="m-0 whitespace-pre-wrap break-words">{program?.Description || '—'}</p></div>
    <CouponProgram promotion={program} />
    <PromotionAudit row={row} />
    <div className="flex justify-end gap-2"><PromotionPopupButton secondary onClick={onClose}>Đóng</PromotionPopupButton>{can('delete') && <PromotionPopupButton secondary danger onClick={onDelete}>Xóa mã</PromotionPopupButton>}{can('update') && <PromotionPopupButton onClick={onEdit}>Sửa thông tin</PromotionPopupButton>}</div>
  </div>
}

function CouponMutation({ mode, row, promotions, promotionId, now, can, onBusy, onDone, onClose }) {
  const auth = useInternalAuth(), [busy, setBusy] = useState(false), [failure, setFailure] = useState(null)
  const writing = useRef(false), mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  async function execute(action, message) {
    if (writing.current) return
    writing.current = true; setBusy(true); onBusy(true); setFailure(null)
    try { await auth.withAccessToken(action); if (mounted.current) onDone(message) }
    catch (error) { if (mounted.current) setFailure(error) }
    finally { writing.current = false; if (mounted.current) { setBusy(false); onBusy(false) } }
  }
  function save(form) {
    if (!can(mode === 'new' ? 'create' : 'update')) return
    try {
      const body = row ? couponPatch(form, row) : couponBody(form)
      void execute((token) => row ? Object.keys(body).length ? updateCoupon(token, row.CouponId, body) : Promise.resolve() : createCoupon(token, body), row ? 'Đã cập nhật mã giảm giá.' : 'Đã thêm mã giảm giá.')
    } catch (error) { setFailure(error) }
  }
  if (mode !== 'delete') return <CouponEditor row={row} promotions={promotions} promotionId={promotionId} now={now} busy={busy} failure={failure} onClose={onClose} onSave={save} />
  const inUse = failure?.code === 'coupon_in_use'
  return <div className="flex flex-col gap-[15px] text-xs leading-[normal]">
    <p className="m-0 text-admin-muted">Bạn có chắc muốn xóa mã giảm giá <strong className="font-semibold break-words text-admin-text">{row.Code}</strong> khỏi hệ thống?</p>
    {failure && <p role="alert" className="m-0 rounded-lg bg-red-50 p-3 text-admin-red">{couponError(failure)}</p>}
    <div className="flex justify-end gap-2"><PromotionPopupButton secondary disabled={busy} onClick={onClose}>Hủy</PromotionPopupButton>{!inUse && can('delete') && <PromotionPopupButton secondary danger disabled={busy} onClick={() => void execute((token) => deleteCoupon(token, row.CouponId), 'Đã xóa mã giảm giá.')}>{busy ? 'Đang xóa…' : 'Xóa mã giảm giá'}</PromotionPopupButton>}</div>
  </div>
}

export default function CouponDialog({ mode, couponId, promotionId, can, onClose, onDone, onEdit, onDelete }) {
  const [busy, setBusy] = useState(false)
  const now = useCouponClock()
  const detail = useAdminQuery('/admin/coupons/' + encodeURIComponent(couponId ?? ''), {}, mode !== 'new')
  const directory = useAdminLoad(getPromotionDirectory, mode !== 'delete')
  const refreshDetail = detail.refresh, refreshDirectory = directory.refresh
  const refreshView = useCallback(() => { refreshDetail(); refreshDirectory() }, [refreshDetail, refreshDirectory])
  useCouponRefresh(refreshView, mode === 'view')
  const loading = detail.loading || directory.loading, failure = detail.error || directory.error
  const title = { new: 'Thêm mã giảm giá mới', edit: 'Sửa mã giảm giá', view: 'Chi tiết mã giảm giá', delete: 'Xóa mã giảm giá?' }[mode]
  return <Modal variant="promotion-popup" open title={title} busy={busy} onClose={onClose} className={'rounded-[14px]! [&&:focus-visible]:outline-none! shadow-[0px_8px_24px_0px_rgba(0,0,0,0.14)]! ' + (mode === 'delete' ? 'w-[460px]!' : mode === 'view' ? 'w-[650px]!' : 'w-[680px]!')}>
    {loading ? <LoadingState label="Đang tải mã giảm giá…" /> : failure ? <ErrorState message={failure} onRetry={() => { detail.refresh(); directory.refresh() }} /> : mode !== 'new' && !detail.data ? <p>Không tìm thấy mã giảm giá.</p> : mode === 'view' ? <CouponDetails row={detail.data} promotions={directory.data ?? []} now={now} can={can} onEdit={onEdit} onDelete={onDelete} onClose={onClose} /> : <CouponMutation mode={mode} row={mode === 'new' ? null : detail.data} promotions={directory.data ?? []} promotionId={promotionId} now={now} can={can} onBusy={setBusy} onClose={onClose} onDone={onDone} />}
  </Modal>
}
