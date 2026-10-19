import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { getAdminData } from '../../services/api/admin.js'
import PurchaseForm from '../components/PurchaseForm.jsx'
import { PurchaseButton } from '../components/PurchaseUi.jsx'
import useAdminQuery, { useAdminLoad } from '../hooks/useAdminQuery.js'
import { purchaseEditable, purchaseListSearch } from '../lib/purchases.js'
import { savePurchaseDraft } from '../services/purchase-form.js'
import { createPurchase, getPurchaseVariants, purchaseReadBatch } from '../services/purchases.js'
import { getSupplierDirectory } from '../services/suppliers.js'

export default function PurchaseFormPage() {
  const { purchaseId } = useParams()
  const edit = Boolean(purchaseId)
  const auth = useInternalAuth(), navigate = useNavigate()
  const [params] = useSearchParams()
  const allowed = auth.permissions.includes('purchases:view') && auth.permissions.includes(edit ? 'purchases:update' : 'purchases:create')
  const detail = useAdminQuery('/admin/purchase-orders/' + encodeURIComponent(purchaseId ?? ''), {}, edit && allowed)
  const suppliers = useAdminLoad(getSupplierDirectory, allowed && auth.permissions.includes('suppliers:view'))
  const catalog = useAdminLoad(getPurchaseVariants, allowed && auth.permissions.includes('products:view'))
  const missing = JSON.stringify((detail.data?.Items ?? []).map((item) => item.ProductVariantId).filter((id) => !catalog.data?.some((variant) => variant.ProductVariantId === id)))
  const loadHistoric = useCallback(async (token, signal) => {
    const variants = await purchaseReadBatch(JSON.parse(missing), (id) => getAdminData(token, '/admin/variants/' + encodeURIComponent(id), {}, signal), signal)
    const products = await purchaseReadBatch([...new Set(variants.map((variant) => variant.ProductId))], (id) => getAdminData(token, '/admin/products/' + encodeURIComponent(id), {}, signal), signal)
    return variants.map((variant) => ({ ...variant, Name: products.find((product) => product.ProductId === variant.ProductId)?.Name }))
  }, [missing])
  const historic = useAdminLoad(loadHistoric, allowed && auth.permissions.includes('products:view') && Boolean(detail.data && catalog.data) && missing !== '[]')
  const variants = { data: [...(catalog.data ?? []), ...(historic.data ?? [])], loading: catalog.loading || historic.loading, error: catalog.error || historic.error, refresh: () => { catalog.refresh(); historic.refresh() } }
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const writing = useRef(false), mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const listPath = '/admin/purchases' + purchaseListSearch(params)
  const detailPath = edit ? '/admin/purchases/' + encodeURIComponent(purchaseId) + purchaseListSearch(params) : listPath
  async function save(body) {
    if (!allowed || writing.current) return
    writing.current = true; setBusy(true); setError('')
    try {
      const result = await auth.withAccessToken((token) => edit ? savePurchaseDraft(token, purchaseId, body) : createPurchase(token, body))
      if (mounted.current) navigate('/admin/purchases/' + encodeURIComponent(result.PurchaseOrderId) + purchaseListSearch(params), { replace: true, state: { purchaseNotice: edit ? 'Đã cập nhật phiếu nhập.' : 'Đã tạo phiếu nhập.' } })
    } catch (failure) { if (mounted.current) setError(failure.message) }
    finally { writing.current = false; if (mounted.current) setBusy(false) }
  }
  return <section aria-label={edit ? 'Sửa phiếu nhập' : 'Tạo phiếu nhập'} className="-mt-1 flex min-w-0 flex-col gap-3.5">
    <div className="flex items-center justify-between"><div><h2 className="m-0 text-xl leading-6 font-bold">{edit ? 'Sửa phiếu nhập' + (detail.data ? ' ' + detail.data.PurchaseOrderCode : '') : 'Tạo phiếu nhập mới'}</h2><p className="mt-[3px] mb-0 text-[11px] leading-[13px] text-admin-muted">Nhập thông tin nhà cung cấp và danh sách sản phẩm cần nhập</p></div><PurchaseButton secondary disabled={busy} onClick={() => navigate(listPath)}>← Danh sách phiếu nhập</PurchaseButton></div>
    {edit && detail.loading ? <LoadingState label="Đang tải phiếu nhập…" /> : edit && detail.error ? <ErrorState title="Không tải được phiếu nhập" message={detail.error} onRetry={detail.refresh} /> : edit && detail.data && !purchaseEditable(detail.data) ? <p role="status" className="m-0 rounded-xl border border-admin-border p-4 text-xs text-admin-muted">Phiếu hiện tại không còn được phép sửa. Chỉ sửa phiếu chờ xác nhận hoặc bị từ chối.</p> : <>
      {(!auth.permissions.includes('suppliers:view') || !auth.permissions.includes('products:view')) && <p role="alert" className="m-0 text-xs text-admin-red">Bạn cần quyền xem nhà cung cấp và sản phẩm để lập hoặc sửa phiếu nhập.</p>}
      {suppliers.error && <ErrorState title="Chưa tải được nhà cung cấp" message={suppliers.error} onRetry={suppliers.refresh} className="py-2" />}{variants.error && <ErrorState title="Chưa tải được sản phẩm" message={variants.error} onRetry={variants.refresh} className="py-2" />}
      {allowed && <PurchaseForm po={edit ? detail.data : null} role={auth.user.Role} suppliers={suppliers} variants={variants} busy={busy} error={error} blocked={!auth.permissions.includes('suppliers:view') || !auth.permissions.includes('products:view')} onError={setError} onSave={save} onCancel={() => navigate(detailPath)} />}
    </>}
  </section>
}
