// @vitest-environment node
import { afterEach, expect, test, vi } from 'vitest'
import { createCatalogItem, updateCatalogItem, updateCatalogProduct, createProduct, updateProduct, deleteProduct, createVariant, updateVariant, deleteVariant, addProductImage, deleteProductImage } from './products.js'

afterEach(() => vi.unstubAllGlobals())

test('catalog writes use authenticated existing endpoints and keep stock out of variant data', async () => {
  const fetch = vi.fn(async () => new Response('{}', { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  const product = { Name: 'Máy thật', CategoryId: 'category', BrandId: 'brand', WarrantyMonths: 12, Status: 'Draft', Slug: 'may-that' }
  const variant = { ProductId: 'p1', Sku: 'SKU', VariantName: 'Đen', Price: '12000000' }
  await createProduct('access', product)
  await updateProduct('access', 'p1', { Name: 'Tên mới' })
  await deleteProduct('access', 'p1')
  await createVariant('access', variant)
  await updateVariant('access', 'v1', { Price: '10000000' })
  await deleteVariant('access', 'v1')
  await addProductImage('access', 'p1', { ImageUrl: 'https://example.com/image.png', IsDefault: true })
  await deleteProductImage('access', 'p1', 'i1')
  expect(fetch.mock.calls.map(([url, options]) => [url, options.method])).toEqual([
    ['/api/admin/products', 'POST'], ['/api/admin/products/p1', 'PATCH'], ['/api/admin/products/p1', 'DELETE'],
    ['/api/admin/variants', 'POST'], ['/api/admin/variants/v1', 'PATCH'], ['/api/admin/variants/v1', 'DELETE'],
    ['/api/admin/products/p1/images', 'POST'], ['/api/admin/products/p1/images/i1', 'DELETE'],
  ])
  expect(fetch.mock.calls.every(([, options]) => options.headers.Authorization === 'Bearer access' && options.credentials === 'include')).toBe(true)
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(product)
  expect(JSON.parse(fetch.mock.calls[3][1].body)).toEqual(variant)
  expect(fetch.mock.calls[2][1].body).toBeUndefined()
})

test('single-SKU forms use one authenticated request for catalog data, price and images', async () => {
  const fetch = vi.fn(async () => new Response('{}', { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  const body = { ProductId: 'p1', Sku: 'MY-WHITE', Color: 'Trắng', Price: '12000000', IsActive: true }
  await createCatalogItem('access', body)
  const { ProductId: parentId, ...variantBody } = body
  await updateCatalogItem('access', 'variant/id', variantBody)
  const shared = { Name: 'Máy', Images: [{ ImageUrl: 'https://example.com/white.png', IsDefault: true }] }
  await updateCatalogProduct('access', parentId, shared)
  expect(fetch.mock.calls.map(([url, options]) => [url, options.method])).toEqual([
    ['/api/admin/catalog-items', 'POST'], ['/api/admin/catalog-items/variant%2Fid', 'PUT'],
    ['/api/admin/catalog-products/p1', 'PUT'],
  ])
  for (const [, options] of fetch.mock.calls) {
    expect(options.headers.Authorization).toBe('Bearer access')
    expect(options.credentials).toBe('include')
  }
  expect(fetch.mock.calls.map(([, options]) => JSON.parse(options.body))).toEqual([body, variantBody, shared])
})
