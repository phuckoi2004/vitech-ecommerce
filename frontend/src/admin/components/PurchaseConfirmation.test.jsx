import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import PurchaseConfirmation from './PurchaseConfirmation.jsx'

const po = { PurchaseOrderId: 'po1', PurchaseOrderCode: 'PN-API-01' }
function props(action = 'reject', overrides = {}) { return { action, po, busy: false, error: '', permitted: true, onCancel: vi.fn(), onConfirm: vi.fn(), ...overrides } }

test.each([['reject', 'Từ chối phiếu nhập PN-API-01', 'Xác nhận từ chối'], ['cancel', 'Xóa phiếu nhập?', 'Xác nhận xóa'], ['approve', 'Xác nhận phiếu nhập PN-API-01?', 'Xác nhận phiếu']])('%s confirmation uses the live code and lets Hủy dismiss without sending a write', (action, title, label) => {
  const values = props(action)
  render(<PurchaseConfirmation {...values} />)
  expect(screen.getByRole('dialog', { name: title })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Hủy', exact: true }))
  expect(values.onCancel).toHaveBeenCalledTimes(1)
  expect(values.onConfirm).not.toHaveBeenCalled()
  expect(screen.queryByText('PN-202610-018')).not.toBeInTheDocument()
})

test('rejection accepts only a nonblank reason, trims it and preserves typed text until submission succeeds', () => {
  const values = props()
  render(<PurchaseConfirmation {...values} />)
  const input = screen.getByRole('textbox', { name: 'Lý do từ chối' })
  const submit = screen.getByRole('button', { name: 'Xác nhận từ chối' })
  expect(input).toHaveAttribute('placeholder', 'Nhập lý do từ chối phiếu nhập')
  expect(submit).toBeDisabled()
  fireEvent.change(input, { target: { value: '   ' } })
  fireEvent.submit(input.closest('form'))
  expect(values.onConfirm).not.toHaveBeenCalled()
  fireEvent.change(input, { target: { value: ' Sai đơn giá ' } })
  fireEvent.click(submit)
  expect(values.onConfirm).toHaveBeenCalledWith('Sai đơn giá')
  expect(input).toHaveValue(' Sai đơn giá ')
})

test('pending writes block cancellation through the button, Escape and the backdrop', () => {
  const values = props('approve', { busy: true })
  render(<PurchaseConfirmation {...values} />)
  const dialog = screen.getByRole('dialog')
  expect(screen.getByRole('button', { name: 'Hủy', exact: true })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Đang xử lý…' })).toBeDisabled()
  fireEvent.click(dialog)
  fireEvent(dialog, new Event('cancel', { cancelable: true }))
  fireEvent.submit(dialog.querySelector('form'))
  expect(values.onCancel).not.toHaveBeenCalled()
  expect(values.onConfirm).not.toHaveBeenCalled()
})

test('fresh uncancellable details disable confirmation and explain that receiving has already begun', () => {
  const values = props('cancel', { permitted: false })
  render(<PurchaseConfirmation {...values} />)
  expect(screen.getByRole('button', { name: 'Xác nhận xóa' })).toBeDisabled()
  expect(screen.getByRole('alert')).toHaveTextContent('không thể hủy')
  expect(screen.getByText(/giữ lại lịch sử/)).toBeInTheDocument()
  fireEvent.submit(screen.getByRole('dialog').querySelector('form'))
  expect(values.onConfirm).not.toHaveBeenCalled()
})

test('failed detail reads can retry but cannot confirm a different or unloaded order', () => {
  const onRetry = vi.fn()
  const values = props('cancel', { po: null, loadError: 'Lỗi tải phiếu.', onRetry })
  render(<PurchaseConfirmation {...values} />)
  expect(screen.getByRole('button', { name: 'Xác nhận xóa' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  expect(onRetry).toHaveBeenCalledTimes(1)
  expect(values.onConfirm).not.toHaveBeenCalled()
})
