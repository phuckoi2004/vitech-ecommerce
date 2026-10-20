import { afterEach, describe, expect, test, vi } from 'vitest'
import { listProductSummaries, loadProductCards, toProductCard } from './catalog-api.js'

const product = {
  ProductId: 'p1', BrandId: 'b1', Name: 'iPhone 18 Pro Max', Slug: 'iphone-18-pro-max',
  AverageRating: '4.80', ReviewCount: 12, SoldQuantity: 1250,
  Variants: [
    { ProductVariantId: 'v1', Price: '24990000.00', StockQuantity: 0 },
    { ProductVariantId: 'v2', Price: '20990000.00', StockQuantity: 3 },
  ],
  Images: [
    { ImageUrl: 'https://cdn.example/second.png', DisplayOrder: 0, IsDefault: false },
    { ImageUrl: 'https://cdn.example/default.png', DisplayOrder: 5, IsDefault: true },
  ],
}

describe('toProductCard', () => {
  test('discount pairs the original and sale prices of the same cheapest variant', () => {
    const card = toProductCard({ ...product, Variants: [
      { Price: '35000000', SalePrice: '33000000', OriginalPrice: '35000000', DiscountPercent: '5.71' },
      { Price: '34000000', SalePrice: '32000000', OriginalPrice: '34000000', DiscountPercent: '5.88' },
    ] })
    expect(card).toMatchObject({ price: 32000000, originalPrice: 34000000, discountPercent: 5.88 })
  })
  test('lowest variant price, default image first, stock from any variant', () => {
    expect(toProductCard(product)).toEqual({
      id: 'p1', name: 'iPhone 18 Pro Max', slug: 'iphone-18-pro-max', brandId: 'b1',
      price: 20990000, imageUrl: 'https://cdn.example/default.png',
      rating: 4.8, reviewCount: 12, sold: 1250, inStock: true,
    })
  })

  test('one price, no image, nothing in stock', () => {
    const card = toProductCard({ ...product, Variants: [{ Price: '990000.00', StockQuantity: 0 }], Images: [] })
    expect(card).toMatchObject({ price: 990000, imageUrl: null, inStock: false })
  })

  test('without a variant on sale there is no price', () => {
    expect(toProductCard({ ...product, Variants: [] })).toMatchObject({ price: null, inStock: false })
  })

  test('cards use the default colour photo instead of a shared photo of another colour', () => {
    const colored = { ...product, DefaultVariantId: 'white', VariantImages: {
      white: [{ ImageUrl: 'https://cdn.example/white.png', IsDefault: true, DisplayOrder: 0 }],
    } }
    expect(toProductCard(colored).imageUrl).toBe('https://cdn.example/white.png')
    expect(toProductCard({ ...colored, VariantImages: { white: [] } }).imageUrl).toBeNull()
  })
})

describe('loadProductCards', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('reads each product detail and leaves out the ones that fail', async () => {
    const urls = []
    vi.stubGlobal('fetch', vi.fn(async (url) => {
      urls.push(url)
      if (url.endsWith('/products/gone')) return new Response(JSON.stringify({ detail: 'Không tìm thấy sản phẩm' }), { status: 404 })
      return new Response(JSON.stringify(product), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const cards = await loadProductCards([{ ProductId: 'p1' }, { ProductId: 'gone' }])
    expect(urls).toEqual(['/api/products/p1', '/api/products/gone'])
    expect(cards.map((card) => card.id)).toEqual(['p1'])
  })

  test('an aborted load is not turned into an empty list', async () => {
    const controller = new AbortController()
    vi.stubGlobal('fetch', vi.fn(async () => {
      controller.abort()
      throw new DOMException('Aborted', 'AbortError')
    }))
    await expect(loadProductCards([{ ProductId: 'p1' }], { signal: controller.signal })).rejects.toThrow()
  })

  test('a server failure is not mistaken for a removed product', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'Hệ thống đang bận.' }), { status: 503 })))
    await expect(loadProductCards([{ ProductId: 'p1' }])).rejects.toMatchObject({ status: 503 })
  })

  test('network failures remain retryable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('network unavailable') }))
    await expect(loadProductCards([{ ProductId: 'p1' }])).rejects.toThrow('Không kết nối được máy chủ')
  })

  test('reads summaries beyond the first page without sending new backend options', async () => {
    const urls = []
    vi.stubGlobal('fetch', vi.fn(async (input) => {
      const url = new URL(input, 'http://localhost')
      urls.push(url)
      const page = Number(url.searchParams.get('page'))
      const items = page === 1
        ? Array.from({ length: 100 }, (_, index) => ({ ProductId: `p${index}`, BrandId: 'b1', SoldQuantity: index }))
        : [{ ProductId: 'older-best', BrandId: 'b2', SoldQuantity: 500 }]
      return new Response(JSON.stringify({ Items: items, Total: 101, Page: page }), { status: 200 })
    }))
    const summaries = await listProductSummaries({ categoryId: 'c1', includeDescendants: true })
    expect(summaries).toHaveLength(101)
    expect(summaries.at(-1)).toMatchObject({ ProductId: 'older-best', BrandId: 'b2', SoldQuantity: 500 })
    expect(urls.map((url) => url.searchParams.get('page'))).toEqual(['1', '2'])
    for (const url of urls) {
      expect(url.searchParams.get('category_id')).toBe('c1')
      expect(url.searchParams.get('include_descendants')).toBe('true')
      expect(url.searchParams.has('sort')).toBe(false)
    }
  })
})
