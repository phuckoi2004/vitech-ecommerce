// @vitest-environment node
import { afterEach, expect, test, vi } from 'vitest'
import { createBrand, deleteBrand, updateBrand } from './brands.js'

afterEach(() => vi.unstubAllGlobals())

test('brand writes use existing endpoints, session headers and supported DTO fields', async () => {
  const fetch = vi.fn(async (_, options) => options.method === 'DELETE' ? new Response(null, { status: 204 }) : new Response('{}', { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  const body = { Name: 'Hãng thật', Slug: 'hang-that', Description: null, LogoUrl: null, IsActive: true }
  await createBrand('access', body)
  await updateBrand('access', 'brand/id', { IsActive: false })
  expect(await deleteBrand('access', 'brand/id')).toBeNull()
  expect(fetch.mock.calls.map(([url, options]) => [url, options.method])).toEqual([
    ['/api/admin/brands', 'POST'], ['/api/admin/brands/brand%2Fid', 'PATCH'], ['/api/admin/brands/brand%2Fid', 'DELETE'],
  ])
  expect(fetch.mock.calls.every(([, options]) => options.headers.Authorization === 'Bearer access' && options.credentials === 'include')).toBe(true)
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(body)
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ IsActive: false })
  expect(fetch.mock.calls[2][1].body).toBeUndefined()
})
