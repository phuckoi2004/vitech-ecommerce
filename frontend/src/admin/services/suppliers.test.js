// @vitest-environment node
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { createSupplier, getSupplierDirectory, hideSupplier, updateSupplier } from './suppliers.js'

const api = vi.hoisted(() => ({ getAdminData: vi.fn() }))
vi.mock('../../services/api/admin.js', () => api)
beforeEach(() => vi.resetAllMocks())
afterEach(() => vi.unstubAllGlobals())

test('directory reads all API pages before local searching, including inactive suppliers', async () => {
  const rows = Array.from({ length: 251 }, (_, i) => ({ SupplierId: 's' + i, SupplierCode: 'NCC-' + i, IsActive: i % 2 === 0 }))
  api.getAdminData.mockImplementation(async (_, __, query) => ({ Items: rows.slice((query.page - 1) * query.page_size, query.page * query.page_size), Total: rows.length }))
  const signal = new AbortController().signal
  expect(await getSupplierDirectory('access', signal)).toEqual(rows)
  expect(api.getAdminData.mock.calls.map(([, , query]) => query)).toEqual([1, 2, 3].map((page) => ({ active_only: false, page, page_size: 100 })))
  expect(api.getAdminData.mock.calls.every(([token, path, , passedSignal]) => token === 'access' && path === '/admin/suppliers' && passedSignal === signal)).toBe(true)
})

test('a failed later page rejects the directory instead of exposing incomplete counts/search results', async () => {
  api.getAdminData.mockResolvedValueOnce({ Items: [{ SupplierId: 's1' }], Total: 101 }).mockRejectedValueOnce(new Error('Lỗi trang thứ hai'))
  await expect(getSupplierDirectory('access')).rejects.toThrow('Lỗi trang thứ hai')
})

test('session errors from a parallel batch reach withAccessToken for refresh and retry', async () => {
  api.getAdminData.mockResolvedValueOnce({ Items: [], Total: 201 }).mockRejectedValueOnce(new Error('Lỗi kết nối')).mockRejectedValueOnce(Object.assign(new Error('Hết phiên'), { status: 401 }))
  await expect(getSupplierDirectory('access')).rejects.toMatchObject({ status: 401 })
})

test('aborting after the first page prevents any further page reads', async () => {
  const controller = new AbortController()
  api.getAdminData.mockImplementationOnce(async () => { controller.abort(); return { Items: [], Total: 201 } })
  await expect(getSupplierDirectory('access', controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
  expect(api.getAdminData).toHaveBeenCalledTimes(1)
})

test('supplier writes use the DTO and soft deletion is PATCH IsActive=false, never DELETE', async () => {
  const fetch = vi.fn(async () => new Response('{}', { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  const body = { SupplierCode: 'NCC-NGUOI-DUNG', Name: 'Nhà cung cấp thật', PhoneNumber: '028 7300 0001', Email: null, Address: 'Địa chỉ thật', TaxCode: null, Note: null, IsActive: true }
  await createSupplier('access', body)
  await updateSupplier('access', 'supplier/id', { ...body, IsActive: true })
  await hideSupplier('access', 'supplier/id')
  expect(fetch.mock.calls.map(([url, options]) => [url, options.method])).toEqual([
    ['/api/admin/suppliers', 'POST'], ['/api/admin/suppliers/supplier%2Fid', 'PATCH'], ['/api/admin/suppliers/supplier%2Fid', 'PATCH'],
  ])
  expect(fetch.mock.calls.every(([, options]) => options.headers.Authorization === 'Bearer access' && options.credentials === 'include')).toBe(true)
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(body)
  expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({ IsActive: false })
})
