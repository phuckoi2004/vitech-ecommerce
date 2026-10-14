import Button from './Button.jsx'

// Previous/next pagination for PageResponse lists ({ Items, Total, Page, PageSize }); hidden when everything fits on one page.
export default function Pagination({ page, pageSize, total, onPageChange, disabled = false, label = 'Phân trang', variant, itemLabel = 'sản phẩm' }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (variant === 'admin') {
    const candidates = [...new Set([1, page - 1, page, page + 1, pages].filter((value) => value >= 1 && value <= pages))].sort((a, b) => a - b)
    const buttonClass = 'inline-grid h-8 min-w-[34px] cursor-pointer place-items-center rounded-lg border border-admin-border bg-white px-2 text-[11px] text-admin-muted enabled:hover:bg-admin-soft disabled:cursor-not-allowed disabled:opacity-40'
    return <div className="flex flex-wrap items-center justify-between gap-3 text-[11px] text-admin-muted">
      <span>Hiển thị {total ? (page - 1) * pageSize + 1 : 0}–{Math.min(page * pageSize, total)} trong {total} {itemLabel}</span>
      <nav aria-label={label} className="flex flex-wrap items-center gap-2">
        <button type="button" className={buttonClass} disabled={disabled || page <= 1} aria-label="Trang trước" onClick={() => onPageChange(page - 1)}>‹</button>
        {candidates.map((value, index) => <span key={value} className="flex items-center gap-2">
          {index > 0 && value - candidates[index - 1] > 1 && <span aria-hidden="true">…</span>}
          <button type="button" className={`${buttonClass} aria-[current=page]:border-admin-blue aria-[current=page]:bg-admin-blue aria-[current=page]:text-white`} aria-label={`Trang ${value}`} aria-current={page === value ? 'page' : undefined} disabled={disabled} onClick={() => onPageChange(value)}>{value}</button>
        </span>)}
        <button type="button" className={buttonClass} disabled={disabled || page >= pages} aria-label="Trang sau" onClick={() => onPageChange(page + 1)}>›</button>
      </nav>
    </div>
  }
  if (pages <= 1) return null
  return <nav aria-label={label} className="flex items-center justify-center gap-3 font-sans text-sm">
    <Button variant="secondary" size="sm" onClick={() => onPageChange(page - 1)} disabled={disabled || page <= 1}>Trước</Button>
    <span className="text-muted-600">Trang {page} / {pages}</span>
    <Button variant="secondary" size="sm" onClick={() => onPageChange(page + 1)} disabled={disabled || page >= pages}>Sau</Button>
  </nav>
}
