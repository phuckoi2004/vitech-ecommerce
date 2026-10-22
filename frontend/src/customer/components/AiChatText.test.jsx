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
