import { WARRANTY_RESULTS, warrantyResultLabel } from '../lib/warranties.js'

export default function WarrantyResult({ workflow }) {
  const { item, stage, closed, canUpdate, busy, resultType, setResultType, resultNote, setResultNote, validation } = workflow
  const editable = stage === 'Repairing' && !closed && canUpdate
  return <section aria-label="Kết quả bảo hành" className="mt-4 flex flex-col gap-3 rounded-lg border border-admin-border bg-white p-3">
    <h3 className="m-0 text-sm leading-[17px] font-semibold">Kết quả bảo hành gửi khách hàng</h3>
    {editable ? <>
      <label className="flex flex-col gap-1.5 text-[11px] font-medium">Kết quả bảo hành <span className="sr-only">bắt buộc</span><select aria-label="Kết quả bảo hành" required disabled={busy} value={resultType} onChange={(event) => setResultType(event.target.value)} className="h-10 rounded-lg border border-admin-border bg-white px-3 text-xs"><option value="" disabled hidden />{WARRANTY_RESULTS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label className="flex flex-col gap-1.5 text-[11px] font-medium">Nội dung kết quả gửi khách hàng<textarea aria-label="Nội dung kết quả gửi khách hàng" required rows={4} maxLength={4000} disabled={busy} value={resultNote} onChange={(event) => setResultNote(event.target.value)} className="resize-y rounded-lg border border-admin-border bg-white p-3 text-xs font-normal" /></label>
      {validation && <p role="alert" className="m-0 text-xs text-admin-red">{validation}</p>}
    </> : item.ResultApprovedAt && item.ResultType ? <><strong className="text-xs">{warrantyResultLabel(item.ResultType)}</strong><p className="m-0 text-xs whitespace-pre-wrap">{item.ResultNote || '—'}</p></> : <p className="m-0 text-xs text-admin-muted">Chưa ghi nhận kết quả.</p>}
  </section>
}
