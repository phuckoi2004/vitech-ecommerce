// Shared public card endpoint fixture; per-product overrides still model removal and service failures.
export async function productCardsResponse(url, lookup, overrides = {}) {
  const products = []
  for (const id of url.searchParams.getAll('product_id')) {
    const path = `/products/${id}`
    let value = path in overrides
      ? typeof overrides[path] === 'function' ? await overrides[path](url) : overrides[path]
      : typeof lookup === 'function' ? lookup(id) : lookup[id]
    if (value instanceof Response) {
      if (value.status === 404) continue
      if (!value.ok) return value.clone()
      value = await value.clone().json()
    }
    if (value) products.push(value)
  }
  return new Response(JSON.stringify(products), { headers: { 'Content-Type': 'application/json' } })
}
