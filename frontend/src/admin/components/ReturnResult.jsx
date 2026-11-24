import { returnResultNote } from '../../lib/returns.js'

export default function ReturnResult({ workflow }) {
  const { item, stage, closed, canUpdate, busy, damageAssessment, setDamageAssessment, resultNote, setResultNote, validation } = workflow
  const editable = stage === 'Processing' && !closed && canUpdate
  return <section aria-label="Đánh giá hư hại" className="mt-4 flex flex-col gap-3 rounded-lg border border-admin-border bg-white p-3">
    <h3 className="m-0 text-sm leading-[17px] font-semibold">Kết quả đánh giá đổi trả gửi khách hàng</h3>
    {editable ? <>
      <label className="flex flex-col gap-1.5 text-[11px] font-medium">Tình trạng sản phẩm<textarea aria-label="Tình trạng sản phẩm" required rows={3} maxLength={4000} disabled={busy} value={damageAssessment} onChange={(event) => setDamageAssessment(event.target.value)} className="resize-y rounded-lg border border-admin-border bg-white p-3 text-xs font-normal" /></label>
      <label className="flex flex-col gap-1.5 text-[11px] font-medium">Nội dung kết quả gửi khách hàng<textarea aria-label="Nội dung kết quả gửi khách hàng" required rows={4} maxLength={4000} disabled={busy} value={resultNote} onChange={(event) => setResultNote(event.target.value)} className="resize-y rounded-lg border border-admin-border bg-white p-3 text-xs font-normal" /></label>
      {validation && <p role="alert" className="m-0 text-xs text-admin-red">{validation}</p>}
    </> : item.Status === 'Completed' && item.DamageAssessment ? <>
      <div><strong className="text-[11px]">Tình trạng sản phẩm</strong><p className="mb-0 text-xs whitespace-pre-wrap">{item.DamageAssessment}</p></div>
      <div><strong className="text-[11px]">Nội dung kết quả gửi khách hàng</strong><p className="mb-0 text-xs whitespace-pre-wrap">{returnResultNote(item) || '—'}</p></div>
    </> : <p className="m-0 text-xs text-admin-muted">Chưa ghi nhận kết quả đánh giá.</p>}
  </section>
}
