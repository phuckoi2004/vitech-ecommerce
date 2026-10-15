import { useEffect, useId, useRef, useState } from 'react'
import Button from '../../../components/shared/Button.jsx'
import RichTextContent from '../../../components/shared/RichTextContent.jsx'
import { productHighlights, productSpecifications } from '../../../lib/product-detail.js'
import ProductModal from './ProductModal.jsx'

function SpecificationTable({ entries }) {
  return <table className="pd-spec-table"><caption className="sr-only">Thông số của phiên bản đang chọn</caption>
    <tbody>{entries.map(([name, value]) => <tr key={name}><th scope="row">{name}</th><td>{value}</td></tr>)}</tbody>
  </table>
}

function ProductDescription({ value }) {
  const [expanded, setExpanded] = useState(false)
  const [overflows, setOverflows] = useState(false)
  const preview = useRef(null)
  const content = useRef(null)
  const heading = useRef(null)
  const contentId = useId()

  useEffect(() => {
    const element = content.current
    function measure() {
      const viewport = preview.current
      if (!viewport || !element.isConnected) return
      const limit = Number.parseFloat(getComputedStyle(viewport).getPropertyValue('--pd-description-preview-height'))
      setOverflows(element.scrollHeight > limit + 1)
    }
    // Measure the rendered HTML, including font sizes and images, rather than estimating from text length.
    const timer = window.setTimeout(measure, 0)
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    observer?.observe(element)
    window.addEventListener('resize', measure)
    element.addEventListener('load', measure, true)
    return () => {
      window.clearTimeout(timer)
      observer?.disconnect()
      window.removeEventListener('resize', measure)
      element.removeEventListener('load', measure, true)
    }
  }, [value])

  function toggle() {
    setExpanded(!expanded)
    if (expanded) heading.current?.scrollIntoView?.({ block: 'start' })
  }

  return <>
    <h2 ref={heading} className="pd-description-heading">Mô tả sản phẩm</h2>
    <div ref={preview} id={contentId} className={`pd-description-body${expanded ? '' : ' is-collapsed'}${overflows ? ' has-overflow' : ''}`}
      onFocusCapture={() => { if (!expanded) setExpanded(true) }}>
      <div ref={content}>
        <RichTextContent value={value} className="pd-description-text"
          fallback={<p className="pd-description-text pd-muted">Đang cập nhật mô tả sản phẩm.</p>} />
      </div>
    </div>
    {overflows && <Button variant="outline" className="pd-description-toggle" onClick={toggle}
      aria-expanded={expanded} aria-controls={contentId}
      aria-label={expanded ? 'Thu gọn mô tả sản phẩm' : 'Xem thêm mô tả sản phẩm'}>
      {expanded ? 'Thu gọn' : 'Xem thêm'}
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
        <path d="m6 9 6 6 6-6" />
      </svg>
    </Button>}
  </>
}

export default function ProductInformation({ product, variant }) {
  const [open, setOpen] = useState(false)
  const specs = productSpecifications(product, variant)
  const highlights = productHighlights(product, variant)

  return <div className="pd-information grid grid-cols-1 gap-5 min-[1000px]:grid-cols-[840fr_430fr]">
    <section className="pd-card pd-description" aria-labelledby="pd-highlights-title">
      <h2 id="pd-highlights-title">Đặc điểm nổi bật</h2>
      <div className="pd-highlights">{highlights.length ? <ul>{highlights.map(([name, value]) => <li key={name}><strong>{name}:</strong> {value}</li>)}</ul>
        : <p>Đang cập nhật đặc điểm sản phẩm.</p>}</div>
      <ProductDescription key={product.ProductId} value={product.Description} />
      {!!highlights.length && <dl className="pd-quick-specs grid grid-cols-5 gap-2.5 max-[600px]:grid-cols-2">
        {highlights.map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}
      </dl>}
    </section>
    <section className="pd-card pd-specifications" aria-labelledby="pd-specifications-title">
      <h2 id="pd-specifications-title">Thông số kỹ thuật</h2>
      {specs.length ? <SpecificationTable entries={specs.slice(0, 10)} /> : <p className="pd-muted">Đang cập nhật thông số kỹ thuật.</p>}
      <Button variant="outline" className="pd-all-specs" disabled={!specs.length} onClick={() => setOpen(true)} aria-haspopup="dialog">Xem đầy đủ thông số</Button>
    </section>
    <ProductModal open={open} title={`Thông số kỹ thuật — ${product.Name}`} onClose={() => setOpen(false)}>
      {variant && <p className="pd-muted">{variant.VariantName}</p>}
      <SpecificationTable entries={specs} />
    </ProductModal>
  </div>
}
