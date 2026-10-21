import { fireEvent, render, screen, within } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import ReportsWorkspace from './ReportsWorkspace.jsx'
import { defaultReportFilters } from '../lib/reports.js'

function setup(overrides = {}) {
  const props = { tab: 'revenue', tabs: ['revenue','orders'], filter: defaultReportFilters(),
    onTab: vi.fn(), onApply: vi.fn(), onProduct: vi.fn(), onSort: vi.fn(), onPage: vi.fn(), page: 1,
    options: { data: { Categories: [{ Id: 'cat1', Name: 'Điện thoại' }], Brands: [], Products: [{ Id: 'p1', Name: 'Máy từ API', CategoryId: 'cat1', BrandId: 'b1' }] }, loading: false, error: '', refresh: vi.fn() },
    state: { data: { Summary: { Revenue: '0', Cost: '0', Profit: '0', Quantity: 0, TotalOrders: 0, AverageOrderValue: '0' }, Chart: [], Items: [], Total: 0 }, loading: false, error: '', refresh: vi.fn() },
    ...overrides }
  render(<ReportsWorkspace {...props} />); return props
}
test('empty report has the agreed product columns and no fabricated values or bars', () => {
  setup()
  expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Sản phẩm','SL bán','Doanh số','Tổng giá nhập','Lãi gộp','Biên lãi'])
  expect(within(screen.getByRole('article', { name: 'Doanh số bán hàng' })).getByText(/0/)).toBeInTheDocument()
  expect(screen.getByRole('img').querySelectorAll('rect')).toHaveLength(0)
  expect(screen.queryByText('Doanh thu cao nhất')).not.toBeInTheDocument()
})
test('filters apply only on submit and changing category clears the product', () => {
  const props = setup()
  fireEvent.change(screen.getByRole('combobox', { name: 'Sản phẩm', exact: true }), { target: { value: 'p1' } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Danh mục', exact: true }), { target: { value: 'cat1' } })
  expect(screen.getByRole('combobox', { name: 'Sản phẩm', exact: true })).toHaveValue('')
  expect(props.onApply).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Áp dụng' }))
  expect(props.onApply).toHaveBeenCalledWith(expect.objectContaining({ category_id: 'cat1', product_id: '' }))
})
test('custom reversed dates remain a draft and do not replace the applied report', () => {
  const props = setup()
  fireEvent.change(screen.getByRole('combobox', { name: 'Kỳ báo cáo' }), { target: { value: 'custom' } })
  fireEvent.change(screen.getByLabelText('Từ ngày'), { target: { value: '2026-10-21' } })
  fireEvent.change(screen.getByLabelText('Đến ngày'), { target: { value: '2026-10-01' } })
  fireEvent.click(screen.getByRole('button', { name: 'Áp dụng' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Từ ngày không được sau Đến ngày')
  expect(props.onApply).not.toHaveBeenCalled()
})
test('unknown import price never renders zero cost or artificial profit', () => {
  setup({ state: { data: { Summary: { Revenue: '100000', Cost: null, Profit: null, Margin: null, LinesMissingCost: 2, TotalOrders: 1 }, Items: [], Chart: [], Total: 0 }, loading: false, error: '' } })
  for (const name of ['Tổng giá nhập','Lãi gộp']) expect(within(screen.getByRole('article', { name })).getByText('Chưa đủ dữ liệu')).toBeInTheDocument()
  expect(screen.getByText('2 dòng chưa có giá nhập')).toBeInTheDocument()
})
test('order chart stacks processing, delivered and cancelled while cards use the placement cohort', () => {
  const props = setup({ tab: 'orders', state: { data: { Summary: { TotalOrders: 10, InProgressOrders: 1, DeliveredOrders: 7, CancelledOrders: 2 }, Chart: [{ DateFrom: '2026-10-01', Label: '01/10', TotalOrders: 10, InProgressOrders: 1, DeliveredOrders: 7, CancelledOrders: 2 }], Items: [], Total: 0 }, loading: false, error: '' } })
  expect(screen.getByRole('img').querySelectorAll('rect')).toHaveLength(3)
  expect(within(screen.getByRole('article', { name: 'Đã hủy' })).getByText('Tỷ lệ hủy 20%')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Bán hàng & lãi gộp' }))
  expect(props.onTab).toHaveBeenCalledWith('revenue')
})
test('API errors retain unknown values and offer retry', () => {
  const refresh = vi.fn()
  setup({ state: { data: null, loading: false, error: 'Máy chủ không phản hồi', refresh } })
  expect(within(screen.getByRole('article', { name: 'Doanh số bán hàng' })).getByText('—')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  expect(refresh).toHaveBeenCalled()
})
