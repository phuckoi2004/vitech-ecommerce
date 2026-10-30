import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, test } from 'vitest'
import { compatibilityFixture } from '../../test/ai-compatibility.js'
import AiCompatibility from './AiCompatibility.jsx'
import { compatibilityLabels } from './ai-compatibility.js'

function view(data = compatibilityFixture()) {
  return render(<MemoryRouter><AiCompatibility compatibility={data} /></MemoryRouter>)
}

test.each(Object.keys(compatibilityLabels))('status %s has an explicit readable label and symbol', (status) => {
  view(compatibilityFixture(status))
  expect(screen.getByRole('heading', { name: 'VIETECH AI – KIỂM TRA TƯƠNG THÍCH' })).toBeInTheDocument()
  expect(screen.getAllByText(compatibilityLabels[status]).length).toBeGreaterThan(0)
  expect(screen.getByRole('region').querySelector('.ai-compatibility-status > span')).toHaveAttribute('aria-hidden', 'true')
})

test.each([['compatible', 'Có thể kết nối (suy theo loại thiết bị)'], ['requires_adapter', 'Cần cáp hoặc bộ chuyển đổi (suy theo loại thiết bị)']])(
  'a %s result read by device type is never labelled as confirmed', (status, label) => {
    view({ ...compatibilityFixture(status), Basis: 'device_type' })
    expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    expect(screen.queryByText(compatibilityLabels.compatible)).not.toBeInTheDocument()
  })

test('a mode checked against the published maximum says so on the verdict and the mode criteria', () => {
  const data = compatibilityFixture('compatible')
  view({ ...data, ModeBasis: 'published_max', Criteria: data.Criteria.map((criterion) => ({ ...criterion, Status: 'compatible' })) })
  const region = screen.getByRole('region')
  expect(region.querySelector('.ai-compatibility-overview')).toHaveTextContent('Chạy được theo mức tối đa hãng công bố')
  // The basic connection keeps its own label; only resolution, refresh rate and the signal mode use the new one.
  expect(screen.getAllByText('Chạy được theo mức tối đa hãng công bố').length).toBe(
    1 + data.Criteria.filter((criterion) => ['resolution', 'refresh_rate', 'signal_mode'].includes(criterion.Id)).length)
  expect(screen.getAllByText(compatibilityLabels.compatible).length).toBeGreaterThan(0)
})

test('basic connectivity and full requested mode have separate results and missing facts', () => {
  view()
  const region = screen.getByRole('region')
  expect(within(region).getByText('Kết nối cơ bản')).toBeInTheDocument()
  expect(within(region).getByText('Chế độ tín hiệu trên toàn bộ đường truyền')).toBeInTheDocument()
  expect(screen.getAllByText('Chưa thể xác nhận').length).toBeGreaterThan(0)
  expect(screen.getByText('Thông số còn thiếu cần kiểm tra')).toBeInTheDocument()
  expect(screen.getByText('Chế độ tín hiệu đầu ra của laptop')).toBeInTheDocument()
  expect(screen.getByText('3840×2160 · 144 Hz')).toBeInTheDocument()
})

test('product names and images link to details and failed/unsafe images fall back safely', () => {
  const fixture = compatibilityFixture()
  fixture.Products[1].ImageUrl = 'javascript:alert(1)'
  const { container } = view(fixture)
  expect(screen.getByRole('link', { name: 'Xem chi tiết ASUS Zenbook UX3405' })).toHaveAttribute('href', '/san-pham/asus-zenbook')
  const image = container.querySelector('img')
  expect(image.closest('a')).toHaveAttribute('href', '/san-pham/asus-zenbook')
  expect(container.querySelector('img[src^="javascript:"]')).toBeNull()
  fireEvent.error(image)
  expect(container.querySelector('img')).toBeNull()
})

test('missing specs do not manufacture port information', () => {
  const fixture = compatibilityFixture()
  fixture.Products.forEach((product) => { product.Facts = [] })
  fixture.Criteria = [{ Id: 'connection', Label: 'Kết nối cơ bản', Status: 'unknown', Summary: 'Chưa đủ dữ liệu để xác nhận.' }]
  fixture.Explanation = 'Bạn cần kiểm tra thông số cổng xuất hình và đầu vào video.'
  fixture.Conditions = []
  view(fixture)
  expect(screen.getAllByText('Chưa rõ thông số cổng kết nối.')).toHaveLength(2)
  expect(screen.queryByText(/HDMI/)).not.toBeInTheDocument()
})

test('AI output and catalog fields remain text, never executable HTML', () => {
  const fixture = compatibilityFixture()
  fixture.Explanation = '<script>alert(1)</script>'
  fixture.Products[0].Facts = ['<img src=x onerror=alert(1)>']
  const { container } = view(fixture)
  expect(screen.getByText('<script>alert(1)</script>')).toBeInTheDocument()
  expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument()
  expect(container.querySelector('script, img[onerror]')).toBeNull()
})

test('saved technical wording preserves uncertainty, signal limits and data-only port restrictions', () => {
  const fixture = compatibilityFixture()
  fixture.Products[0].Facts = ['USB-C chỉ truyền dữ liệu, không xuất hình.']
  const { container } = view(fixture)
  expect(container.textContent).not.toMatch(/dữ liệu|đối chiếu|xác minh|căn cứ/i)
  expect(screen.getByText('USB-C chỉ truyền tệp, không xuất hình.')).toBeInTheDocument()
  expect(screen.getAllByText('Chưa thể xác nhận').length).toBeGreaterThan(0)
  expect(screen.getByText('3840×2160 · 144 Hz')).toBeInTheDocument()
  expect(screen.getByText('Chế độ tín hiệu đầu ra của laptop')).toBeInTheDocument()
})

test('provider failure keeps the result with a customer-facing recovery explanation', () => {
  view({ ...compatibilityFixture(), AnalysisStatus: 'fallback' })
  expect(screen.getByRole('status')).toHaveTextContent('kết quả kiểm tra và các điều kiện kết nối')
  expect(screen.getByText('GIẢI THÍCH KẾT QUẢ')).toBeInTheDocument()
  expect(screen.queryByText('GIẢI THÍCH CỦA AI')).not.toBeInTheDocument()
})

test('explanation selected by the AI uses the same customer-facing heading', () => {
  view({ ...compatibilityFixture(), ExplanationSource: 'gemini' })
  expect(screen.getByText('GIẢI THÍCH KẾT QUẢ')).toBeInTheDocument()
})

test('connector and direct-only conditions that change the verdict are shown with the requested mode', () => {
  const fixture = compatibilityFixture('incompatible')
  fixture.Request = { ...fixture.Request, SourceConnector: 'usb_c', DirectOnly: true }
  view(fixture)
  expect(screen.getByText('3840×2160 · 144 Hz · qua cổng USB-C của laptop · chỉ kết nối trực tiếp, không dùng bộ chuyển đổi'))
    .toBeInTheDocument()
})

test('unknown connector values from history are not displayed', () => {
  const fixture = compatibilityFixture()
  fixture.Request = { SourceConnector: 'toString', DirectOnly: 'yes' }
  view(fixture)
  expect(screen.queryByText(/Yêu cầu cần kiểm tra/)).not.toBeInTheDocument()
})

test('single laptop output check is labelled separately from a complete connection', () => {
  const fixture = compatibilityFixture()
  fixture.CheckType = 'laptop_video_output'
  fixture.Products = fixture.Products.slice(0, 1)
  view(fixture)
  expect(screen.getByText(/Chọn thêm màn hình/)).toBeInTheDocument()
  expect(screen.getAllByRole('link')).toHaveLength(1)
})

test.each([undefined, null, {}, { Version: 2 }, { ...compatibilityFixture(), Products: [] },
  { ...compatibilityFixture(), Status: 'definitely_yes' }, { ...compatibilityFixture(), Criteria: [null] }])(
  'corrupt or unsupported history metadata is ignored without crashing', (value) => {
    expect(render(<MemoryRouter><AiCompatibility compatibility={value} /></MemoryRouter>).container).toBeEmptyDOMElement()
  },
)
