import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'
import { Button, EmptyState, ErrorState, Field, LoadingState, Money, Pagination } from './index.js'

describe('Button', () => {
  test('is a non-submitting button by default and forwards clicks', async () => {
    const onClick = vi.fn()
    render(<form onSubmit={() => { throw new Error('must not submit') }}><Button onClick={onClick}>Lưu</Button></form>)
    const button = screen.getByRole('button', { name: 'Lưu' })
    expect(button).toHaveAttribute('type', 'button')
    await userEvent.click(button)
    expect(onClick).toHaveBeenCalledOnce()
  })

  test('loading disables the button and marks it busy', async () => {
    const onClick = vi.fn()
    render(<Button loading onClick={onClick}>Đang lưu</Button>)
    const button = screen.getByRole('button', { name: 'Đang lưu' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    await userEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  test('variants use the brand tokens', () => {
    render(<><Button>Chính</Button><Button variant="outline">Phụ</Button></>)
    expect(screen.getByRole('button', { name: 'Chính' }).className).toContain('bg-brand-500')
    expect(screen.getByRole('button', { name: 'Phụ' }).className).toContain('border-brand-500')
  })
})

describe('Field', () => {
  test('labels its input and links the hint', () => {
    render(<Field id="email" label="Email" hint="Dùng email đã đăng ký" type="email" />)
    const input = screen.getByLabelText('Email')
    expect(input).toHaveAttribute('type', 'email')
    expect(input).toHaveAccessibleDescription('Dùng email đã đăng ký')
    expect(input).not.toHaveAttribute('aria-invalid')
  })

  test('an error marks the input invalid and describes it; required shows a marker', () => {
    render(<Field id="phone" label="Số điện thoại" required error="Vui lòng nhập số điện thoại Việt Nam hợp lệ." />)
    const input = screen.getByLabelText(/Số điện thoại/)
    expect(input).toBeRequired()
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveAccessibleDescription('Vui lòng nhập số điện thoại Việt Nam hợp lệ.')
  })

  test('accepts a custom control', () => {
    render(<Field id="gender" label="Giới tính"><select id="gender"><option>Nam</option></select></Field>)
    expect(screen.getByLabelText('Giới tính').tagName).toBe('SELECT')
  })
})

describe('states', () => {
  test('LoadingState announces its label', () => {
    render(<LoadingState label="Đang tải đơn hàng…" />)
    expect(screen.getByRole('status')).toHaveTextContent('Đang tải đơn hàng…')
  })

  test('EmptyState shows a title, description and action', () => {
    render(<EmptyState title="Chưa có đơn hàng" description="Hãy bắt đầu mua sắm." action={<a href="/">Mua sắm</a>} />)
    expect(screen.getByRole('heading', { name: 'Chưa có đơn hàng' })).toBeInTheDocument()
    expect(screen.getByText('Hãy bắt đầu mua sắm.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Mua sắm' })).toBeInTheDocument()
  })

  test('ErrorState is an alert and offers a retry only when it can retry', async () => {
    const onRetry = vi.fn()
    const { rerender } = render(<ErrorState message="Không tải được dữ liệu." onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Không tải được dữ liệu.')
    await userEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(onRetry).toHaveBeenCalledOnce()
    rerender(<ErrorState message="Không có quyền." />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('Pagination', () => {
  test('is hidden when everything fits on one page', () => {
    const { container } = render(<Pagination page={1} pageSize={20} total={20} onPageChange={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  test('moves between pages and disables the ends', async () => {
    const onPageChange = vi.fn()
    const { rerender } = render(<Pagination page={1} pageSize={20} total={45} onPageChange={onPageChange} />)
    expect(screen.getByRole('navigation', { name: 'Phân trang' })).toHaveTextContent('Trang 1 / 3')
    expect(screen.getByRole('button', { name: 'Trước' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Sau' }))
    expect(onPageChange).toHaveBeenLastCalledWith(2)
    rerender(<Pagination page={3} pageSize={20} total={45} onPageChange={onPageChange} />)
    expect(screen.getByRole('button', { name: 'Sau' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Trước' }))
    expect(onPageChange).toHaveBeenLastCalledWith(2)
  })

  test('disabled blocks both directions while a page is loading', () => {
    render(<Pagination page={2} pageSize={10} total={30} onPageChange={() => {}} disabled />)
    expect(screen.getByRole('button', { name: 'Trước' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Sau' })).toBeDisabled()
  })
})

test('Money shows API amounts in VND', () => {
  const { container } = render(<Money value="15000000.00" />)
  // Exact text: the currency sign follows a no-break space (getByText would normalize it to a space).
  expect(container.textContent).toBe('15.000.000 ₫')
})
