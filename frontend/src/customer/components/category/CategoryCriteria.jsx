import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { categoryPath } from '../../routes/paths.js'
import { ChevronDownIcon } from '../icons.jsx'

// Figma "Full Filters" and its "Filter Overlay/..." panels. "Bộ lọc" lists every criterion; each criterion chip opens
// its own panel under it. Options of one criterion combine with OR, criteria with AND (GET /products). The panel
// closes on "Đóng", Escape or a click outside; options stay reachable with Tab right after their chip.
function Panel({ id, title, onClose, children }) {
  const panel = useRef(null)
  // Opens under its chip, moved left when a chip near the right edge would push it off screen.
  useLayoutEffect(() => {
    const element = panel.current
    const overflow = element.getBoundingClientRect().right - (document.documentElement.clientWidth - 16)
    if (overflow > 0) element.style.left = `${-overflow}px`
  }, [])
  return <div className="catalog-overlay" id={id} role="dialog" aria-label={title} ref={panel}>
    <div className="catalog-overlay-header">
      <h3>{title}</h3>
      <button type="button" className="catalog-chip is-small" onClick={onClose}>Đóng</button>
    </div>
    <div className="catalog-overlay-options">{children}</div>
  </div>
}

function OptionButton({ pressed, onClick, children }) {
  return <button type="button" className="catalog-option" aria-pressed={pressed} onClick={onClick}>{children}</button>
}

export default function CategoryCriteria({ listing, priceRanges, facets, needs, currentCategoryId, onChange, onClear, active }) {
  const [open, setOpen] = useState(null)
  const root = useRef(null)
  const baseId = useId()
  const panelId = (key) => `${baseId}-${key}`

  useEffect(() => {
    if (!open) return undefined
    const outside = (event) => { if (!root.current?.querySelector('.catalog-criterion.is-open')?.contains(event.target)) setOpen(null) }
    const escape = (event) => {
      if (event.key !== 'Escape') return
      setOpen(null)
      root.current?.querySelector('.catalog-criterion.is-open > button')?.focus()
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape) }
  }, [open])

  const toggleSpec = (key, value) => {
    const spec = `${key}:${value}`
    onChange({ specs: listing.specs.includes(spec) ? listing.specs.filter((item) => item !== spec) : [...listing.specs, spec] })
  }
  const selectedIn = (key) => listing.specs.filter((spec) => spec.startsWith(`${key}:`)).length

  const criteria = [
    ...(priceRanges.length ? [{ key: 'price', label: 'Xem theo giá', count: listing.price ? 1 : 0 }] : []),
    ...(needs.length ? [{ key: 'needs', label: 'Nhu cầu sử dụng', count: 0 }] : []),
    ...facets.map((facet) => ({ key: `spec-${facet.Key}`, label: facet.Label, count: selectedIn(facet.Key), facet })),
  ]

  function panel(criterion) {
    const close = () => setOpen(null)
    if (criterion.key === 'price') {
      return <Panel id={panelId('price')} title="Xem theo giá" onClose={close}>
        {priceRanges.map((range) => <OptionButton key={range.Value} pressed={listing.price === range.Value}
          onClick={() => onChange({ price: listing.price === range.Value ? '' : range.Value })}>{range.Label}</OptionButton>)}
      </Panel>
    }
    if (criterion.key === 'needs') {
      return <Panel id={panelId('needs')} title="Nhu cầu sử dụng" onClose={close}>
        {needs.map((item) => <Link key={item.CategoryId} className="catalog-option" to={categoryPath(item.Slug)}
          aria-current={item.CategoryId === currentCategoryId ? 'page' : undefined} onClick={close}>{item.Name}</Link>)}
      </Panel>
    }
    return <Panel id={panelId(criterion.key)} title={criterion.label} onClose={close}>
      {criterion.facet.Options.map((option) => <OptionButton key={option.Value}
        pressed={listing.specs.includes(`${criterion.facet.Key}:${option.Value}`)}
        onClick={() => toggleSpec(criterion.facet.Key, option.Value)}>{option.Label}</OptionButton>)}
    </Panel>
  }

  return <section className="catalog-card" aria-labelledby={`${baseId}-title`}>
    <h2 id={`${baseId}-title`}>Chọn theo tiêu chí</h2>
    <ul className="catalog-criteria" ref={root}>
      {criteria.length > 0 && <li className={`catalog-criterion${open === 'all' ? ' is-open' : ''}`}>
        <button type="button" className="catalog-chip is-outline" aria-expanded={open === 'all'} aria-controls={panelId('all')}
          onClick={() => setOpen(open === 'all' ? null : 'all')}>Bộ lọc</button>
        {open === 'all' && <Panel id={panelId('all')} title="Bộ lọc đầy đủ" onClose={() => setOpen(null)}>
          {criteria.map((criterion) => <button key={criterion.key} type="button" className="catalog-option"
            onClick={() => setOpen(criterion.key)}>{criterion.label}{criterion.count > 0 && ` (${criterion.count})`}</button>)}
        </Panel>}
      </li>}
      <li><button type="button" className="catalog-chip" aria-pressed={listing.inStock}
        onClick={() => onChange({ inStock: !listing.inStock })}>Sẵn hàng</button></li>
      <li><button type="button" className="catalog-chip" aria-pressed={listing.newArrivals}
        onClick={() => onChange({ newArrivals: !listing.newArrivals })}>Hàng mới về</button></li>
      {criteria.map((criterion) => <li key={criterion.key} className={`catalog-criterion${open === criterion.key ? ' is-open' : ''}`}>
        <button type="button" className={`catalog-chip${criterion.count ? ' is-selected' : ''}`} aria-expanded={open === criterion.key}
          aria-controls={panelId(criterion.key)} onClick={() => setOpen(open === criterion.key ? null : criterion.key)}>
          {criterion.label}{criterion.count > 1 && ` (${criterion.count})`}<ChevronDownIcon className="size-4" />
        </button>
        {open === criterion.key && panel(criterion)}
      </li>)}
      {active && <li><button type="button" className="catalog-clear" onClick={onClear}>Xóa bộ lọc</button></li>}
    </ul>
  </section>
}
