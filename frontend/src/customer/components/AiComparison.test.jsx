import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, test } from 'vitest'
import AiComparison from './AiComparison.jsx'

import { comparisonFixture } from '../../test/ai-comparison.js'

function renderTable(comparison = comparisonFixture()) {
  return render(<MemoryRouter><AiComparison comparison={comparison} /></MemoryRouter>)
}

describe('structured comparison in an AI message', () => {
  test.each([2, 3])('renders %i exact SKU columns, prices, stock, missing specs and detail links', (count) => {
    renderTable(comparisonFixture(count))
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('columnheader')).toHaveLength(count + 1)
    expect(within(table).getAllByText('Chưa rõ')).toHaveLength(count)
    expect(within(table).getByText('Hết hàng')).toBeInTheDocument()
    expect(within(table).getAllByRole('link')).toHaveLength(count)
    expect(screen.getByRole('link', { name: 'Xem chi tiết Laptop 1' })).toHaveAttribute('href', '/san-pham/laptop-1')
    expect(screen.getByText('Nhận xét')).toBeInTheDocument()
    expect(screen.getAllByText(/Mức phù hợp với nhu cầu: 80%/)).toHaveLength(count)
    expect(screen.getAllByText('chưa rõ CPU')).toHaveLength(count)
    expect(table.querySelectorAll('.is-missing')).toHaveLength(count)
  })

  test('horizontal scrolling region is keyboard accessible and images reject unsafe sources', () => {
    const { container } = renderTable()
    expect(screen.getByRole('region', { name: /có thể cuộn ngang/ })).toHaveAttribute('tabindex', '0')
    expect(container.querySelector('.ai-comparison-scroll > table')).toBeInTheDocument()
    expect(container.querySelector('img[src^="javascript:"]')).toBeNull()
    expect(container.querySelector('img[src="/laptop.png"]')).toBeInTheDocument()
  })

  test('AI/catalog strings stay text and never become HTML', () => {
    const comparison = comparisonFixture()
    comparison.Products[0].Strengths = ['<img src=x onerror=alert(1)>']
    comparison.Recommendation = '<script>alert(1)</script>'
    const { container } = renderTable(comparison)
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument()
    expect(container.querySelector('script, img[onerror]')).toBeNull()
  })

  test('provider failure leaves verified comparison and analysis available', () => {
    renderTable({ ...comparisonFixture(), AnalysisStatus: 'fallback' })
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Nhận xét tạm thời chưa hoàn tất')
  })

  test('saved automatic disclaimers and the repeated footer are hidden while missing specs stay visible', () => {
    renderTable({ ...comparisonFixture(), Caveats: [
      'Giá và tồn kho được ghi nhận tại thời điểm tư vấn; xem trang sản phẩm để kiểm tra lại.',
      'Điểm phù hợp là đánh giá theo tiêu chí của VieTech, không phải kết quả đo hiệu năng.',
      'Một số thông số chưa có dữ liệu; chưa thể kết luận đầy đủ về các tiêu chí đó.',
      'Dung lượng pin không xác định thời lượng sử dụng thực tế.',
      'Không kết luận chất lượng ảnh chỉ từ số MP.',
      'Chưa có kiểm thử phần mềm thực tế; không cam kết chạy mượt Android Studio, trò chơi hoặc ứng dụng cụ thể.',
      'Các phiên bản chỉ khác màu sắc có cùng thông số và giá; bảng dùng MacBook Air M4: Ánh sao · 256GB.',
    ] })
    expect(screen.queryByText('Điều cần lưu ý')).not.toBeInTheDocument()
    expect(screen.queryByText('Về yêu cầu của bạn')).not.toBeInTheDocument()
    expect(screen.queryByText(/Giá và tồn kho|Nhận xét dựa|Điểm phù hợp là|chỉ khác màu|Dung lượng pin/)).not.toBeInTheDocument()
    expect(screen.queryByText(/kiểm thử phần mềm|chưa thể kết luận đầy đủ/)).not.toBeInTheDocument()
    expect(screen.getAllByText('chưa rõ CPU')).toHaveLength(2)
    expect(within(screen.getByRole('table')).getAllByText('Chưa rõ')).toHaveLength(2)
  })

  test('an uncertainty about the requested software stays visible without unrelated notes', () => {
    const note = 'Chưa có kết quả chạy thử Android Studio trên các mẫu này để xác nhận mức đáp ứng bạn hỏi.'
    renderTable({ ...comparisonFixture(), Caveats: [null, '', note] })
    expect(screen.getByText('Về yêu cầu của bạn')).toBeInTheDocument()
    expect(screen.getByText(note)).toBeInTheDocument()
    expect(screen.queryByText(/Nhận xét dựa/)).not.toBeInTheDocument()
  })

  test('old saved wording stays focused on products without completeness percentages or processing terms', () => {
    const { container } = renderTable()
    expect(container.textContent).not.toMatch(/dữ liệu|đối chiếu|xác minh|căn cứ|Đủ 90%/i)
    expect(screen.getAllByText('Điểm mạnh')).toHaveLength(2)
    expect(screen.getAllByText('Điểm cần cân nhắc')).toHaveLength(2)
    expect(screen.queryByText('Chưa thể chọn một mẫu phù hợp hơn với nhu cầu của bạn.')).not.toBeInTheDocument()
    expect(screen.queryByText('Gợi ý theo nhu cầu')).not.toBeInTheDocument()
  })

  test('keeps a specific recommendation while removing an empty automatic recommendation section', () => {
    const recommendation = 'Laptop 1 phù hợp hơn nhờ RAM 16 GB và giá thấp hơn.'
    renderTable({ ...comparisonFixture(), Recommendation: recommendation })
    expect(screen.getByText('Gợi ý theo nhu cầu')).toBeInTheDocument()
    expect(screen.getByText(recommendation)).toBeInTheDocument()
  })

  test('camera modules use separate lines and each product keeps its own named assessment', () => {
    const comparison = comparisonFixture()
    comparison.Products[0].ProductName = 'OPPO Reno16 F'
    comparison.Products[1].ProductName = 'OPPO Find X5 Pro'
    comparison.Rows.push({ Key:'camera', Label:'Camera sau', Values:[
      '50 MP OIS, f/1.8, 8 MP góc rộng, f/2.2, 50 MP OIS Tele, f/2.8',
      'Camera chính: 50 MP, f/1.7; Camera góc rộng: 50 MP, f/2.2; FOV 112°; Camera tele: 13 MP, f/2.4',
    ] })
    comparison.Differences = ['Camera sau: mẫu 1: camera A, mẫu 2: camera B',
      'RAM: OPPO Find X5 Pro có 12 GB, hơn 4 GB để giữ nhiều ứng dụng đang mở.']
    comparison.Products[0].Strengths = ['CPU: Dimensity 7300-Energy, phục vụ ứng dụng hằng ngày.']
    comparison.Products[1].Strengths = ['RAM: 12 GB, hỗ trợ giữ nhiều ứng dụng đang mở.']
    renderTable(comparison)
    const cameraRow = screen.getByRole('rowheader', { name:'Camera sau' }).closest('tr')
    const cells = within(cameraRow).getAllByRole('cell')
    expect(cells[0].querySelectorAll('.ai-comparison-spec-lines > span')).toHaveLength(3)
    expect(cells[1].querySelectorAll('.ai-comparison-spec-lines > span')).toHaveLength(3)
    expect(within(cells[1]).getByText('Camera góc rộng: 50 MP, f/2.2, FOV 112°')).toBeInTheDocument()
    const first = screen.getByRole('region', { name:'Nhận xét OPPO Reno16 F' })
    const second = screen.getByRole('region', { name:'Nhận xét OPPO Find X5 Pro' })
    expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(within(first).getByText(/Dimensity 7300/)).toBeInTheDocument()
    expect(within(second).getByText(/RAM: 12 GB/)).toBeInTheDocument()
    expect(screen.queryByText(/mẫu [12]:/)).not.toBeInTheDocument()
  })

  test('default history hides color as a criterion, explicit requests retain it', () => {
    const comparison = comparisonFixture()
    comparison.Rows.push({ Key:'color', Label:'Màu sắc', Values:['Đen', 'Trắng'] })
    const view = renderTable(comparison)
    expect(screen.queryByRole('rowheader', { name:'Màu sắc' })).not.toBeInTheDocument()
    view.unmount()
    renderTable({ ...comparison, Needs:['màu sắc'] })
    expect(screen.getByRole('rowheader', { name:'Màu sắc' })).toBeInTheDocument()
  })

  test.each([null, {}, { Version: 2 }, { ...comparisonFixture(), Products: [] },
    { ...comparisonFixture(), Rows: [{ Label: 'RAM', Values: ['16 GB'] }] }])('ignores malformed history metadata safely', (value) => {
    const { container } = renderTable(value)
    expect(container).toBeEmptyDOMElement()
  })
})
