import { render, screen, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import ProductInformation from './ProductInformation.jsx'

const product = { ProductId: 'p1', Name: 'Điện thoại kiểm thử', Specifications: null }

function renderDescription(Description) {
  render(<ProductInformation product={{ ...product, Description }} variant={null} />)
  return screen.getByRole('region', { name: 'Đặc điểm nổi bật' })
}

test('highlights choose key selling specifications even when JSON starts with GPS, WiFi and recording', () => {
  const Specifications = {
    GPS: 'Có', RAM: '12GB', WiFi: 'Wi-Fi 7', 'Ghi âm': 'Mặc định', 'Loại SIM': 'eSIM',
    'Bộ nhớ trong': '256GB', 'Chip xử lý': 'Chip từ API', 'Dung lượng pin': '4300 mAh',
    'Tần số quét': '120 Hz', 'Loại tấm nền': 'AMOLED', 'Kích thước màn hình': '6.3 inch',
    'Độ phân giải camera sau': '50 MP', 'Độ phân giải camera trước': '12 MP',
    'Công suất sạc hỗ trợ tối đa': '25 W',
  }
  const view = render(<ProductInformation product={{ ...product, Specifications }} variant={{ Storage: '256GB', Color: 'Đen' }} />)
  const expected = [
    'Màn hình: 6.3 inch · AMOLED · 120 Hz', 'Hiệu năng: Chip từ API · RAM 12GB',
    'Camera: Sau 50 MP · Trước 12 MP', 'Bộ nhớ: 256GB', 'Pin và sạc: 4300 mAh · Sạc 25 W',
  ]
  const highlights = () => [...view.container.querySelectorAll('.pd-highlights li')].map((item) => item.textContent)
  expect(highlights()).toEqual(expected)
  expect(view.container.querySelector('.pd-quick-specs')).not.toHaveTextContent(/GPS|WiFi|Ghi âm|Màu sắc/)
  view.rerender(<ProductInformation product={{ ...product, Specifications: Object.fromEntries(Object.entries(Specifications).reverse()) }}
    variant={{ Storage: '256GB', Color: 'Đen' }} />)
  expect(highlights()).toEqual(expected)
})

test('selecting another storage updates both highlights and the existing memory row without mutating product data', () => {
  const Specifications = { 'Bộ nhớ trong': '256GB', RAM: '12GB' }
  const view = render(<ProductInformation product={{ ...product, Specifications }} variant={{ Storage: '256GB' }} />)
  view.rerender(<ProductInformation product={{ ...product, Specifications }} variant={{ Storage: '512GB' }} />)
  expect(view.container.querySelector('.pd-highlights')).toHaveTextContent('Bộ nhớ: 512GB')
  const specs = screen.getByRole('region', { name: 'Thông số kỹ thuật' })
  expect(within(specs).getByRole('cell', { name: '512GB' })).toBeInTheDocument()
  expect(within(specs).queryByRole('cell', { name: '256GB' })).not.toBeInTheDocument()
  expect(within(specs).getAllByRole('row')).toHaveLength(2)
  expect(Specifications['Bộ nhớ trong']).toBe('256GB')
})

test('without relevant specifications the highlights show a pending state instead of unrelated metadata', () => {
  const view = render(<ProductInformation product={{ ...product, Specifications: { GPS: 'Có', 'Ghi âm': 'Mặc định', 'Màu sắc': 'Đen' } }}
    variant={{ Color: 'Đen' }} />)
  const highlights = view.container.querySelector('.pd-highlights')
  expect(highlights).toHaveTextContent('Đang cập nhật đặc điểm sản phẩm.')
  expect(highlights.querySelector('ul')).toBeNull()
  expect(view.container.querySelector('.pd-quick-specs')).toBeNull()
})

test('laptop specifications and unit-bearing field names use the same real-data groups', () => {
  const Specifications = { Processor: 'CPU từ API', 'RAM (GB)': '16GB', SSD: '512GB', 'Screen_size': '14 inch',
    'Refresh rate': '90 Hz', Webcam: '1080p', 'Battery capacity': '' }
  const view = render(<ProductInformation product={{ ...product, Specifications }} variant={null} />)
  expect([...view.container.querySelectorAll('.pd-highlights li')].map(item => item.textContent)).toEqual([
    'Màn hình: 14 inch · 90 Hz', 'Hiệu năng: CPU từ API · RAM 16GB', 'Camera: 1080p', 'Bộ nhớ: 512GB',
  ])
})

test('combined screen details do not repeat the same panel or refresh rate', () => {
  const Specifications = { 'Màn hình': '6.7 inch AMOLED 120 Hz', 'Loại tấm nền': 'amoled', 'Tần số quét': '120 Hz' }
  const view = render(<ProductInformation product={{ ...product, Specifications }} variant={null} />)
  expect(view.container.querySelector('.pd-highlights li')).toHaveTextContent('Màn hình: 6.7 inch AMOLED 120 Hz')
  expect(view.container.querySelector('.pd-highlights li').textContent).not.toContain(' · ')
})

test('formatted descriptions from the admin keep headings, emphasis, lists, alignment and links', () => {
  const section = renderDescription('<h2>Thiết kế sang trọng</h2><p>Khung <strong>titan</strong>, <em>mặt kính</em> <u>Ceramic</u>.</p>'
    + '<p></p><h3>Hiệu năng</h3><ul><li><p>Chip A19</p></li><li><p>RAM 12GB</p></li></ul><ol><li><p>Bước một</p></li></ol>'
    + '<p style="text-align: center">Ưu đãi tại <a href="https://vietech.vn/khuyen-mai">VieTech</a> và <a href="/tin-tuc">tin tức</a>.</p>')
  const description = section.querySelector('.pd-description-text')
  expect(within(description).getByRole('heading', { level: 2, name: 'Thiết kế sang trọng' })).toBeInTheDocument()
  expect(within(description).getByRole('heading', { level: 3, name: 'Hiệu năng' })).toBeInTheDocument()
  expect(within(description).getByText('titan').tagName).toBe('STRONG')
  expect(within(description).getByText('mặt kính').tagName).toBe('EM')
  expect(within(description).getByText('Ceramic').tagName).toBe('U')
  expect(within(description).getAllByRole('listitem').map((item) => item.textContent)).toEqual(['Chip A19', 'RAM 12GB', 'Bước một'])
  expect(within(description).getByText(/Ưu đãi tại/)).toHaveStyle({ textAlign: 'center' })
  const external = within(description).getByRole('link', { name: 'VieTech' })
  expect(external).toHaveAttribute('href', 'https://vietech.vn/khuyen-mai')
  expect(external).toHaveAttribute('target', '_blank')
  expect(external).toHaveAttribute('rel', 'noopener noreferrer nofollow')
  expect(within(description).getByRole('link', { name: 'tin tức' })).not.toHaveAttribute('target')
  // The blank line typed between paragraphs is kept.
  expect([...description.children].map((child) => child.tagName)).toEqual(['H2', 'P', 'P', 'H3', 'UL', 'OL', 'P'])
})

test('font sizes, fonts and images chosen in the admin editor are shown to customers', () => {
  const section = renderDescription('<p><span style="font-family: Georgia, serif; font-size: 24px"><strong>Thiết kế</strong></span></p>'
    + '<p>Nội dung <span style="font-size: 12px">chú thích</span></p><img src="https://cdn.example/products/mat-sau.png" alt="Mặt sau">')
  const description = section.querySelector('.pd-description-text')
  expect(within(description).getByText('Thiết kế').parentElement).toHaveStyle({ fontSize: '24px', fontFamily: 'Georgia, serif' })
  expect(within(description).getByText('chú thích')).toHaveStyle({ fontSize: '12px' })
  const image = within(description).getByRole('img', { name: 'Mặt sau' })
  expect(image).toHaveAttribute('src', 'https://cdn.example/products/mat-sau.png')
  expect(image).toHaveAttribute('loading', 'lazy')
})

test('unsafe HTML in a description is removed before it reaches the page', () => {
  const section = renderDescription('<p>An toàn<script>window.hacked = true</script><img src="x" onerror="window.hacked = true"></p>'
    + '<p onmouseover="window.hacked = true" style="position: fixed; inset: 0">Phủ trang</p><a href="javascript:window.hacked = true">Bấm</a>'
    + '<iframe src="https://evil.example"></iframe><form><input name="password"></form><svg><script>1</script></svg>')
  const description = section.querySelector('.pd-description-text')
  expect(description).toHaveTextContent('An toànPhủ trangBấm')
  expect(description.querySelector('script, img, iframe, form, input, svg, [onerror], [onmouseover], [style]')).toBeNull()
  expect(within(description).queryByRole('link')).not.toBeInTheDocument()
  expect(window.hacked).toBeUndefined()
})

test('legacy plain-text descriptions still show as readable paragraphs', () => {
  const section = renderDescription('Đoạn mô tả thứ nhất.\nDòng tiếp theo.\n\nĐoạn thứ hai & giá < 10 triệu.')
  const paragraphs = section.querySelectorAll('.pd-description-text p')
  expect(paragraphs).toHaveLength(2)
  expect(paragraphs[0].innerHTML).toBe('Đoạn mô tả thứ nhất.<br>Dòng tiếp theo.')
  expect(paragraphs[1]).toHaveTextContent('Đoạn thứ hai & giá < 10 triệu.')
})

test('legacy text with inline tags keeps both its emphasis and its paragraphs', () => {
  const section = renderDescription('Pin <b>5000mAh</b>\nSạc nhanh\n\nĐoạn hai<script>window.hacked = true</script>')
  const paragraphs = section.querySelectorAll('.pd-description-text p')
  expect([...paragraphs].map((paragraph) => paragraph.innerHTML)).toEqual(['Pin <b>5000mAh</b><br>Sạc nhanh', 'Đoạn hai'])
  expect(window.hacked).toBeUndefined()
})

test('an empty or blank formatted description shows the pending message', () => {
  for (const Description of [null, '', '<p></p>', '<p><script>x</script></p>']) {
    const section = renderDescription(Description)
    expect(within(section).getByText('Đang cập nhật mô tả sản phẩm.')).toBeInTheDocument()
    section.closest('.pd-information').parentElement.remove()
  }
})
