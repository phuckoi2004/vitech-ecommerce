import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { expect, test, vi } from 'vitest'
import RichTextEditor from './RichTextEditor.jsx'

function renderEditor(props = {}) {
  const onChange = vi.fn()
  const view = render(<RichTextEditor id="description" label="Mô tả" value="" onChange={onChange} {...props} />)
  const content = screen.getByRole('textbox', { name: 'Mô tả' })
  return { ...view, onChange, content, editor: content.editor }
}

// Select the text the way an administrator highlights it before using the toolbar.
function select(editor, text) {
  let from = -1
  editor.state.doc.descendants((node, pos) => {
    if (from < 0 && node.isText && node.text.includes(text)) from = pos + node.text.indexOf(text)
  })
  act(() => { editor.commands.setTextSelection({ from, to: from + text.length }) })
}

const lastHtml = (onChange) => onChange.mock.calls.at(-1)[0]
const png = (name = 'anh.png', type = 'image/png', size = 1024) => new File([new Uint8Array(size)], name, { type })

test('legacy plain-text descriptions load as separate paragraphs without being reported as an edit', () => {
  const { content, onChange } = renderEditor({ value: 'Đoạn một\ndòng hai\n\nĐoạn hai' })
  expect(content.querySelectorAll('p')).toHaveLength(2)
  expect(content.querySelector('p').innerHTML).toBe('Đoạn một<br>dòng hai')
  expect(onChange).not.toHaveBeenCalled()
})

test('highlighted text gets emphasis, a font size and a font from the toolbar instead of headings', () => {
  const { editor, onChange } = renderEditor({ value: '<p>Thiết kế cao cấp</p><p>Pin bền bỉ</p><p>Sạc nhanh</p>' })
  expect(screen.queryByRole('button', { name: /H2|H3|Đề mục/ })).not.toBeInTheDocument()
  select(editor, 'cao cấp')
  fireEvent.click(screen.getByRole('button', { name: 'In đậm (Ctrl + B)' }))
  expect(lastHtml(onChange)).toContain('<p>Thiết kế <strong>cao cấp</strong></p>')
  expect(screen.getByRole('button', { name: 'In đậm (Ctrl + B)' })).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(screen.getByRole('button', { name: 'In nghiêng (Ctrl + I)' }))
  fireEvent.click(screen.getByRole('button', { name: 'Gạch chân (Ctrl + U)' }))
  fireEvent.change(screen.getByRole('combobox', { name: 'Cỡ chữ' }), { target: { value: '24px' } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Phông chữ' }), { target: { value: '"Times New Roman", Times, serif' } })
  expect(lastHtml(onChange)).toContain('<p>Thiết kế <span style="font-family: &quot;Times New Roman&quot;, Times, serif; font-size: 24px;"><strong><em><u>cao cấp</u></em></strong></span></p>')
  expect(screen.getByRole('combobox', { name: 'Cỡ chữ' })).toHaveValue('24px')
  expect(screen.getByRole('combobox', { name: 'Phông chữ' })).toHaveValue('"Times New Roman", Times, serif')
  fireEvent.change(screen.getByRole('combobox', { name: 'Cỡ chữ' }), { target: { value: '' } })
  expect(lastHtml(onChange)).toContain('<span style="font-family: &quot;Times New Roman&quot;, Times, serif;"><strong>')
  select(editor, 'Sạc')
  fireEvent.click(screen.getByRole('button', { name: 'Danh sách dấu chấm' }))
  fireEvent.click(screen.getByRole('button', { name: 'Căn giữa' }))
  expect(lastHtml(onChange)).toContain('<ul><li><p style="text-align: center;">Sạc nhanh</p></li></ul>')
  fireEvent.click(screen.getByRole('button', { name: 'Danh sách đánh số' }))
  expect(lastHtml(onChange)).toContain('<ol><li>')
  fireEvent.click(screen.getByRole('button', { name: 'Hoàn tác (Ctrl + Z)' }))
  expect(lastHtml(onChange)).toContain('<ul><li>')
  act(() => { editor.commands.setTextSelection({ from: 1, to: editor.state.doc.firstChild.nodeSize - 1 }) })
  fireEvent.click(screen.getByRole('button', { name: 'Xóa định dạng' }))
  expect(lastHtml(onChange)).toMatch(/^<p>Thiết kế cao cấp<\/p>/)
})

test('a description saved with headings opens as bold text of a similar size and keeps that look when saved', () => {
  const { content, editor, onChange } = renderEditor({ value: '<h2>Thiết kế</h2><p>Nội dung</p>' })
  expect(content.querySelector('h2')).toBeNull()
  expect(content.querySelector('span[style]')).toHaveStyle({ fontSize: '20px' })
  expect(content.querySelector('span[style] strong')).toHaveTextContent('Thiết kế')
  select(editor, 'Nội dung')
  fireEvent.click(screen.getByRole('button', { name: 'In đậm (Ctrl + B)' }))
  expect(lastHtml(onChange)).toBe('<p><span style="font-size: 20px;"><strong>Thiết kế</strong></span></p><p><strong>Nội dung</strong></p>')
})

test('a link is added to highlighted text, invalid addresses are refused and the link can be removed', () => {
  const { editor, onChange } = renderEditor({ value: '<p>Xem khuyến mãi</p>' })
  select(editor, 'khuyến mãi')
  fireEvent.click(screen.getByRole('button', { name: 'Chèn hoặc sửa liên kết' }))
  const address = screen.getByRole('textbox', { name: 'Địa chỉ liên kết' })
  fireEvent.change(address, { target: { value: 'javascript:alert(1)' } })
  fireEvent.keyDown(address, { key: 'Enter' })
  expect(screen.getByRole('alert')).toHaveTextContent('Nhập địa chỉ hợp lệ')
  expect(onChange).not.toHaveBeenCalled()
  fireEvent.change(address, { target: { value: 'vietech.vn/khuyen-mai' } })
  fireEvent.keyDown(address, { key: 'Enter' })
  expect(lastHtml(onChange)).toBe('<p>Xem <a target="_blank" rel="noopener noreferrer nofollow" href="https://vietech.vn/khuyen-mai">khuyến mãi</a></p>')
  expect(screen.queryByRole('textbox', { name: 'Địa chỉ liên kết' })).not.toBeInTheDocument()
  select(editor, 'khuyến')
  fireEvent.click(screen.getByRole('button', { name: 'Chèn hoặc sửa liên kết' }))
  expect(screen.getByRole('textbox', { name: 'Địa chỉ liên kết' })).toHaveValue('https://vietech.vn/khuyen-mai')
  fireEvent.click(screen.getByRole('button', { name: 'Gỡ liên kết' }))
  expect(lastHtml(onChange)).toBe('<p>Xem khuyến mãi</p>')
})

test('an uploaded image is inserted where the cursor is, with its description, while saving is blocked', async () => {
  let finish
  const onUploadImage = vi.fn(() => new Promise((resolve) => { finish = resolve }))
  const onUploadBusy = vi.fn()
  const { editor, onChange } = renderEditor({ value: '<p>Trước ảnh</p><p>Sau ảnh</p>', onUploadImage, onUploadBusy })
  act(() => { editor.commands.setTextSelection(editor.state.doc.firstChild.nodeSize - 1) })
  fireEvent.click(screen.getByRole('button', { name: 'Chèn hoặc sửa ảnh' }))
  fireEvent.change(screen.getByRole('textbox', { name: 'Mô tả ảnh' }), { target: { value: 'Mặt trước máy' } })
  const file = png('mat-truoc.png')
  fireEvent.change(screen.getByLabelText('Chọn ảnh để chèn vào mô tả'), { target: { files: [file] } })
  expect(onUploadImage).toHaveBeenCalledWith(file)
  expect(onUploadBusy).toHaveBeenLastCalledWith(true)
  expect(await screen.findByRole('status')).toHaveTextContent('Đang tải ảnh…')
  await act(async () => { finish('https://cdn.example/products/mat-truoc.png') })
  expect(lastHtml(onChange)).toBe('<p>Trước ảnh</p><img src="https://cdn.example/products/mat-truoc.png" alt="Mặt trước máy"><p>Sau ảnh</p>')
  expect(onUploadBusy).toHaveBeenLastCalledWith(false)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.queryByRole('textbox', { name: 'Mô tả ảnh' })).not.toBeInTheDocument()
})

test('unsupported or oversized files are refused before uploading and upload failures are reported', async () => {
  const onUploadImage = vi.fn().mockRejectedValueOnce(new Error('Không tải được ảnh sản phẩm lên kho lưu trữ.'))
  const { onChange } = renderEditor({ value: '<p>Nội dung</p>', onUploadImage })
  fireEvent.click(screen.getByRole('button', { name: 'Chèn hoặc sửa ảnh' }))
  const picker = screen.getByLabelText('Chọn ảnh để chèn vào mô tả')
  fireEvent.change(picker, { target: { files: [png('dong.gif', 'image/gif')] } })
  expect(screen.getByRole('alert')).toHaveTextContent('Chọn ảnh JPG, PNG hoặc WEBP, tối đa 2 MB mỗi ảnh.')
  fireEvent.change(picker, { target: { files: [png('lon.png', 'image/png', 2 * 1024 * 1024 + 1)] } })
  expect(onUploadImage).not.toHaveBeenCalled()
  fireEvent.change(picker, { target: { files: [png()] } })
  expect(await screen.findByRole('alert')).toHaveTextContent('Không tải được ảnh sản phẩm lên kho lưu trữ.')
  expect(onChange).not.toHaveBeenCalled()
})

test('an image file pasted into the description is uploaded and inserted', async () => {
  const onUploadImage = vi.fn().mockResolvedValue('https://cdn.example/products/dan.webp')
  const { content, editor, onChange } = renderEditor({ value: '<p>Nội dung</p>', onUploadImage })
  act(() => { editor.commands.focus('end') })
  const file = png('dan.webp', 'image/webp')
  fireEvent.paste(content, { clipboardData: { files: [file], types: ['Files'], getData: () => '' } })
  await waitFor(() => expect(lastHtml(onChange)).toBe('<p>Nội dung</p><img src="https://cdn.example/products/dan.webp" alt=""><p></p>'))
  expect(onUploadImage).toHaveBeenCalledWith(file)
})

test('an image can be inserted from a web address and its description edited later', () => {
  const { content, editor, onChange } = renderEditor({ value: '<p>Nội dung</p>' })
  expect(screen.queryByText('Tải ảnh từ máy')).not.toBeInTheDocument()
  act(() => { editor.commands.focus('end') })
  fireEvent.click(screen.getByRole('button', { name: 'Chèn hoặc sửa ảnh' }))
  const address = screen.getByRole('textbox', { name: 'Đường dẫn ảnh' })
  fireEvent.change(address, { target: { value: 'data:image/png;base64,AAAA' } })
  fireEvent.click(screen.getByRole('button', { name: 'Chèn ảnh' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Nhập đường dẫn ảnh bắt đầu bằng https://')
  fireEvent.change(address, { target: { value: 'cdn.vietech.vn/a.png' } })
  fireEvent.keyDown(address, { key: 'Enter' })
  expect(lastHtml(onChange)).toContain('<img src="https://cdn.vietech.vn/a.png" alt="">')
  expect(content.querySelector('img')).toBeInTheDocument()
  act(() => { editor.commands.setNodeSelection(editor.state.doc.firstChild.nodeSize) })
  fireEvent.click(screen.getByRole('button', { name: 'Chèn hoặc sửa ảnh' }))
  expect(screen.getByRole('textbox', { name: 'Đường dẫn ảnh' })).toHaveValue('https://cdn.vietech.vn/a.png')
  fireEvent.change(screen.getByRole('textbox', { name: 'Mô tả ảnh' }), { target: { value: 'Hộp máy' } })
  fireEvent.click(screen.getByRole('button', { name: 'Cập nhật ảnh' }))
  expect(lastHtml(onChange)).toContain('<img src="https://cdn.vietech.vn/a.png" alt="Hộp máy">')
})

test('line breaks and new paragraphs keep the spacing the administrator typed', () => {
  const { editor, onChange } = renderEditor({ value: '<p>Dòng đầu</p>' })
  act(() => { editor.commands.focus('end') })
  fireEvent.click(screen.getByRole('button', { name: 'Xuống dòng trong đoạn (Shift + Enter)' }))
  act(() => { editor.commands.insertContent('dòng tiếp') })
  act(() => { editor.commands.splitBlock() })
  act(() => { editor.commands.splitBlock() })
  act(() => { editor.commands.insertContent('Đoạn mới') })
  expect(lastHtml(onChange)).toBe('<p>Dòng đầu<br>dòng tiếp</p><p></p><p>Đoạn mới</p>')
})

test('clearing the editor reports an empty description', () => {
  const { editor, onChange } = renderEditor({ value: '<p>Nội dung</p>' })
  act(() => { editor.commands.clearContent(true) })
  expect(lastHtml(onChange)).toBe('')
})

test('a description loaded from another product replaces the content without counting as an edit', () => {
  const onChange = vi.fn()
  const { rerender } = render(<RichTextEditor id="description" label="Mô tả" value="<p>Sản phẩm A</p>" onChange={onChange} />)
  rerender(<RichTextEditor id="description" label="Mô tả" value={'Sản phẩm B\n\nĐoạn hai'} onChange={onChange} />)
  expect(screen.getByRole('textbox', { name: 'Mô tả' })).toHaveTextContent('Sản phẩm BĐoạn hai')
  expect(onChange).not.toHaveBeenCalled()
})

test('typing keeps the caret: the parent value round-trips without resetting the editor', () => {
  function Harness() {
    const [value, setValue] = useState('<p>Ban đầu</p>')
    return <><RichTextEditor id="description" label="Mô tả" value={value} onChange={setValue} /><output>{value}</output></>
  }
  render(<Harness />)
  const editor = screen.getByRole('textbox', { name: 'Mô tả' }).editor
  act(() => { editor.commands.focus('end') })
  act(() => { editor.commands.insertContent(' thêm') })
  act(() => { editor.commands.insertContent(' nữa') })
  expect(document.querySelector('output')).toHaveTextContent('<p>Ban đầu thêm nữa</p>')
  expect(editor.state.selection.from).toBe(editor.state.doc.content.size - 1)
})

test('read-only mode shows the saved formatting without the toolbar', () => {
  const { content } = renderEditor({ readOnly: true, value: '<p><strong><span style="font-size: 24px">Lớn</span></strong></p><img src="https://cdn.example/a.png" alt="Ảnh">' })
  expect(screen.queryByRole('toolbar')).not.toBeInTheDocument()
  expect(content).toHaveAttribute('contenteditable', 'false')
  expect(content.querySelector('span[style]')).toHaveStyle({ fontSize: '24px' })
  expect(content.querySelector('span[style] strong')).toHaveTextContent('Lớn')
  expect(content.querySelector('img')).toHaveAttribute('alt', 'Ảnh')
})

test('while saving the content and the toolbar are locked', () => {
  const { content } = renderEditor({ disabled: true, value: '<p>Đang lưu</p>' })
  expect(content).toHaveAttribute('contenteditable', 'false')
  for (const control of [...screen.getAllByRole('button'), ...screen.getAllByRole('combobox')]) expect(control).toBeDisabled()
})
