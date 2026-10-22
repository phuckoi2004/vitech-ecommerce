import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import ProductStockDialog from './ProductStockDialog.jsx'

const api = vi.hoisted(() => ({ setStockQuantity: vi.fn() }))
vi.mock('../services/inventory.js', () => api)
const item = { ProductVariantId: 'v1', Name: 'Điện thoại', Sku: 'PHONE-DEN', StockQuantity: 3, IsSerialTracked: false }
let saved, closed, refreshed
beforeEach(() => {
  vi.resetAllMocks(); saved = vi.fn(); closed = vi.fn(); refreshed = vi.fn()
  api.setStockQuantity.mockImplementation(async (_, id, body) => ({ ProductVariantId: id, StockQuantity: body.StockQuantity }))
})
function show(role = 'Admin', variant = item, permissions = ['inventory:update']) {
  render(<AuthContext.Provider value={makeAuth({ role, permissions })}><ProductStockDialog item={variant} onClose={closed} onSaved={saved} onRefresh={refreshed} /></AuthContext.Provider>)
}

test.each([10, 2, 0])('Admin can set stock to %s without a reason/history request', async (quantity) => {
  show()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Số lượng tồn kho mới' }), { target: { value: String(quantity) } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu tồn kho' }))
  await waitFor(() => expect(api.setStockQuantity).toHaveBeenCalledExactlyOnceWith('access-for-test', 'v1', { StockQuantity: quantity, ExpectedStockQuantity: 3 }))
  expect(saved).toHaveBeenCalledWith({ QuantityBefore: 3, QuantityAfter: quantity })
})

test.each(['-1', '1.5', '', '2147483648'])('invalid stock %s is blocked before calling the API', async (value) => {
  show()
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value } })
  expect(screen.getByRole('button', { name: 'Lưu tồn kho' })).toBeDisabled()
  fireEvent.submit(screen.getByRole('dialog').querySelector('form'))
  expect(api.setStockQuantity).not.toHaveBeenCalled()
})

test.each(['Staff', 'Customer'])('%s cannot see an edit form even with a stale inventory permission', (role) => {
  show(role)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(api.setStockQuantity).not.toHaveBeenCalled()
})

test('increasing tracked stock requires a second form with only serial input before any write', async () => {
  show('Admin', { ...item, IsSerialTracked: true })
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '5' } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu tồn kho' }))
  expect(api.setStockQuantity).not.toHaveBeenCalled()
  expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
  const serial = screen.getByRole('textbox', { name: 'Serial/IMEI' })
  expect(screen.getAllByRole('textbox')).toHaveLength(1)
  fireEvent.change(serial, { target: { value: 'REAL-1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Xác nhận sửa' }))
  expect(screen.getByRole('alert')).toHaveTextContent('đúng 2')
  fireEvent.change(serial, { target: { value: 'REAL-1\nREAL-1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Xác nhận sửa' }))
  expect(screen.getByRole('alert')).toHaveTextContent('bị trùng')
  expect(api.setStockQuantity).not.toHaveBeenCalled()
  fireEvent.change(serial, { target: { value: ' REAL-1 \n REAL-2 ' } })
  fireEvent.click(screen.getByRole('button', { name: 'Xác nhận sửa' }))
  await waitFor(() => expect(api.setStockQuantity).toHaveBeenCalledExactlyOnceWith('access-for-test', 'v1', {
    StockQuantity: 5, ExpectedStockQuantity: 3, SerialNumbers: ['REAL-1', 'REAL-2'],
  }))
})

test('reducing tracked stock lets the server select devices without an input form', async () => {
  show('Admin', { ...item, IsSerialTracked: true })
  fireEvent.click(screen.getByRole('button', { name: 'Giảm tồn kho 1' }))
  fireEvent.click(screen.getByRole('button', { name: 'Giảm tồn kho 1' }))
  expect(screen.getByRole('spinbutton')).toHaveValue(1)
  fireEvent.click(screen.getByRole('button', { name: 'Lưu tồn kho' }))
  await waitFor(() => expect(api.setStockQuantity).toHaveBeenCalledWith('access-for-test', 'v1', { StockQuantity: 1, ExpectedStockQuantity: 3 }))
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
})

test('switching from an increase to a decrease never sends entered serials or asks which devices to remove', async () => {
  show('Admin', { ...item, IsSerialTracked: true })
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '4' } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu tồn kho' }))
  fireEvent.change(screen.getByRole('textbox', { name: 'Serial/IMEI' }), { target: { value: 'NEW-1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Quay lại' }))
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '1' } })
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Lưu tồn kho' }))
  await waitFor(() => expect(api.setStockQuantity).toHaveBeenCalledExactlyOnceWith('access-for-test', 'v1', {
    StockQuantity: 1, ExpectedStockQuantity: 3,
  }))
})

test('cancel from serial input never changes stock or registers codes', () => {
  show('Admin', { ...item, IsSerialTracked: true })
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '4' } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu tồn kho' }))
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'REAL-1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Hủy' }))
  expect(api.setStockQuantity).not.toHaveBeenCalled()
  expect(closed).toHaveBeenCalledOnce()
})

test('cancel does not save and unchanged stock cannot be submitted', () => {
  show()
  expect(screen.getByRole('button', { name: 'Lưu tồn kho' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Hủy' }))
  expect(closed).toHaveBeenCalledOnce()
  expect(api.setStockQuantity).not.toHaveBeenCalled()
})

test('a stale count requires a refresh before another write', async () => {
  api.setStockQuantity.mockRejectedValue(Object.assign(new Error('Tồn kho đã thay đổi'), { status: 409 }))
  show()
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '5' } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu tồn kho' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: 'Lưu tồn kho' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Đóng và tải lại' }))
  expect(refreshed).toHaveBeenCalledOnce()
})

test('an existing serial is rejected without saving and can be corrected in the same serial form', async () => {
  api.setStockQuantity.mockRejectedValueOnce(Object.assign(new Error('Serial/IMEI đã tồn tại'), { status: 409, code: 'serial_exists' }))
  show('Admin', { ...item, IsSerialTracked: true })
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '4' } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu tồn kho' }))
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'EXISTING' } })
  fireEvent.click(screen.getByRole('button', { name: 'Xác nhận sửa' }))
  await screen.findByRole('alert')
  expect(saved).not.toHaveBeenCalled()
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'NEW-1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Xác nhận sửa' }))
  await waitFor(() => expect(saved).toHaveBeenCalledOnce())
  expect(api.setStockQuantity).toHaveBeenLastCalledWith('access-for-test', 'v1', {
    StockQuantity: 4, ExpectedStockQuantity: 3, SerialNumbers: ['NEW-1'],
  })
})

test('pending saves cannot be duplicated or dismissed', async () => {
  let finish
  api.setStockQuantity.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  show()
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '5' } })
  fireEvent.submit(screen.getByRole('dialog').querySelector('form'))
  fireEvent.submit(screen.getByRole('dialog').querySelector('form'))
  expect(api.setStockQuantity).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('button', { name: 'Hủy' })).toBeDisabled()
  await act(async () => finish({ StockQuantity: 5 }))
})
