import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronLeftIcon, ChevronRightIcon } from '../icons.jsx'

// Horizontally scrolling row of `<li>` items; on wide screens an arrow pages through it while there is more that way.
// The arrows are a pointer shortcut kept out of the tab order (each item holds a link, and focusing it scrolls the
// row), so an arrow disappearing at the end never drops keyboard focus.
export default function ScrollRail({ className = '', children }) {
  const track = useRef(null)
  const [edges, setEdges] = useState({ start: true, end: true })

  const measure = useCallback(() => {
    const element = track.current
    if (!element) return
    const start = element.scrollLeft <= 4
    const end = element.scrollLeft + element.clientWidth >= element.scrollWidth - 4
    setEdges((current) => current.start === start && current.end === end ? current : { start, end })
  }, [])

  useEffect(() => {
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [measure, children])

  const page = (direction) => track.current?.scrollBy?.({ left: direction * track.current.clientWidth * 0.85, behavior: 'smooth' })

  return <div className={`home-rail ${className}`.trim()}>
    {!edges.start && <button type="button" className="home-rail-nav is-prev" onClick={() => page(-1)} tabIndex={-1} aria-hidden="true"><ChevronLeftIcon /></button>}
    <ul className="home-rail-track" ref={track} onScroll={measure}>{children}</ul>
    {!edges.end && <button type="button" className="home-rail-nav is-next" onClick={() => page(1)} tabIndex={-1} aria-hidden="true"><ChevronRightIcon /></button>}
  </div>
}
