import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { PolicySection } from '../components/home/StaticSections.jsx'
import InfoPage from './InfoPage.jsx'

const policy = {
  ReturnWindowDays: 15,
  Warranty: ['Bảo hành theo thời hạn của sản phẩm đã mua.', 'Phí gửi và thời gian xử lý cần nhân viên xác nhận.'],
  Returns: ['Gửi yêu cầu đổi sản phẩm trong 15 ngày, tính ngày giao là ngày đầu tiên.',
    'Mỗi phiếu đổi 1 sản phẩm; chưa hỗ trợ yêu cầu trả hàng hoàn tiền mới.'],
}

function response(data = policy, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
}

afterEach(() => vi.unstubAllGlobals())

test.each([
  ['warranty', 'Chính sách bảo hành', policy.Warranty, 'Tạo yêu cầu bảo hành', '/bao-hanh/tao-yeu-cau'],
  ['returns', 'Chính sách đổi trả', policy.Returns, 'Tạo yêu cầu đổi sản phẩm', '/doi-tra/tao-yeu-cau'],
])('%s page shows the public server policy and its request link without an account', async (page, title, lines, label, path) => {
  const fetcher = vi.fn(async () => response())
  vi.stubGlobal('fetch', fetcher)
  render(<MemoryRouter><InfoPage page={page} /></MemoryRouter>)
  expect(screen.getByRole('heading', { level: 1, name: title })).toBeInTheDocument()
  for (const line of lines) expect(await screen.findByText(line)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: label })).toHaveAttribute('href', path)
  expect(fetcher.mock.calls).toHaveLength(1)
  expect(fetcher.mock.calls[0][0]).toMatch(/\/store-policies$/)
  expect(screen.queryByText(/Khoản hoàn tiền được xác nhận/)).not.toBeInTheDocument()
})

test('a failed policy request is retryable and does not publish a guessed return window', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response({ detail: 'Không tải được chính sách.' }, 503))
    .mockResolvedValueOnce(response()))
  render(<MemoryRouter><InfoPage page="returns" /></MemoryRouter>)
  expect(await screen.findByRole('alert')).toHaveTextContent('Không tải được chính sách.')
  expect(screen.queryByText(/7 ngày/)).not.toBeInTheDocument()
  await userEvent.setup().click(screen.getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByText(policy.Returns[0])).toBeInTheDocument()
})

test('the homepage exchange window follows the server configuration', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => response()))
  render(<PolicySection />)
  expect(await screen.findByText('Trong 15 ngày')).toBeInTheDocument()
  expect(screen.getByText('Đổi sản phẩm')).toBeInTheDocument()
  expect(screen.queryByText('Trong 7 ngày')).not.toBeInTheDocument()
})

test('the homepage keeps neutral wording if its policy cannot be loaded', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => response({ detail: 'Chưa tải được chính sách.' }, 503)))
  render(<PolicySection />)
  expect(screen.getByText('Xem điều kiện')).toBeInTheDocument()
  expect(screen.queryByText(/Trong \d+ ngày/)).not.toBeInTheDocument()
})
