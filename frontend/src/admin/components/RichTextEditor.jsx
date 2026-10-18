import { useEffect, useRef, useState } from 'react'
import { EditorContent, useEditor, useEditorState } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import TextAlign from '@tiptap/extension-text-align'
import { FontFamily, FontSize, TextStyle } from '@tiptap/extension-text-style'
import Image from '@tiptap/extension-image'
import { Placeholder } from '@tiptap/extensions'
import { headingsToParagraphs, normalizeImageUrl, normalizeLinkUrl, richTextToHtml } from '../../lib/rich-text.js'
import { isAllowedProductImage, PRODUCT_IMAGE_RULE, PRODUCT_IMAGE_TYPES } from '../lib/product-images.js'
import '../../components/shared/RichText.css'

// Fonts available on customer devices that include Vietnamese characters; the value is the saved CSS font stack.
const FONT_FAMILIES = [
  ['', 'Phông mặc định'],
  ['Arial, Helvetica, sans-serif', 'Arial'],
  ['Tahoma, Verdana, sans-serif', 'Tahoma'],
  ['Verdana, Geneva, sans-serif', 'Verdana'],
  ['"Times New Roman", Times, serif', 'Times New Roman'],
  ['Georgia, serif', 'Georgia'],
  ['"Courier New", Courier, monospace', 'Courier New'],
]
const FONT_SIZES = ['12px', '13px', '14px', '16px', '18px', '20px', '24px', '28px', '32px']
const fontKey = (value) => (value ?? '').replace(/['"\s]/g, '').toLowerCase()

const ICONS = {
  bulletList: <><path d="M9 6h11M9 12h11M9 18h11" /><circle cx="4.5" cy="6" r="1.2" fill="currentColor" stroke="none" /><circle cx="4.5" cy="12" r="1.2" fill="currentColor" stroke="none" /><circle cx="4.5" cy="18" r="1.2" fill="currentColor" stroke="none" /></>,
  orderedList: <><path d="M10 6h10M10 12h10M10 18h10" /><path d="M4 4.5 5.2 4v4M4 8h2.4M3.8 11.3a1.2 1.2 0 0 1 2.2.7c0 .9-2.2 1.7-2.2 2.5h2.3M3.8 17h1.3a.9.9 0 0 1 0 1.8m-1.3 0h1.3a.9.9 0 0 1 0 1.8H3.8" strokeWidth="1.4" /></>,
  link: <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />,
  image: <><rect x="3" y="4" width="18" height="16" rx="2.5" /><circle cx="9" cy="10" r="1.8" /><path d="m4 18 5.5-5.5 3.5 3.5 2.5-2.5L20 18" /></>,
  hardBreak: <path d="M19 5v5a3 3 0 0 1-3 3H5m4-4-4 4 4 4" />,
  alignLeft: <path d="M4 6h16M4 10h10M4 14h16M4 18h10" />,
  alignCenter: <path d="M4 6h16M7 10h10M4 14h16M7 18h10" />,
  alignRight: <path d="M4 6h16M10 10h10M4 14h16M10 18h10" />,
  alignJustify: <path d="M4 6h16M4 10h16M4 14h16M4 18h16" />,
  clear: <path d="M6 5h12M12 5 9 19m-4 0h7M15 14l5 5m0-5-5 5" />,
  undo: <path d="M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11" />,
  redo: <path d="m15 14 5-5-5-5m5 5H9.5a5.5 5.5 0 0 0 0 11H13" />,
}

const ALIGNMENTS = ['center', 'right', 'justify']

// Grouped toolbar actions. `run` receives an editor chain that already has focus(); link and image open a panel.
const TOOL_GROUPS = [
  [
    { key: 'bold', label: 'In đậm (Ctrl + B)', text: 'B', textClass: 'font-bold', run: (chain) => chain.toggleBold(), active: (editor) => editor.isActive('bold') },
    { key: 'italic', label: 'In nghiêng (Ctrl + I)', text: 'I', textClass: 'font-serif italic', run: (chain) => chain.toggleItalic(), active: (editor) => editor.isActive('italic') },
    { key: 'underline', label: 'Gạch chân (Ctrl + U)', text: 'U', textClass: 'underline underline-offset-2', run: (chain) => chain.toggleUnderline(), active: (editor) => editor.isActive('underline') },
  ],
  [
    { key: 'bulletList', label: 'Danh sách dấu chấm', icon: 'bulletList', run: (chain) => chain.toggleBulletList(), active: (editor) => editor.isActive('bulletList') },
    { key: 'orderedList', label: 'Danh sách đánh số', icon: 'orderedList', run: (chain) => chain.toggleOrderedList(), active: (editor) => editor.isActive('orderedList') },
  ],
  [
    { key: 'link', label: 'Chèn hoặc sửa liên kết', icon: 'link', active: (editor) => editor.isActive('link') },
    { key: 'image', label: 'Chèn hoặc sửa ảnh', icon: 'image', active: (editor) => editor.isActive('image') },
    { key: 'hardBreak', label: 'Xuống dòng trong đoạn (Shift + Enter)', icon: 'hardBreak', run: (chain) => chain.setHardBreak() },
  ],
  [
    { key: 'alignLeft', label: 'Căn trái', icon: 'alignLeft', run: (chain) => chain.unsetTextAlign(), active: (editor) => !ALIGNMENTS.some((textAlign) => editor.isActive({ textAlign })) },
    { key: 'alignCenter', label: 'Căn giữa', icon: 'alignCenter', run: (chain) => chain.setTextAlign('center'), active: (editor) => editor.isActive({ textAlign: 'center' }) },
    { key: 'alignRight', label: 'Căn phải', icon: 'alignRight', run: (chain) => chain.setTextAlign('right'), active: (editor) => editor.isActive({ textAlign: 'right' }) },
    { key: 'alignJustify', label: 'Căn đều hai bên', icon: 'alignJustify', run: (chain) => chain.setTextAlign('justify'), active: (editor) => editor.isActive({ textAlign: 'justify' }) },
  ],
  [
    { key: 'clear', label: 'Xóa định dạng', icon: 'clear', run: (chain) => chain.unsetAllMarks().clearNodes().unsetTextAlign() },
    { key: 'undo', label: 'Hoàn tác (Ctrl + Z)', icon: 'undo', run: (chain) => chain.undo(), enabled: (editor) => editor.can().undo() },
    { key: 'redo', label: 'Làm lại (Ctrl + Y)', icon: 'redo', run: (chain) => chain.redo(), enabled: (editor) => editor.can().redo() },
  ],
]
const TOOLS = TOOL_GROUPS.flat()

const SELECT = 'h-8 rounded-[7px] border border-admin-border bg-white px-2 font-admin text-xs text-admin-text disabled:cursor-not-allowed disabled:opacity-35'
const PANEL_INPUT = 'h-8 min-w-[150px] flex-1 rounded-[7px] border border-admin-border px-2.5 font-admin text-xs text-admin-text'
const PANEL_PRIMARY = 'h-8 cursor-pointer rounded-[7px] bg-admin-blue px-3 text-xs font-medium text-white hover:bg-admin-navy disabled:cursor-not-allowed disabled:opacity-50'
const PANEL_SECONDARY = 'h-8 cursor-pointer rounded-[7px] border border-admin-border px-3 text-xs text-admin-muted hover:bg-admin-page'

function ToolIcon({ name }) {
  return <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[name]}</svg>
}

function toolbarState(editor) {
  const { fontSize, fontFamily } = editor.getAttributes('textStyle')
  return {
    ...Object.fromEntries(TOOLS.map((tool) => [tool.key, { active: tool.active?.(editor) ?? false, enabled: tool.enabled?.(editor) ?? true }])),
    textStyle: { fontSize: fontSize ?? '', fontFamily: fontFamily ?? '' },
  }
}

const editorHtml = (value) => headingsToParagraphs(richTextToHtml(value))
const imageFiles = (transfer) => [...(transfer?.files ?? [])].filter((file) => file.type.startsWith('image/'))
// Pasting HTML must not bypass the local upload flow. Saved content is loaded separately.
function withoutPastedImages(html) {
  const document = new DOMParser().parseFromString(html, 'text/html')
  document.querySelectorAll('img').forEach((image) => image.remove())
  return document.body.innerHTML
}

// Tiptap editor for product descriptions. `value` may be legacy plain text or saved HTML; `onChange` receives HTML
// (or '' when empty) only after the administrator edits, so untouched descriptions are saved exactly as loaded.
// `onUploadImage(file)` resolves to the uploaded image URL; `onUploadBusy` lets the form block saving meanwhile.
// Other fields (technical specifications) reuse it with their own texts and `allowImages={false}`.
export default function RichTextEditor({ id, label, labelClassName = '', value, onChange, readOnly = false, disabled = false,
  placeholder = 'Nhập mô tả sản phẩm…', onUploadImage, onUploadBusy, allowImages = true, emptyText = 'Chưa có mô tả sản phẩm.',
  toolbarLabel = 'Định dạng mô tả sản phẩm', hint, readOnlyHint = 'Mô tả dùng chung cho các biến thể của sản phẩm.',
  imageUploadLabel = 'Chọn ảnh để chèn vào mô tả' }) {
  const labelId = id + '-label', hintId = id + '-hint', linkInputId = id + '-link', imageAltId = id + '-image-alt'
  const editable = !readOnly && !disabled, canUpload = allowImages && Boolean(onUploadImage)
  const lastValue = useRef(value), toolbar = useRef(null), fileInput = useRef(null), uploading = useRef(false), mounted = useRef(true), imageSelection = useRef(null)
  const callbacks = useRef({})
  const [linkDraft, setLinkDraft] = useState(null), [linkError, setLinkError] = useState('')
  const [imageDraft, setImageDraft] = useState(null), [imageError, setImageError] = useState(''), [imageStatus, setImageStatus] = useState('')
  const [tabStop, setTabStop] = useState(TOOLS[0].key)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false, code: false, codeBlock: false, horizontalRule: false,
        link: { openOnClick: false, defaultProtocol: 'https', HTMLAttributes: { target: '_blank', rel: 'noopener noreferrer nofollow' } },
      }),
      TextStyle, FontFamily, FontSize,
      ...(allowImages ? [Image.configure({ allowBase64: false })] : []),
      TextAlign.configure({ types: ['paragraph'], alignments: ['left', ...ALIGNMENTS] }),
      Placeholder.configure({ showOnlyWhenEditable: false, placeholder: ({ editor: current }) => current.isEditable ? placeholder : emptyText }),
    ],
    content: editorHtml(value),
    editable,
    editorProps: {
      attributes: { id, role: 'textbox', 'aria-multiline': 'true', 'aria-labelledby': labelId, 'aria-describedby': hintId, class: 'vt-rich-text' },
      transformPastedHTML: withoutPastedImages,
      // Image files dropped or pasted into the description are uploaded like the toolbar button does.
      handleDrop: (view, event, _slice, moved) => {
        const files = imageFiles(event.dataTransfer)
        if (moved || !files.length || !callbacks.current.canUpload) return false
        event.preventDefault()
        void callbacks.current.upload(files, view.posAtCoords({ left: event.clientX, top: event.clientY })?.pos)
        return true
      },
      handlePaste: (_view, event) => {
        const files = imageFiles(event.clipboardData)
        if (!files.length || !callbacks.current.canUpload) return false
        void callbacks.current.upload(files)
        return true
      },
    },
    onUpdate: ({ editor: current }) => {
      const html = current.isEmpty ? '' : current.getHTML()
      lastValue.current = html
      callbacks.current.onChange(html)
    },
  })
  const state = useEditorState({ editor, selector: ({ editor: current }) => current ? toolbarState(current) : null })

  // Load a different description (another parent product, a reset form) without reporting it as an edit.
  useEffect(() => {
    if (!editor || value === lastValue.current) return
    lastValue.current = value
    editor.commands.setContent(editorHtml(value), { emitUpdate: false })
  }, [editor, value])
  useEffect(() => { editor?.setEditable(editable, false) }, [editor, editable])

  async function uploadImages(fileList, position) {
    const files = [...(fileList ?? [])]
    if (!files.length || !onUploadImage || uploading.current || !editor || !editable) return
    if (!files.every(isAllowedProductImage)) { setImageError(PRODUCT_IMAGE_RULE); return }
    const alt = imageDraft?.alt.trim() ?? ''
    const replaceAt = position === undefined && editor.isActive('image') ? editor.state.selection.from : undefined
    let at = position
    uploading.current = true
    setImageError('')
    onUploadBusy?.(true)
    try {
      for (const [index, file] of files.entries()) {
        setImageStatus(files.length > 1 ? `Đang tải ảnh ${index + 1}/${files.length}…` : 'Đang tải ảnh…')
        const src = normalizeImageUrl(await onUploadImage(file))
        if (!mounted.current || editor.isDestroyed) return
        if (!src) throw new Error('Kho lưu trữ chưa trả về địa chỉ ảnh hợp lệ. Vui lòng thử lại.')
        const image = { type: 'image', attrs: { src, alt } }
        if (index === 0 && replaceAt !== undefined && editor.state.doc.nodeAt(replaceAt)?.type.name === 'image') {
          editor.chain().setNodeSelection(replaceAt).updateAttributes('image', image.attrs).setTextSelection(replaceAt + 1).run()
        } else if (at === undefined) editor.chain().insertContent(image).run()
        else { editor.chain().insertContentAt(at, image).run(); at = undefined }
      }
      setImageDraft(null)
    } catch (failure) {
      if (mounted.current) setImageError(failure?.message || 'Không tải được ảnh. Vui lòng thử lại.')
    } finally {
      uploading.current = false
      if (mounted.current) setImageStatus('')
      if (fileInput.current) fileInput.current.value = ''
      onUploadBusy?.(false)
    }
  }
  useEffect(() => { callbacks.current = { onChange, canUpload: canUpload && editable, upload: uploadImages } })

  function runTool(tool) {
    if (!editor || !editable) return
    if (tool.key === 'link') {
      setImageDraft(null)
      setLinkDraft(editor.getAttributes('link').href ?? '')
      setLinkError('')
      return
    }
    if (tool.key === 'image') {
      const current = editor.isActive('image') ? editor.getAttributes('image') : {}
      setLinkDraft(null)
      if (!canUpload && !current.src) return
      imageSelection.current = current.src ? editor.state.selection.from : null
      setImageDraft({ existing: Boolean(current.src), alt: current.alt ?? '' })
      setImageError('')
      return
    }
    tool.run(editor.chain().focus()).run()
  }
  function applyTextStyle(kind, next) {
    if (!editor || !editable) return
    const chain = editor.chain().focus()
    if (kind === 'fontSize') (next ? chain.setFontSize(next) : chain.unsetFontSize()).run()
    else (next ? chain.setFontFamily(next) : chain.unsetFontFamily()).run()
  }
  function closePanels() {
    setLinkDraft(null)
    setImageDraft(null)
    setLinkError('')
    setImageError('')
    editor?.commands.focus()
  }
  function applyLink() {
    const href = normalizeLinkUrl(linkDraft)
    if (!href) { setLinkError('Nhập địa chỉ hợp lệ, ví dụ https://vietech.vn, /san-pham/... hoặc mailto:hotro@vietech.vn.'); return }
    const chain = editor.chain().focus()
    if (editor.state.selection.empty && !editor.isActive('link')) chain.insertContent({ type: 'text', text: href, marks: [{ type: 'link', attrs: { href } }] }).unsetMark('link')
    else chain.extendMarkRange('link').setLink({ href })
    chain.run()
    setLinkDraft(null)
    setLinkError('')
  }
  function removeLink() {
    editor.chain().focus().extendMarkRange('link').unsetLink().run()
    setLinkDraft(null)
    setLinkError('')
  }
  function applyImage() {
    const position = imageSelection.current
    if (!editor || !editable || uploading.current || position == null) return
    if (editor.state.doc.nodeAt(position)?.type.name !== 'image') { closePanels(); return }
    editor.chain().focus().setNodeSelection(position).updateAttributes('image', { alt: imageDraft.alt.trim() }).run()
    setImageDraft(null)
    setImageError('')
  }
  function panelKeys(apply) {
    return (event) => {
      if (event.key === 'Enter') { event.preventDefault(); apply() }
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); closePanels() }
    }
  }
  // Arrow keys move between toolbar buttons so the buttons are a single Tab stop; the two menus keep their own keys.
  function moveFocus(event) {
    const keys = { ArrowRight: 1, ArrowLeft: -1, Home: 'first', End: 'last' }
    if (!(event.key in keys) || !toolbar.current || event.target.tagName === 'SELECT') return
    const buttons = [...toolbar.current.querySelectorAll('button:not(:disabled)')]
    if (!buttons.length) return
    event.preventDefault()
    const index = buttons.indexOf(document.activeElement), step = keys[event.key]
    const next = step === 'first' ? 0 : step === 'last' ? buttons.length - 1 : (index + step + buttons.length) % buttons.length
    buttons[next].focus()
  }

  const focusable = state?.[tabStop]?.enabled ? tabStop : TOOLS[0].key
  const fontSize = state?.textStyle.fontSize ?? '', fontFamily = state?.textStyle.fontFamily ?? ''
  const familyOption = FONT_FAMILIES.find(([option]) => fontKey(option) === fontKey(fontFamily))
  const sizes = fontSize && !FONT_SIZES.includes(fontSize) ? [...FONT_SIZES, fontSize] : FONT_SIZES
  const busy = !editor || disabled
  return <div className="flex min-w-0 flex-col gap-[7px]">
    <span id={labelId} className={labelClassName} onClick={() => editor?.commands.focus()}>{label}</span>
    <div className="vt-rich-editor" data-readonly={readOnly}>
      {!readOnly && <div ref={toolbar} role="toolbar" aria-label={toolbarLabel} aria-controls={id} onKeyDown={moveFocus}
        className="flex flex-wrap items-center gap-0.5 border-b border-admin-border bg-admin-page px-1.5 py-1.5">
        <div className="flex items-center gap-1.5">
          <select aria-label="Phông chữ" title="Phông chữ" className={SELECT + ' w-[140px]'} disabled={busy} value={familyOption ? familyOption[0] : fontFamily}
            onChange={(event) => applyTextStyle('fontFamily', event.target.value)}>
            {FONT_FAMILIES.map(([option, name]) => <option key={name} value={option} style={option ? { fontFamily: option } : undefined}>{name}</option>)}
            {fontFamily && !familyOption && <option value={fontFamily}>{fontFamily}</option>}
          </select>
          <select aria-label="Cỡ chữ" title="Cỡ chữ" className={SELECT + ' w-[112px]'} disabled={busy} value={fontSize} onChange={(event) => applyTextStyle('fontSize', event.target.value)}>
            <option value="">Cỡ mặc định</option>
            {sizes.map((size) => <option key={size} value={size}>{size.replace('px', '')} px</option>)}
          </select>
        </div>
        {TOOL_GROUPS.map((group, groupIndex) => <div key={groupIndex} className="flex items-center gap-0.5">
          <span className="mx-1 h-5 w-px bg-admin-border" aria-hidden="true" />
          {group.filter((tool) => allowImages || tool.key !== 'image').map((tool) => {
            const toolState = state?.[tool.key], toggle = Boolean(tool.active)
            return <button key={tool.key} type="button" title={tool.label} aria-label={tool.label} aria-pressed={toggle ? Boolean(toolState?.active) : undefined}
              tabIndex={tool.key === focusable ? 0 : -1} disabled={busy || toolState?.enabled === false || (tool.key === 'image' && !canUpload && !state?.image.active)}
              onFocus={() => setTabStop(tool.key)} onMouseDown={(event) => event.preventDefault()} onClick={() => runTool(tool)}
              className={'grid h-8 min-w-8 cursor-pointer place-items-center rounded-[7px] px-1.5 font-admin text-xs text-admin-text transition-colors hover:bg-admin-soft focus-visible:outline-2 focus-visible:outline-admin-blue disabled:cursor-not-allowed disabled:opacity-35 '
                + (toolState?.active ? 'bg-admin-soft text-admin-blue' : '')}>
              {tool.icon ? <ToolIcon name={tool.icon} /> : <span className={'text-[13px] leading-none font-semibold ' + (tool.textClass ?? '')}>{tool.text}</span>}
            </button>
          })}
        </div>)}
      </div>}
      {linkDraft !== null && editable && <div className="flex flex-wrap items-center gap-2 border-b border-admin-border bg-white px-2.5 py-2">
        <label htmlFor={linkInputId} className="text-[11px] font-medium">Địa chỉ liên kết</label>
        <input id={linkInputId} type="text" inputMode="url" autoComplete="off" autoFocus placeholder="https://..." value={linkDraft}
          aria-invalid={Boolean(linkError) || undefined} aria-describedby={linkError ? linkInputId + '-error' : undefined} className={PANEL_INPUT}
          onChange={(event) => { setLinkDraft(event.target.value); setLinkError('') }} onKeyDown={panelKeys(applyLink)} />
        <button type="button" className={PANEL_PRIMARY} onClick={applyLink}>Áp dụng</button>
        {state?.link.active && <button type="button" className="h-8 cursor-pointer rounded-[7px] border border-admin-border px-3 text-xs text-admin-red hover:bg-admin-red/5" onClick={removeLink}>Gỡ liên kết</button>}
        <button type="button" className={PANEL_SECONDARY} onClick={closePanels}>Hủy</button>
        {linkError && <p id={linkInputId + '-error'} role="alert" className="m-0 w-full text-[11px] text-admin-red">{linkError}</p>}
      </div>}
      {imageDraft !== null && editable && <div className="flex flex-wrap items-center gap-2 border-b border-admin-border bg-white px-2.5 py-2">
        {canUpload && <>
          <button type="button" disabled={busy} className={PANEL_PRIMARY} onClick={() => fileInput.current?.click()}>Tải ảnh từ máy</button>
          <input ref={fileInput} type="file" tabIndex={-1} disabled={busy} className="sr-only" aria-label={imageUploadLabel} accept={PRODUCT_IMAGE_TYPES.join(',')} multiple
            onChange={(event) => void uploadImages(event.target.files)} />
          <span className="text-[11px] text-admin-muted">{PRODUCT_IMAGE_RULE}</span>
        </>}
        <label htmlFor={imageAltId} className="sr-only">Mô tả ảnh</label>
        <input id={imageAltId} type="text" disabled={busy} autoComplete="off" maxLength={200} placeholder="Mô tả ảnh (không bắt buộc)" value={imageDraft.alt} className={PANEL_INPUT}
          onChange={(event) => setImageDraft((draft) => ({ ...draft, alt: event.target.value }))} onKeyDown={(event) => panelKeys(applyImage)(event)} />
        {imageDraft.existing && <button type="button" disabled={busy} className={PANEL_PRIMARY} onClick={() => applyImage()}>Cập nhật ảnh</button>}
        <button type="button" disabled={busy} className={PANEL_SECONDARY} onClick={closePanels}>Hủy</button>
      </div>}
      <EditorContent editor={editor} />
    </div>
    {imageStatus && <p role="status" className="m-0 text-[11px] text-admin-blue">{imageStatus}</p>}
    {imageError && <p role="alert" className="m-0 text-[11px] text-admin-red">{imageError}</p>}
    <p id={hintId} className="m-0 text-[11px] text-admin-muted">{readOnly ? readOnlyHint
      : hint ?? 'Bôi đen chữ rồi chọn phông, cỡ chữ hoặc định dạng. Enter tạo đoạn mới, Shift + Enter xuống dòng trong cùng đoạn.'
        + (canUpload ? ' Có thể kéo thả hoặc dán ảnh vào ô mô tả.' : '')}</p>
  </div>
}
