import { useId, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import useApiData from '../../hooks/useApiData.js'
import { getSearchSuggestions } from '../../lib/catalog-api.js'
import { formatMoney } from '../../lib/format.js'
import { SEARCH_PATH, categoryPath, productPath } from '../routes/paths.js'
import StoreImage from './StoreImage.jsx'
import './SearchBox.css'

const searchPath = (text) => `${SEARCH_PATH}?q=${encodeURIComponent(text)}`
const HISTORY_KEY = 'vietech:search-history'
const HISTORY_SIZE = 8

// "Lịch sử tìm kiếm": this browser's latest searches, newest first, kept in localStorage (it may be unavailable).
function readHistory() {
  try {
    const saved = JSON.parse(localStorage.getItem(HISTORY_KEY) ?? '[]')
    return Array.isArray(saved) ? saved.filter((item) => typeof item === 'string' && item.trim()).slice(0, HISTORY_SIZE) : []
  } catch {
    return []
  }
}
function saveHistory(items) {
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(items)) } catch { /* private mode: history stays in memory */ }
  return items
}

// The header search, as on CellphoneS: an empty box shows recent searches; typing opens suggestions under the box
// (“Có phải bạn muốn tìm” category pages and “Sản phẩm gợi ý” products); Enter opens the results page. Vietnamese input
// composition finishes before asking.
export default function SearchBox() {
  const navigate = useNavigate()
  const { pathname, search } = useLocation()
  const route = pathname + search
  const currentKeyword = pathname === SEARCH_PATH ? new URLSearchParams(search).get('q') ?? '' : ''
  const [draft, setDraft] = useState({ route, value: currentKeyword })
  const keyword = draft.route === route ? draft.value : currentKeyword
  // Suggestions stay open on the page they were opened on; any page change closes them.
  const [openOn, setOpenOn] = useState(null)
  const [query, setQuery] = useState('')
  const suggestions = useApiData(query ? `search-suggestions:${query}` : null, (signal) => getSearchSuggestions(query, { signal }))
  // The previous answer stays on screen while the next one loads, so the box does not flicker while typing.
  const [shown, setShown] = useState(null)
  if (suggestions.data && suggestions.data !== shown) setShown(suggestions.data)
  const timer = useRef(null)
  const composing = useRef(false)
  const input = useRef(null)
  const panel = useRef(null)
  const panelId = useId()
  const [history, setHistory] = useState(readHistory)
  const browsing = keyword.trim() === ''
  const open = openOn === route && (browsing ? history.length > 0 : query !== '')

  function ask(value, immediately = false) {
    clearTimeout(timer.current)
    if (composing.current) return
    const text = value.trim()
    if (immediately) setQuery(text)
    else timer.current = setTimeout(() => setQuery(text), 250)
  }

  function change(value) {
    setDraft({ route, value })
    setOpenOn(route)
    ask(value)
  }

  function submit(event) {
    event.preventDefault()
    clearTimeout(timer.current)
    setOpenOn(null)
    const text = keyword.trim()
    // The keyword already shown keeps the category and sort the customer has chosen.
    if (!text) return
    remember(text)
    if (pathname === SEARCH_PATH && text === currentKeyword.trim()) return
    leave()
    navigate(searchPath(text))
  }

  function remember(text) {
    const same = (item) => item.toLocaleLowerCase('vi-VN') === text.toLocaleLowerCase('vi-VN')
    setHistory((items) => saveHistory([text, ...items.filter((item) => !same(item))].slice(0, HISTORY_SIZE)))
  }

  function forget(text) {
    setHistory((items) => saveHistory(items.filter((item) => item !== text)))
  }

  // Once the box has opened a page, it shows that page's keyword (empty outside search), also after Back.
  function leave() {
    setDraft({ route: null, value: '' })
  }

  // Arrow keys walk the suggestion links, from the box into the list and around it.
  function step(event) {
    if (event.key === 'Escape') {
      if (!open) return  // a second Escape clears the box, as the browser does for search fields
      event.preventDefault()
      setOpenOn(null)
      input.current?.focus()
      return
    }
    if (!open || !['ArrowDown', 'ArrowUp'].includes(event.key)) return
    const links = [...(panel.current?.querySelectorAll('a') ?? [])]
    if (!links.length) return
    event.preventDefault()
    const at = links.indexOf(document.activeElement)
    const next = event.key === 'ArrowDown' ? at + 1 : (at < 0 ? links.length : at) - 1
    links[(next + links.length) % links.length].focus()
  }

  const data = shown && open ? shown : null
  const empty = data && !data.Searches.length && !data.Products.length

  return <form className="shop-search" role="search" onSubmit={submit} onKeyDown={step}
    onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpenOn(null) }}>
    <input ref={input} type="search" name="q" value={keyword} onChange={(event) => change(event.target.value)}
      onFocus={(event) => {
        // Coming back from the list (Escape) leaves it closed; arriving from elsewhere shows it again.
        if (event.currentTarget.form.contains(event.relatedTarget)) return
        setOpenOn(route)
        if (keyword.trim()) ask(keyword, true)
      }}
      onCompositionStart={() => { composing.current = true; clearTimeout(timer.current) }}
      onCompositionEnd={(event) => { composing.current = false; change(event.currentTarget.value) }}
      placeholder="Tìm kiếm điện thoại, laptop, phụ kiện..." aria-label="Tìm kiếm sản phẩm" maxLength={100}
      aria-controls={open ? panelId : undefined} aria-expanded={open} autoComplete="off" />
    {open && <div id={panelId} ref={panel} className="search-suggest" role="region" aria-label="Gợi ý tìm kiếm"
      onMouseDown={(event) => event.preventDefault()} onClick={(event) => { if (event.target.closest('a')) leave() }}>
      {browsing ? <section aria-labelledby={`${panelId}-history`}>
        <div className="search-history-heading"><h2 id={`${panelId}-history`}>Lịch sử tìm kiếm</h2>
          <button type="button" onClick={() => setHistory(saveHistory([]))}>Xóa tất cả</button></div>
        <ul className="search-history">{history.map((item) => <li key={item}>
          <Link to={searchPath(item)} onClick={() => remember(item)}>{item}</Link>
          <button type="button" aria-label={`Xóa “${item}” khỏi lịch sử`} onClick={() => forget(item)}>×</button>
        </li>)}</ul>
      </section> : !data ? <p className="search-suggest-note">{suggestions.error ? 'Chưa tải được gợi ý. Nhấn Enter để xem kết quả.' : 'Đang tìm…'}</p>
        : empty ? <p className="search-suggest-note">Không có sản phẩm nào khớp với “{query}”.</p> : <>
          {data.Searches.length > 0 && <section aria-labelledby={`${panelId}-searches`}>
            <h2 id={`${panelId}-searches`}>Có phải bạn muốn tìm</h2>
            <ul className="search-suggest-searches">{data.Searches.map((item) => <li key={item.Label}>
              <Link to={categoryPath(item.CategorySlug) + (item.BrandId ? `?brand=${encodeURIComponent(item.BrandId)}` : '')}>
                <StoreImage src={item.ImageUrl} alt="" loading="lazy" fallback={<span className="search-suggest-thumb" aria-hidden="true" />} />
                <span>{item.Label}</span>
              </Link>
            </li>)}</ul>
          </section>}
          {data.Products.length > 0 && <section aria-labelledby={`${panelId}-products`}>
            <h2 id={`${panelId}-products`}>Sản phẩm gợi ý</h2>
            <ul className="search-suggest-products">{data.Products.map((product) => <li key={product.ProductId}>
              <Link to={productPath(product.Slug)}>
                <StoreImage src={product.ImageUrl} alt="" loading="lazy" fallback={<span className="search-suggest-thumb" aria-hidden="true" />} />
                <span className="search-suggest-product">
                  <span className="search-suggest-name">{product.Name}</span>
                  <span className="search-suggest-price">{product.Price === null ? 'Liên hệ' : formatMoney(product.Price)}
                    {product.OriginalPrice && <del>{formatMoney(product.OriginalPrice)}</del>}</span>
                </span>
              </Link>
            </li>)}</ul>
          </section>}
          <Link className="search-suggest-all" to={searchPath(query)} onClick={() => remember(query)}>Xem tất cả kết quả cho “{query}” <span aria-hidden="true">›</span></Link>
        </>}
    </div>}
  </form>
}
