import { useEffect, useState } from 'react'

const wishlistCache = new Map()
const wishlistRequests = new Map()
const wishlistVersions = new Map()
const wishlistChanges = new Map()

export async function readWishlistProducts(userId, send, options = {}) {
  const version = wishlistVersions.get(userId) ?? 0
  const wishlist = await send('/wishlist', options)
  const ids = new Set((wishlist.Items ?? []).map((item) => item.ProductId ?? item.Product?.ProductId).filter(Boolean))
  // A GET started before a successful toggle must not restore its older heart state.
  for (const [productId, change] of wishlistChanges.get(userId) ?? []) {
    if (change.version <= version) continue
    if (change.added) ids.add(productId)
    else ids.delete(productId)
  }
  wishlistCache.set(userId, ids)
  return wishlist
}

async function loadWishlist(userId, send, refresh = false) {
  if (!refresh && wishlistCache.has(userId)) return wishlistCache.get(userId)
  if (!wishlistRequests.has(userId)) {
    const request = readWishlistProducts(userId, send).then(() => {
      wishlistRequests.delete(userId)
      return wishlistCache.get(userId)
    }).catch((error) => {
      wishlistRequests.delete(userId)
      throw error
    })
    wishlistRequests.set(userId, request)
  }
  return wishlistRequests.get(userId)
}

export function updateWishlistProduct(userId, productId, added) {
  const ids = new Set(wishlistCache.get(userId) ?? [])
  if (added) ids.add(productId)
  else ids.delete(productId)
  wishlistCache.set(userId, ids)
  const version = (wishlistVersions.get(userId) ?? 0) + 1
  wishlistVersions.set(userId, version)
  const changes = wishlistChanges.get(userId) ?? new Map()
  changes.set(productId, { added, version })
  wishlistChanges.set(userId, changes)
}

export default function useWishlistProduct({ enabled, productId, userId, send }) {
  const key = `${userId ?? ''}:${productId}`
  const [state, setState] = useState({ key: '', added: false })

  useEffect(() => {
    if (!enabled) return undefined
    let active = true
    const sync = (refresh = false) => {
      loadWishlist(userId, send, refresh)
        .then((ids) => { if (active) setState({ key, added: ids.has(productId) }) })
        .catch(() => {})
    }
    const changed = () => sync()
    const refresh = () => { if (!document.hidden) sync(true) }
    sync(true)
    window.addEventListener('vietech-wishlist-changed', changed)
    window.addEventListener('focus', refresh)
    return () => {
      active = false
      window.removeEventListener('vietech-wishlist-changed', changed)
      window.removeEventListener('focus', refresh)
    }
  }, [enabled, key, productId, send, userId])

  const added = enabled ? (state.key === key ? state.added : wishlistCache.get(userId)?.has(productId) ?? false) : false
  return [added, (value) => setState({ key, added: value })]
}
