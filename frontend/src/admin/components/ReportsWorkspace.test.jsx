import { fireEvent, render, screen, within } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import ReportsWorkspace from './ReportsWorkspace.jsx'
import { defaultReportFilters } from '../lib/reports.js'

function setup(overrides = {}) {
  const props = {
    tab: 'revenue', tabs: ['revenue', 'orders'], filter: defaultReportFilters(), onTab: vi.fn(), onApply: vi.fn(),
    options: { data: { Categories: [{ Id: 'cat1', Name: 'Điện thoại' }], Brands: [{ Id: 'b1', Name: 'Hãng thật' }], Products: [{ Id: 'p1', Name: 'Máy từ API', CategoryId: 'cat1', BrandId: 'b1' }] }, loading: false, error: '', refresh: vi.fn() },
    state: { data: { Summary: { Revenue: '0', TotalOrders: 0, AverageOrderValue: '0', PeakRevenue: '0' }, Chart: [], Items: [], Total: 0 }, loading: false, error: '', refresh: vi.fn() },
    page: 1, onPage: vi.fn(),
    ...overrides,
  }
  render(<ReportsWorkspace {...props} />)
  return props
}

test('empty revenue report keeps Figma columns and zero summary without example products or bars', () => {
  setup()
  expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Thời gian', 'Sản phẩm', 'Danh mục', 'Thương hiệu', 'Doanh thu'])
  expect(within(screen.getByRole('region', { name: 'Tổng doanh thu', exact: true })).getByText(/0/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Xuất báo cáo' })).not.toBeInTheDocument()
  expect(screen.queryByRole('combobox', { name: 'Tài khoản', exact: true })).not.toBeInTheDocument()
  expect(screen.queryByRole('combobox', { name: 'Nhà cung cấp', exact: true })).not.toBeInTheDocument()
  expect(screen.getByRole('img', { name: 'Doanh thu theo thời gian' }).querySelectorAll('rect')).toHaveLength(0)
  expect(screen.getAllByText('Chưa có dữ liệu trong kỳ đã chọn.').length).toBeGreaterThan(0)
})

test('filters only apply on submit; dependent products clear; reset applies defaults', () => {
  const props = setup()
  fireEvent.change(screen.getByRole('combobox', { name: 'Sản phẩm', exact: true }), { target: { value: 'p1' } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Danh mục', exact: true }), { target: { value: 'cat1' } })
  expect(screen.getByRole('combobox', { name: 'Sản phẩm', exact: true })).toHaveValue('')
  fireEvent.change(screen.getByRole('combobox', { name: 'Thương hiệu', exact: true }), { target: { value: 'b1' } })
  expect(props.onApply).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Áp dụng' }))
  expect(props.onApply).toHaveBeenLastCalledWith(expect.objectContaining({ brand_id: 'b1', category_id: 'cat1', product_id: '' }))
  fireEvent.click(screen.getByRole('button', { name: 'Xóa lọc' }))
  expect(props.onApply).toHaveBeenLastCalledWith(defaultReportFilters())
})

test('time dropdown offers twelve individual months and recent five without custom date fields', () => {
  const props = setup()
  const select = screen.getByRole('combobox', { name: 'Thời gian', exact: true })
  expect(within(select).getAllByRole('option')).toHaveLength(13)
  expect(screen.queryByLabelText('Từ ngày')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Đến ngày')).not.toBeInTheDocument()
  fireEvent.change(select, { target: { value: 'recent' } })
  fireEvent.click(screen.getByRole('button', { name: 'Áp dụng' }))
  expect(props.onApply).toHaveBeenCalledWith(expect.objectContaining({ period: 'recent' }))
})

test('order report has one total-orders column per month and keeps status counts in cards/table', () => {
  const props = setup({ tab: 'orders', state: { data: { Summary: { TotalOrders: 10, DeliveredOrders: 7, CancelledOrders: 2 }, Chart: [{ Label: 'Tháng 10/2026', TotalOrders: 10, DeliveredOrders: 7, CancelledOrders: 2 }], Items: [{ Key: '2026-10', PeriodLabel: 'Tháng 10/2026', TotalOrders: 10, DeliveredOrders: 7, CancelledOrders: 2, CancelRate: '20%' }], Total: 1 }, loading: false, error: '', refresh: vi.fn() } })
  expect(screen.queryByRole('combobox', { name: 'Tài khoản' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Xuất báo cáo' })).not.toBeInTheDocument()
  expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Thời gian', 'Tổng đơn', 'Giao thành công', 'Đã hủy', 'Tỷ lệ hủy'])
  expect(screen.getByRole('img', { name: 'Số lượng đơn hàng theo thời gian' }).querySelectorAll('rect')).toHaveLength(1)
  expect(within(screen.getByRole('region', { name: 'Tỷ lệ giao thành công', exact: true })).getByText('70%')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Thống kê theo doanh thu', exact: true }))
  expect(props.onTab).toHaveBeenCalledWith('revenue')
})

test('API failures show retry and unknown totals instead of false zero results', () => {
  const refresh = vi.fn()
  setup({ state: { data: null, loading: false, error: 'Máy chủ không phản hồi', refresh } })
  expect(screen.getByText('Máy chủ không phản hồi')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Xuất báo cáo' })).not.toBeInTheDocument()
  expect(within(screen.getByRole('region', { name: 'Tổng doanh thu', exact: true })).getByText('—')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  expect(refresh).toHaveBeenCalled()
})

test.each(['revenue', 'orders'])('empty five-month %s chart keeps five month labels without inventing bars', (tab) => {
  const months = ['2026-06', '2026-07', '2026-08', '2026-09', '2026-10']
  setup({ tab, state: { data: { Summary: { Revenue: '0', TotalOrders: 0 },
    Chart: months.map((month) => ({ DateFrom: month + '-01', Label: `Tháng ${Number(month.slice(5))}/2026`, Revenue: '0', TotalOrders: 0 })),
    Items: [], Total: 0 }, loading: false, error: '', refresh: vi.fn() } })
  const chart = screen.getByRole('img')
  expect(chart.querySelectorAll('rect')).toHaveLength(0)
  for (const month of months) expect(within(chart).getByText(`Tháng ${Number(month.slice(5))}/2026`)).toBeInTheDocument()
})
