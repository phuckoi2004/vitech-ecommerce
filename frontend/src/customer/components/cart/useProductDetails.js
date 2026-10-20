import { useEffect, useEffectEvent, useState } from 'react'
import { getProduct } from '../../../lib/catalog-api.js'

// Public product details of cart lines (image, link, colour/storage), read once per product. A product that is
// no longer on sale is stored as null (404); other failures are left out and tried again when the lines change.
export default function useProductDetails(productIds) {
  const [details, setDetails] = useState({})
  const key = [...new Set(productIds)].sort().join(',')
  const missing = useEffectEvent(() => key.split(',').filter((id) => id && !(id in details)))

  useEffect(() => {
    const ids = missing()
    if (!ids.length) return undefined
    const controller = new AbortController()
    for (const id of ids) {
      getProduct(id, { signal: controller.signal })
        .then((detail) => setDetails((current) => ({ ...current, [id]: detail })))
        .catch((failure) => {
          if (!controller.signal.aborted && failure?.status === 404) setDetails((current) => ({ ...current, [id]: null }))
        })
    }
    return () => controller.abort()
  }, [key])

  return details
}
