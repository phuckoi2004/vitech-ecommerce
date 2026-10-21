import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import ErrorState from '../../../components/shared/ErrorState.jsx'
import useApiData from '../../../hooks/useApiData.js'
import { listBanners } from '../../../lib/catalog-api.js'
import { ChevronLeftIcon, ChevronRightIcon } from '../icons.jsx'
import StoreImage from '../StoreImage.jsx'
import CategoryMenu from './CategoryMenu.jsx'

const SLIDE_MS = 5000
const TRANSITION_MS = 700
const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

// LinkUrl is https or an internal path starting with "/" (ContentService); anything else is not a link.
function BannerLink({ banner, className, children }) {
  const url = banner.LinkUrl ?? ''
  if (url.startsWith('/') && !url.startsWith('//')) return <Link className={className} to={url}>{children}</Link>
  if (url.startsWith('https://')) return <a className={className} href={url}>{children}</a>
  return <div className={className}>{children}</div>
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => window.matchMedia?.(REDUCED_MOTION_QUERY).matches ?? false)
  useEffect(() => {
    const media = window.matchMedia?.(REDUCED_MOTION_QUERY)
    if (!media) return undefined
    const update = () => setReduced(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  return reduced
}

// Banners from GET /banners (active, in their display window, by DisplayOrder). Advances every 5 s unless the
// visitor hovers or focuses it, or prefers reduced motion.
function BannerCarousel({ banners }) {
  const count = banners.length
  const looped = count > 1
  const [slide, setSlide] = useState({ position: looped ? 1 : 0, phase: 'idle' })
  // The ref locks immediately, including two clicks before React has rendered the next frame.
  const motion = useRef(slide)
  const reducedMotion = useReducedMotion()
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const paused = hovered || focused
  const busy = slide.phase !== 'idle'
  const current = looped ? (slide.position - 1 + count) % count : 0

  const commit = useCallback((next) => {
    motion.current = next
    setSlide(next)
  }, [])

  const navigate = useCallback((target, step = 0) => {
    if (count < 2 || motion.current.phase !== 'idle') return
    const position = target === null ? motion.current.position + step : target + 1
    if (position === motion.current.position) return
    commit(reducedMotion
      ? { position: (position - 1 + count) % count + 1, phase: 'idle' }
      : { position, phase: 'moving' })
  }, [count, reducedMotion, commit])

  const finishTransition = useCallback(() => {
    if (motion.current.phase !== 'moving') return
    const position = motion.current.position
    // The two edge slides are exact copies. Rebase only after the visible transition finishes.
    if (position === 0 || position === count + 1) {
      commit({ position: position === 0 ? count : 1, phase: 'resetting' })
    } else commit({ position, phase: 'idle' })
  }, [count, commit])

  useEffect(() => {
    if (slide.phase !== 'resetting') return undefined
    // Paint the clone-to-original rebase with transition:none before enabling another move.
    let secondFrame
    const firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(() => commit({ ...motion.current, phase: 'idle' }))
    })
    return () => {
      window.cancelAnimationFrame(firstFrame)
      window.cancelAnimationFrame(secondFrame)
    }
  }, [slide.phase, commit])

  useEffect(() => {
    if (slide.phase !== 'moving') return undefined
    if (reducedMotion) {
      finishTransition()
      return undefined
    }
    // Recover when a tab is hidden or a browser cancels/suppresses transitionend.
    const timer = window.setTimeout(finishTransition, TRANSITION_MS + 150)
    return () => window.clearTimeout(timer)
  }, [slide.phase, reducedMotion, finishTransition])

  useEffect(() => {
    if (!looped || paused || reducedMotion || busy) return undefined
    const timer = window.setTimeout(() => navigate(null, 1), SLIDE_MS)
    return () => window.clearTimeout(timer)
  }, [looped, paused, reducedMotion, busy, navigate])

  const go = (step) => navigate(null, step)
  const slides = [
    ...(looped ? [{ banner: banners[count - 1], key: 'clone-last', clone: true, index: count - 1 }] : []),
    ...banners.map((banner, index) => ({ banner, key: banner.BannerId, index, clone: false })),
    ...(looped ? [{ banner: banners[0], key: 'clone-first', clone: true, index: 0 }] : []),
  ]

  return <div className="home-banner-carousel" role="region" aria-roledescription="carousel" aria-label="Chương trình nổi bật" aria-busy={busy}
    onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
    onFocus={() => setFocused(true)} onBlur={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false)
    }}>
    <div className="home-banner">
      <div className={`home-banner-track${slide.phase === 'resetting' ? ' is-resetting' : ''}`}
        style={{ transform: `translate3d(-${slide.position * 100}%, 0, 0)`, '--banner-duration': `${TRANSITION_MS}ms` }}
        onTransitionEnd={(event) => {
          if (event.target === event.currentTarget && event.propertyName === 'transform') finishTransition()
        }}>
        {slides.map(({ banner, key, index, clone }) => <div key={key} className="home-banner-slide"
          role="group" aria-roledescription="slide" aria-label={`${index + 1} / ${count}`}
          aria-hidden={clone || index !== current} inert={clone || index !== current}>
          <BannerLink banner={banner} className="home-banner-link">
            <StoreImage src={banner.ImageUrl} alt={banner.Title} loading="eager" decoding="async"
              fallback={<BannerPlaceholder>
                <p>{banner.Title}</p>
                <p role="status">Hình ảnh đang được cập nhật.</p>
              </BannerPlaceholder>} />
          </BannerLink>
        </div>)}
      </div>
      {count > 1 && <>
        <button type="button" className="home-banner-nav is-prev" onClick={() => go(-1)} aria-label="Banner trước" aria-disabled={busy}><ChevronLeftIcon /></button>
        <button type="button" className="home-banner-nav is-next" onClick={() => go(1)} aria-label="Banner tiếp theo" aria-disabled={busy}><ChevronRightIcon /></button>
      </>}
    </div>
    {count > 1 && <div className="home-banner-dots">
        {banners.map((banner, position) => <button key={banner.BannerId} type="button" className="home-banner-dot"
          aria-label={`Xem banner ${position + 1}`} aria-current={position === current || undefined}
          aria-disabled={busy}
          onClick={() => navigate(position)} />)}
      </div>}
  </div>
}

function BannerPlaceholder({ children, error = false }) {
  return <div className={`home-banner home-banner-placeholder${error ? ' is-error' : ''}`}>{children}</div>
}

// Figma "Danh mục": category menu and the banner area.
export default function HeroSection({ categories, brandPool }) {
  const banners = useApiData('banners', (signal) => listBanners({ signal }))

  let banner
  if (banners.loading) banner = <div className="home-banner is-skeleton" aria-hidden="true" />
  else if (banners.error) banner = <BannerPlaceholder error>
    <ErrorState title="Không tải được banner" message={banners.error} onRetry={banners.reload} className="py-4" />
  </BannerPlaceholder>
  else if (banners.data?.length) banner = <BannerCarousel key={banners.data.map((item) => item.BannerId).join(',')} banners={banners.data} />
  else banner = <BannerPlaceholder><p role="status">Chưa có chương trình nổi bật.</p></BannerPlaceholder>

  return <section className="home-hero home-card is-raised" aria-label="Danh mục và chương trình nổi bật">
    <CategoryMenu categories={categories} brandPool={brandPool} />
    <div className="home-hero-content">{banner}</div>
  </section>
}
