import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import AiChatText from './AiChatText.jsx'

test('answers show short sections, emphasis and separate lists for offers and steps', () => {
  const { container } = render(<AiChatText content={'### Khuyến mãi\n\n**Galaxy A17** đang giảm **300.000 đ**.\n\n- Giá đã gồm giảm tự động.\n- Mã SAVE100 dùng ở giỏ hàng.\n\n### Cách đổi sản phẩm\n\n1. Chọn đơn đã giao.\n2. Gửi yêu cầu và ảnh minh chứng.'} />)
  expect(screen.getAllByRole('heading').map((node) => node.textContent)).toEqual(['Khuyến mãi', 'Cách đổi sản phẩm'])
  expect(container.querySelector('strong')).toHaveTextContent('Galaxy A17')
  expect(container.querySelectorAll('ul li')).toHaveLength(2)
  expect(container.querySelectorAll('ol li')).toHaveLength(2)
  expect(container.querySelector('p')).toHaveTextContent('Galaxy A17 đang giảm 300.000 đ.')
})

test('saved plain-text answers keep readable paragraphs and old bullet markers', () => {
  const { container } = render(<AiChatText content={'Khuyến mãi:\n• Ưu đãi hiện tại.\n• Điều kiện áp dụng.\n\nBạn cần xem sản phẩm nào?\nMình sẽ kiểm tra thêm.'} />)
  expect(screen.getByRole('heading', { name: 'Khuyến mãi' })).toBeInTheDocument()
  expect(container.querySelectorAll('ul li')).toHaveLength(2)
  expect(container.querySelector('p').textContent).toContain('nào?\nMình')
})

test('model HTML, links and scripts remain inert text, including inside bold formatting', () => {
  const { container } = render(<AiChatText content={'**<img src=x onerror=alert(1)>**\n\n<script>alert(1)</script>\n[Nhấn vào](javascript:alert(1))'} />)
  expect(container.querySelector('img, script, a, iframe')).toBeNull()
  expect(container).toHaveTextContent('<script>alert(1)</script>')
  expect(container.querySelector('strong')).toHaveTextContent('<img src=x onerror=alert(1)>')
})

test('unfinished formatting from the model keeps all of the original words', () => {
  const tick = String.fromCharCode(96)
  const { container } = render(<AiChatText content={'**Thông tin chưa đóng\n\n__Mã chưa đóng\n\n' + tick + 'mã chưa đóng'} />)
  expect(container.textContent).toContain('**Thông tin chưa đóng')
  expect(container.textContent).toContain('__Mã chưa đóng')
  expect(container.textContent).toContain(tick + 'mã chưa đóng')
})

test('the old comparison introduction is presented directly while product names and list order stay intact', () => {
  const { container } = render(<AiChatText content={'Mình đã đối chiếu các phiên bản sau bằng dữ liệu hiện tại của VieTech:\n1. iPhone 17 Pro — Bạc · 256 GB.\n2. Samsung Galaxy S26 Ultra — Đen · 256 GB.\n\nChưa đủ dữ liệu để xác nhận thời lượng pin.'} />)
  expect(container.textContent).not.toMatch(/dữ liệu|đối chiếu|xác minh|căn cứ/i)
  expect(screen.getByRole('heading', { name: 'So sánh các mẫu sau' })).toBeInTheDocument()
  expect(container.querySelectorAll('ol li')).toHaveLength(2)
  expect(container.querySelector('ol li')).toHaveTextContent('iPhone 17 Pro — Bạc · 256 GB.')
  expect(screen.getByText('Chưa thể xác nhận thời lượng pin.')).toBeInTheDocument()
})

test('wording cleanup preserves indented list continuations and negative video capabilities', () => {
  const { container } = render(<AiChatText content={'- Cổng USB-C:\n  chỉ truyền dữ liệu, không xuất hình.\n- HDMI 2.0: 3840×2160 @ 60 Hz.'} />)
  expect(container.querySelectorAll('ul li')).toHaveLength(2)
  expect(container.querySelector('ul li')).toHaveTextContent('Cổng USB-C: chỉ truyền tệp, không xuất hình.')
  expect(container.querySelectorAll('p')).toHaveLength(0)
  expect(container).toHaveTextContent('HDMI 2.0: 3840×2160 @ 60 Hz.')
})

test('the removed default sentence disappears from saved messages without adding another sentence', () => {
  const { container } = render(<AiChatText content={'RAM: 16 GB.\n\nChưa thể chọn một mẫu phù hợp hơn với nhu cầu của bạn.'} />)
  expect(container.textContent).toBe('RAM: 16 GB.')
})
