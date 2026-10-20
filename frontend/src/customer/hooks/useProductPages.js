import { useEffect, useEffectEvent, useState } from 'react'

const EMPTY_RESULT = { key: null, pages: [], total: 0, remaining: 0, failed: null }

// Pages of one product query, for "Xem thêm": `more()` appends the next page and keeps the ones already shown.
// `key` names everything the query depends on; a new key starts again from page 1, a null key loads nothing.
// `loadPage(page, signal)` resolves to { cards, Items, Total, PageSize }. Items are the API summaries, including
// products whose detail has since disappeared. A failed page keeps earlier pages; `retry()` asks for it again.
export default function useProductPages(key, loadPage) {
  const [request, setRequest] = useState({ key, page: 1, attempt: 0 })
  const [result, setResult] = useState(EMPTY_RESULT)
  // Reset before committing the new query, including when returning to a key that previously loaded page 2+.
  if (request.key !== key) {
    setRequest({ key, page: 1, attempt: 0 })
    setResult(EMPTY_RESULT)
  }
  const current = request.key === key ? request : { key, page: 1, attempt: 0 }
  const { page, attempt } = current
  const load = useEffectEvent((page, signal) => loadPage(page, signal))

  useEffect(() => {
    if (key === null) return undefined
    const controller = new AbortController()
    load(page, controller.signal).then((data) => {
      if (controller.signal.aborted) return
      // Count consumed summaries, not visible cards: a detail 404 must not create a phantom next page.
      const consumed = (page - 1) * data.PageSize + data.Items.length
      const remaining = data.Items.length < data.PageSize ? 0 : Math.max(0, data.Total - consumed)
      setResult((previous) => {
        const pages = previous.key === key ? previous.pages.slice(0, page - 1) : []
        pages[page - 1] = data.cards
        return { key, pages, total: data.Total, remaining, failed: null }
      })
    }).catch((failure) => {
      if (controller.signal.aborted) return
      setResult((previous) => ({ ...(previous.key === key ? previous : EMPTY_RESULT), key,
        failed: { page, attempt, message: failure?.message || 'Không thể tải sản phẩm.' } }))
    })
    return () => controller.abort()
  }, [key, page, attempt])

  const shown = result.key === key ? result : null
  const loaded = shown?.pages.length ?? 0
  const failed = shown?.failed?.page === page && shown.failed.attempt === attempt ? shown.failed.message : ''
  return {
    products: shown ? shown.pages.flat() : [],
    total: shown?.total ?? 0,
    remaining: shown?.remaining ?? 0,
    loading: key !== null && !failed && loaded < page,
    error: failed,
    more: () => setRequest({ key, page: loaded + 1, attempt: 0 }),
    retry: () => setRequest({ key, page, attempt: attempt + 1 }),
  }
}
