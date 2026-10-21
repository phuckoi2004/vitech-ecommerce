import { useEffect, useRef, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import useAdminQuery, { useAdminLoad } from '../hooks/useAdminQuery.js'
import { createPromotion, updatePromotion, deletePromotion, cancelPromotion, getPromotionProducts } from '../services/promotions.js'
import { PROMOTION_MODES, PROMOTION_TYPES, promotionBody, promotionDateTime, promotionForm, promotionMoney, promotionPatch, promotionTargetName, promotionValue, samePromotionTargets } from '../lib/promotions.js'
import { promotionTopCategories } from '../lib/promotion-targets.js'
import Modal from './Modal.jsx'
import PromotionEditor from './PromotionEditor.jsx'
import { PromotionPopupButton, PromotionStatus } from './PromotionUi.jsx'
import PromotionAudit from './PromotionAudit.jsx'
import useCouponRefresh from '../hooks/useCouponRefresh.js'

function PromotionDetails({ row, products, categories, onEdit, onDelete, canEdit, canDelete }) {
  const targets = promotionForm(row)
  const scope = <>{targets.ProductIds.length > 0 && <><span>Sản phẩm: </span><span>{promotionTargetName(targets.ProductIds, products, 'ProductId')}</span></>}{targets.ProductIds.length > 0 && targets.CategoryIds.length > 0 && <br />}{targets.CategoryIds.length > 0 && <><span>Danh mục: </span><span>{promotionTargetName(promotionTopCategories(targets.CategoryIds, categories), categories, 'CategoryId')}</span></>}{!targets.ProductIds.length && !targets.CategoryIds.length && 'Toàn đơn'}</>
  return <div className="flex flex-col gap-[15px] text-xs leading-[normal]">
    <dl className="m-0 flex flex-col gap-[15px]">{[
      ['Cách áp dụng', PROMOTION_MODES[row.ApplyMode ?? 'Coupon']],
      ['Tên chương trình', row.Name], ['Loại giảm giá', PROMOTION_TYPES[row.DiscountType]], ['Giá trị giảm', promotionValue(row)], ['Đơn hàng tối thiểu', promotionMoney(row.MinOrderValue)], ['Giảm tối đa', row.MaxDiscountAmount == null ? 'Không giới hạn' : promotionMoney(row.MaxDiscountAmount)], ['Thời gian bắt đầu', promotionDateTime(row.StartDate)], ['Thời gian kết thúc', promotionDateTime(row.EndDate)], ['Phạm vi áp dụng', scope],
    ].map(([label, value]) => <div key={label} className="grid grid-cols-[180px_minmax(0,1fr)] items-start"><dt className="font-medium text-admin-muted">{label}</dt><dd className="m-0 font-semibold break-words">{value}</dd></div>)}
    </dl>
    <div className="flex items-center justify-between gap-3"><span className="font-medium text-admin-muted">Trạng thái</span><PromotionStatus value={row.Status} /></div>
    <div className="flex flex-col gap-[7px]"><h3 className="m-0 text-xs leading-[normal] font-medium text-admin-muted">Mô tả</h3><p className="m-0 whitespace-pre-wrap break-words">{row.Description || 'Chưa có mô tả.'}</p></div>
    <PromotionAudit row={row} />
    <div className="flex justify-end gap-2">{canDelete && <PromotionPopupButton secondary danger onClick={onDelete}>Xóa</PromotionPopupButton>}{canEdit && <PromotionPopupButton onClick={onEdit}>Sửa thông tin</PromotionPopupButton>}</div>
  </div>
}

function PromotionMutation({ mode, row, products, categories, onBusy, onClose, onDone }) {
  const auth = useInternalAuth(), [busy, setBusy] = useState(false), [failure, setFailure] = useState(null)
  const writing = useRef(false), mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const can = (action) => auth.user.Role === 'Admin' && auth.permissions.includes('promotions:' + action)
  async function save(form) {
    if (writing.current || !can(mode === 'new' ? 'create' : 'update')) return
    let body
    try { body = promotionBody(form) } catch (error) { setFailure(error); return }
    writing.current = true; setBusy(true); onBusy(true); setFailure(null)
    try {
      await auth.withAccessToken(async (token) => {
        if (mode === 'new') return createPromotion(token, body)
        const patch = promotionPatch(form, row)
        const before = promotionForm(row)
        if (!samePromotionTargets(body.ProductIds, before.ProductIds)) patch.ProductIds = body.ProductIds
        if (!samePromotionTargets(body.CategoryIds, before.CategoryIds)) patch.CategoryIds = body.CategoryIds
        // One API request commits metadata and scope together, or rolls everything back.
        if (Object.keys(patch).length) await updatePromotion(token, row.PromotionId, patch)
      })
      if (mounted.current) onDone(mode === 'new' ? 'Đã thêm chương trình khuyến mãi.' : 'Đã cập nhật chương trình khuyến mãi.')
    } catch (error) { if (mounted.current) setFailure(error) }
    finally { writing.current = false; if (mounted.current) { setBusy(false); onBusy(false) } }
  }
  async function remove(cancel = false) {
    if (writing.current || !can(cancel ? 'update' : 'delete')) return
    writing.current = true; setBusy(true); onBusy(true); setFailure(null)
    try {
      await auth.withAccessToken((token) => cancel ? cancelPromotion(token, row.PromotionId) : deletePromotion(token, row.PromotionId))
      if (mounted.current) onDone(cancel ? 'Đã hủy chương trình khuyến mãi.' : 'Đã xóa chương trình khuyến mãi.')
    } catch (error) { if (mounted.current) setFailure(error) }
    finally { writing.current = false; if (mounted.current) { setBusy(false); onBusy(false) } }
  }
  if (mode === 'delete') return <div className="flex flex-col gap-[15px]">
    <p className="m-0 text-xs leading-[normal] text-admin-muted">Bạn có chắc muốn xóa chương trình khuyến mãi này khỏi hệ thống? Thao tác này sẽ xóa dữ liệu của chương trình.</p>
    <p className="sr-only">Chương trình được chọn: {row.Name}</p>
    {failure && <p role="alert" className="m-0 text-xs text-admin-red">{failure.code === 'promotion_in_use' ? 'Chương trình đã có mã giảm giá liên kết nên không được xóa. Bạn có thể hủy chương trình để ngừng áp dụng.' : failure.message}</p>}
    <div className="flex justify-end gap-2"><PromotionPopupButton secondary disabled={busy} onClick={onClose}>Hủy</PromotionPopupButton>{failure?.code === 'promotion_in_use' && row.Status !== 'Cancelled' && can('update') ? <PromotionPopupButton disabled={busy} onClick={() => void remove(true)}>Hủy chương trình</PromotionPopupButton> : <PromotionPopupButton secondary danger disabled={busy} onClick={() => void remove()}>Xóa khuyến mãi</PromotionPopupButton>}</div>
  </div>
  return <PromotionEditor row={row} products={products} categories={categories} busy={busy} error={failure?.message} onClose={onClose} onSave={(form) => void save(form)} />
}

export default function PromotionDialog({ mode, promotionId, onClose, onDone, onEdit, onDelete }) {
  const auth = useInternalAuth(), [busy, setBusy] = useState(false)
  const detail = useAdminQuery('/admin/promotions/' + encodeURIComponent(promotionId ?? ''), {}, mode !== 'new')
  const products = useAdminLoad(getPromotionProducts, mode !== 'delete')
  const categories = useAdminQuery('/categories', { active_only: false }, mode !== 'delete')
  useCouponRefresh(detail.refresh, mode === 'view')
  const title = { new: 'Thêm khuyến mãi mới', view: 'Chi tiết khuyến mãi', edit: 'Sửa thông tin khuyến mãi', delete: 'Xóa khuyến mãi?' }[mode]
  const loading = (mode !== 'new' && detail.loading) || (mode !== 'delete' && (products.loading || categories.loading))
  const error = (mode !== 'new' && detail.error) || (mode !== 'delete' && (products.error || categories.error))
  return <Modal variant="promotion-popup" open title={title} busy={busy} onClose={onClose} className={'rounded-[14px]! [&&:focus-visible]:outline-none! shadow-[0px_8px_24px_0px_rgba(0,0,0,0.14)]! ' + (mode === 'delete' ? 'w-[460px]!' : mode === 'view' ? 'w-[650px]!' : 'w-[680px]!')}>
    {loading ? <LoadingState label="Đang tải thông tin khuyến mãi…" /> : error ? <ErrorState message={error} onRetry={() => { detail.refresh(); products.refresh(); categories.refresh() }} /> : mode === 'view' && detail.data ? <PromotionDetails row={detail.data} products={products.data ?? []} categories={categories.data ?? []} canEdit={auth.user.Role === 'Admin' && auth.permissions.includes('promotions:update')} canDelete={auth.user.Role === 'Admin' && auth.permissions.includes('promotions:delete')} onEdit={onEdit} onDelete={onDelete} /> : (mode === 'new' || detail.data) ? <PromotionMutation mode={mode} row={mode === 'new' ? null : detail.data} products={products.data ?? []} categories={categories.data ?? []} onBusy={setBusy} onClose={onClose} onDone={onDone} /> : <p>Không tìm thấy chương trình khuyến mãi.</p>}
  </Modal>
}
