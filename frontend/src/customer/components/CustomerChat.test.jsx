import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import CustomerChat from './CustomerChat.jsx'
import ChatDraftProvider from './ChatDraftProvider.jsx'

afterEach(() => { vi.unstubAllGlobals() })

function renderChat(auth = makeAuth()) {
  return render(<AuthContext.Provider value={auth}><MemoryRouter><ChatDraftProvider>
    <CustomerChat />
  </ChatDraftProvider></MemoryRouter></AuthContext.Provider>)
}

test('the AI window enlarges beside the close button, Escape shrinks it first and it reopens at normal size', () => {
  const { container } = renderChat()
  fireEvent.click(screen.getByRole('button', { name: 'Chat với AI' }))
  const dialog = screen.getByRole('dialog')
  expect(dialog).not.toHaveClass('is-expanded')

  const expand = screen.getByRole('button', { name: 'Phóng to cửa sổ chat' })
  expect(expand.nextElementSibling).toBe(screen.getByRole('button', { name: 'Đóng cửa sổ chat' }))
  fireEvent.click(expand)
  expect(dialog).toHaveClass('is-expanded')
  expect(screen.getByRole('button', { name: 'Thu nhỏ cửa sổ chat' })).toHaveAttribute('aria-pressed', 'true')
  expect(container.querySelector('.shop-chat-backdrop')).toBeInTheDocument()

  fireEvent.keyDown(dialog, { key: 'Escape' })
  expect(dialog).not.toHaveClass('is-expanded')
  expect(container.querySelector('.shop-chat-backdrop')).not.toBeInTheDocument()
  fireEvent.keyDown(dialog, { key: 'Escape' })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Chat với AI' }))
  fireEvent.click(screen.getByRole('button', { name: 'Phóng to cửa sổ chat' }))
  fireEvent.click(container.querySelector('.shop-chat-backdrop'))
  expect(screen.getByRole('dialog')).not.toHaveClass('is-expanded')
  fireEvent.click(screen.getByRole('button', { name: 'Phóng to cửa sổ chat' }))
  fireEvent.click(screen.getByRole('button', { name: 'Đóng cửa sổ chat' }))
  fireEvent.click(screen.getByRole('button', { name: 'Chat với AI' }))
  expect(screen.getByRole('dialog')).not.toHaveClass('is-expanded')
})

test('the staff window enlarges the same way, keeps its composer and reopens at normal size', async () => {
  const conversation = { ConversationId: 'staff1', Mode: 'Staff', Status: 'Open', CreatedAt: '2026-10-23T08:00:00Z', Messages: [] }
  vi.stubGlobal('fetch', vi.fn(async (input, options = {}) => {
    const path = new URL(input, 'http://localhost').pathname.replace('/api', '')
    const data = path === '/conversations' && (options.method ?? 'GET') === 'GET' ? { Items: [conversation], Total: 1 } : conversation
    return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }))
  const { container } = renderChat(makeAuth({ role: 'Customer' }))
  fireEvent.click(screen.getByRole('button', { name: 'Chat với nhân viên' }))
  const dialog = screen.getByRole('dialog')
  expect(await screen.findByRole('textbox', { name: 'Nội dung tin nhắn' })).toBeInTheDocument()

  const expand = screen.getByRole('button', { name: 'Phóng to cửa sổ chat' })
  expect(expand.nextElementSibling).toBe(screen.getByRole('button', { name: 'Đóng cửa sổ chat' }))
  fireEvent.click(expand)
  expect(dialog).toHaveClass('shop-chat-panel-staff', 'is-expanded')
  expect(container.querySelector('.shop-chat-backdrop')).toBeInTheDocument()
  expect(screen.getByRole('textbox', { name: 'Nội dung tin nhắn' })).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Thu nhỏ cửa sổ chat' }))
  expect(dialog).not.toHaveClass('is-expanded')
  fireEvent.click(screen.getByRole('button', { name: 'Phóng to cửa sổ chat' }))
  fireEvent.click(screen.getByRole('button', { name: 'Chat với nhân viên' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Chat với nhân viên' }))
  expect(screen.getByRole('dialog')).not.toHaveClass('is-expanded')
})
