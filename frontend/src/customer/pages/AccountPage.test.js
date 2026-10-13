// Converted from the node:test + vm harness (which compiled AccountPage.jsx with stubbed React hooks and inspected the
// returned element tree) to React Testing Library: the real page renders in jsdom with a customer session from the
// auth context. Both scenarios and all assertions are kept; DOM queries replace the element-tree search.
import assert from 'node:assert/strict'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import AccountPage from './AccountPage.jsx'

const account = vi.hoisted(() => ({ getDefaultAddress: null }))

vi.mock('../../lib/account-api.js', async (importOriginal) => ({
  ...(await importOriginal()),
  getDefaultAddress: (...args) => account.getDefaultAddress(...args),
}))

function deferred() {
  let resolve, reject
  const promise = new Promise((accept, decline) => { resolve = accept; reject = decline })
  return { promise, resolve, reject }
}

function harness(readAddress) {
  account.getDefaultAddress = readAddress
  const auth = {
    sessionReady: true,
    isCustomer: true,
    user: { FullName: 'Khách hàng', PhoneNumber: '0912345678', Email: 'customer@example.com', Role: 'Customer' },
    withAccessToken: (call) => call('access-token-for-test'),
    updateUser: () => {},
    endSession: () => {},
    signOut: async () => {},
  }
  return render(createElement(MemoryRouter, null, createElement(AuthContext.Provider, { value: auth }, createElement(AccountPage))))
}

const status = (container) => container.querySelector('[role="status"]')
const input = (container, id) => container.querySelector(`input#${id}`)

test('failed address loading blocks the editable profile and retry restores the saved address', async () => {
  const failed = deferred(), retried = deferred()
  let reads = 0
  const { container } = harness(() => (++reads === 1 ? failed.promise : retried.promise))
  assert.ok(status(container))
  await act(async () => { failed.reject(new Error('Không tải được địa chỉ đã lưu.')) })
  const alert = await screen.findByRole('alert')
  assert.equal(alert.textContent, 'Không tải được địa chỉ đã lưu.')
  assert.equal(container.querySelector('form'), null)
  await userEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  assert.ok(status(container))
  assert.equal(reads, 2)
  await act(async () => { retried.resolve({ Province: 'Hà Nội', Ward: 'Hoàn Kiếm', DetailAddress: '12 Hàng Bài' }) })
  await waitFor(() => assert.ok(container.querySelector('form')))
  assert.equal(screen.queryByRole('alert'), null)
  assert.ok(container.querySelector('form'))
  assert.equal(input(container, 'cacc-province').value, 'Hà Nội')
  assert.equal(input(container, 'cacc-detail').value, '12 Hàng Bài')
})

test('a successful null address opens the profile with empty address fields', async () => {
  const { container } = harness(async () => null)
  await waitFor(() => assert.ok(container.querySelector('form')))
  assert.equal(screen.queryByRole('alert'), null)
  assert.ok(container.querySelector('form'))
  assert.equal(input(container, 'cacc-name').value, 'Khách hàng')
  for (const id of ['cacc-province', 'cacc-ward', 'cacc-detail']) {
    assert.equal(input(container, id).value, '')
  }
})
