import Button from './Button.jsx'

// Previous/next pagination for PageResponse lists ({ Items, Total, Page, PageSize }); hidden when everything fits on one page.
export default function Pagination({ page, pageSize, total, onPageChange, disabled = false, label = 'Phân trang' }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (pages <= 1) return null
  return <nav aria-label={label} className="flex items-center justify-center gap-3 font-sans text-sm">
    <Button variant="secondary" size="sm" onClick={() => onPageChange(page - 1)} disabled={disabled || page <= 1}>Trước</Button>
    <span className="text-muted-600">Trang {page} / {pages}</span>
    <Button variant="secondary" size="sm" onClick={() => onPageChange(page + 1)} disabled={disabled || page >= pages}>Sau</Button>
  </nav>
}
