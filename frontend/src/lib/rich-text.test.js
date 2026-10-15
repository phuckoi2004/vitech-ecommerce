import { describe, expect, test } from 'vitest'
import { headingsToParagraphs, isRichTextHtml, normalizeImageUrl, normalizeLinkUrl, normalizeRichText, plainTextToHtml, richTextToHtml } from './rich-text.js'

describe('legacy plain-text descriptions', () => {
  test('blank lines become paragraphs, single line breaks stay inside the paragraph and text is escaped', () => {
    expect(plainTextToHtml('Đoạn một\ndòng hai\r\n\r\n  Đoạn <b>hai</b> & "ba"  \n\n\n')).toBe(
      '<p>Đoạn một<br>dòng hai</p><p>Đoạn &lt;b&gt;hai&lt;/b&gt; &amp; &quot;ba&quot;</p>')
  })

  test('text with comparison signs is not mistaken for HTML and is saved unchanged', () => {
    const legacy = 'RAM < 8GB thì chạy chậm.\n\nPin > 5000mAh.'
    expect(isRichTextHtml(legacy)).toBe(false)
    expect(normalizeRichText(`  ${legacy}  `)).toBe(legacy)
    expect(richTextToHtml(legacy)).toBe('<p>RAM &lt; 8GB thì chạy chậm.</p><p>Pin &gt; 5000mAh.</p>')
  })

  test('inline tags typed into the former textarea keep their line structure', () => {
    expect(richTextToHtml('Pin <b>lớn</b>\nSạc nhanh\n\nĐoạn <i>hai</i> < 3')).toBe('<p>Pin <b>lớn</b><br>Sạc nhanh</p><p>Đoạn <i>hai</i> &lt; 3</p>')
    expect(richTextToHtml('<p>Đã có\nkhối</p>')).toBe('<p>Đã có\nkhối</p>')
  })
})

describe('formatted descriptions', () => {
  test('editor formatting survives sanitizing', () => {
    const html = '<p style="text-align: center"><strong>Đậm</strong> <em>nghiêng</em> <u>gạch chân</u><br>dòng mới</p>'
      + '<p><span style="font-size: 20px; font-family: &quot;Times New Roman&quot;, Times, serif">Chữ lớn</span> <span style="font-family: Arial, Helvetica, sans-serif">Arial</span></p>'
      + '<ul><li><p>Một</p></li></ul><p></p><ol><li><p>Hai</p></li></ol>'
      + '<img src="https://cdn.example/san-pham/mat-truoc.webp" alt="Mặt trước" loading="lazy" decoding="async"><p>Chip mới</p>'
    expect(richTextToHtml(html)).toBe(html)
    expect(normalizeRichText(html)).toBe(html)
  })

  test('descriptions saved with headings still display them', () => {
    expect(richTextToHtml('<h2>Thiết kế</h2><h3 style="text-align: center">Màn hình</h3><p>Nội dung</p>')).toBe(
      '<h2>Thiết kế</h2><h3 style="text-align: center">Màn hình</h3><p>Nội dung</p>')
  })

  test('scripts, event handlers, unsafe links and arbitrary styles are removed', () => {
    const html = richTextToHtml('<p onclick="alert(1)" style="position:fixed;inset:0;text-align:right">A<script>alert(1)</script>'
      + '<img src=x onerror="alert(1)"><a href="javascript:alert(1)">xấu</a><iframe src="https://evil.example"></iframe></p>'
      + '<h1>Tiêu đề</h1><div style="color:red"><span data-x="1" onmouseover="alert(1)">giữ chữ</span></div>')
    expect(html).toBe('<p style="text-align: right">A<a>xấu</a></p>Tiêu đề<span>giữ chữ</span>')
    expect(html).not.toMatch(/script|onerror|onclick|onmouseover|javascript|iframe|position|data-x/i)
  })

  test('text spans keep only a bounded font size and a plain font name', () => {
    expect(richTextToHtml('<p><span style="font-size: 18px; color: red; background: url(https://x.example/a.png)">A</span>'
      + '<span style="font-size: 200px; font-family: x;background:red">B</span><span style="font-size: 4px">C</span>'
      + '<span style="font-family: Arial, expression(alert(1))">D</span><span style="font-family: url(x)">E</span></p>'
      + '<p style="font-size: 30px">F</p>')).toBe('<p><span style="font-size: 18px">A</span><span style="font-family: x">B</span><span>C</span><span>D</span><span>E</span></p><p>F</p>')
  })

  test('images keep only web or site addresses and load lazily', () => {
    expect(richTextToHtml('<img src="/uploads/a.png" alt="A" width="9999" style="position:fixed" onerror="alert(1)" title="Ảnh">')).toBe(
      '<img src="/uploads/a.png" alt="A" title="Ảnh" loading="lazy" decoding="async">')
    for (const src of ['data:image/png;base64,iVBORw0KGgo=', 'javascript:alert(1)', '//evil.example/a.png', 'file:///c:/a.png', 'x']) {
      expect(richTextToHtml(`<p>Chữ</p><img src="${src}">`)).toBe('<p>Chữ</p>')
    }
    expect(normalizeRichText('<p></p><img src="https://cdn.example/a.png"><p></p>')).toBe(
      '<img src="https://cdn.example/a.png" loading="lazy" decoding="async">')
  })

  test('links open safely in a new tab when external and in place when internal', () => {
    expect(richTextToHtml('<p><a href="https://vietech.vn" target="_self">Web</a> <a href="/san-pham/a" target="_blank">Nội bộ</a></p>')).toBe(
      '<p><a href="https://vietech.vn" target="_blank" rel="noopener noreferrer nofollow">Web</a> <a href="/san-pham/a">Nội bộ</a></p>')
  })

  test('blank paragraphs inside the text are kept while the editor trailing paragraph is dropped', () => {
    expect(normalizeRichText('<p></p><p>Một</p><p></p><p></p><p>Hai</p><ul><li><p>Ba</p></li></ul><p></p><p style="text-align: center;"><br></p>'))
      .toBe('<p>Một</p><p></p><p></p><p>Hai</p><ul><li><p>Ba</p></li></ul>')
  })

  test('an empty editor is saved as null', () => {
    expect(normalizeRichText('<p></p>')).toBeNull()
    expect(normalizeRichText('<p>&nbsp;</p><p><span style="font-size: 20px"> </span></p>')).toBeNull()
    expect(normalizeRichText('<p><img src="data:image/png;base64,AAAA"></p>')).toBeNull()
    expect(normalizeRichText('   ')).toBeNull()
    expect(normalizeRichText(null)).toBeNull()
    expect(richTextToHtml('<p><script>x</script></p>')).toBe('')
  })
})

test('headings saved earlier open in the editor as bold paragraphs of a similar size', () => {
  expect(headingsToParagraphs('<h2>Thiết kế <em>mới</em></h2><h3 style="text-align: center">Màn hình</h3><p>Nội dung</p>')).toBe(
    '<p><strong><span style="font-size: 20px;">Thiết kế <em>mới</em></span></strong></p>'
    + '<p style="text-align: center;"><strong><span style="font-size: 16px;">Màn hình</span></strong></p><p>Nội dung</p>')
  expect(headingsToParagraphs('<p>Không có đề mục</p>')).toBe('<p>Không có đề mục</p>')
})

test('link addresses typed by an administrator are normalized or rejected', () => {
  expect(normalizeLinkUrl('vietech.vn/khuyen-mai')).toBe('https://vietech.vn/khuyen-mai')
  expect(normalizeLinkUrl(' https://vietech.vn ')).toBe('https://vietech.vn/')
  expect(normalizeLinkUrl('/san-pham/iphone')).toBe('/san-pham/iphone')
  expect(normalizeLinkUrl('mailto:hotro@vietech.vn')).toBe('mailto:hotro@vietech.vn')
  expect(normalizeLinkUrl('tel:19001234')).toBe('tel:19001234')
  for (const unsafe of ['javascript:alert(1)', 'JavaScript:alert(document.cookie)', 'data:text/html,<b>x</b>', 'vbscript:x', 'không phải link', '', 'abc']) {
    expect(normalizeLinkUrl(unsafe)).toBeNull()
  }
})

test('image addresses must be web or site paths', () => {
  expect(normalizeImageUrl('cdn.vietech.vn/a.png')).toBe('https://cdn.vietech.vn/a.png')
  expect(normalizeImageUrl('/uploads/a.png')).toBe('/uploads/a.png')
  for (const unsafe of ['mailto:a@b.vn', 'tel:1900', 'data:image/png;base64,AAAA', 'javascript:alert(1)', '']) expect(normalizeImageUrl(unsafe)).toBeNull()
})
