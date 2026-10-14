// @vitest-environment node
import { afterEach, expect, test, vi } from 'vitest'
import { createCategory, deleteCategory, updateCategory } from './categories.js'

afterEach(() => vi.unstubAllGlobals())

test('category writes use the existing API, bearer session and exact DTO fields', async () => {
  const fetch = vi.fn(async (_, options) => options.method === 'DELETE' ? new Response(null, { status: 204 }) : new Response('{}', { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  const body = { Name: 'Danh mục thật', Slug: 'danh-muc-that', Description: null, ParentCategoryId: null, DisplayOrder: 0, IsActive: true }
  await createCategory('access', body)
  await updateCategory('access', 'category/id', { IsActive: false })
  expect(await deleteCategory('access', 'category/id')).toBeNull()
  expect(fetch.mock.calls.map(([url, options]) => [url, options.method])).toEqual([
    ['/api/admin/categories', 'POST'], ['/api/admin/categories/category%2Fid', 'PATCH'], ['/api/admin/categories/category%2Fid', 'DELETE'],
  ])
  expect(fetch.mock.calls.every(([, options]) => options.headers.Authorization === 'Bearer access' && options.credentials === 'include')).toBe(true)
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(body)
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ IsActive: false })
  expect(fetch.mock.calls[2][1].body).toBeUndefined()
})
