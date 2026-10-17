import { useCallback, useEffect, useState } from 'react'
import { listProductReviews } from '../../../lib/review-api.js'

// Keep earlier reviews visible while loading/retrying the next page. A new filter,
// product or saved review starts a fresh list; late responses cannot mix lists.
export default function useProductReviewList(productId, rating, page, version) {
  const key = `${productId}:${rating}:${version}`
  const [state, setState] = useState(null)
  const [attempt, setAttempt] = useState(0)
  const requestKey = `${key}:${page}:${attempt}`

  useEffect(() => {
    const controller = new AbortController()
    listProductReviews(productId, { rating, page, signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return
      setState(previous => {
        const earlier = page > 1 && previous?.key === key ? previous.items : []
        const items = [...new Map([...earlier, ...result.Items].map(review => [review.ReviewId, review])).values()]
        return { key, requestKey, items, total: result.Total, error: '' }
      })
    }).catch(failure => {
      if (controller.signal.aborted) return
      setState(previous => ({
        key, requestKey, error: failure.message || 'Không thể tải đánh giá.',
        items: previous?.key === key ? previous.items : [],
        total: previous?.key === key ? previous.total : 0,
      }))
    })
    return () => controller.abort()
  }, [key, requestKey, productId, rating, page])

  const reload = useCallback(() => setAttempt(value => value + 1), [])
  const current = state?.key === key ? state : null
  return {
    data: current ? { Items: current.items, Total: current.total } : null,
    loading: !current || current.requestKey !== requestKey,
    error: current?.requestKey === requestKey ? current.error : '',
    reload,
  }
}
