import { describe, expect, test } from 'vitest'
import { nextQuery, safeNext, sessionArea } from './session.js'

describe('safeNext', () => {
  test.each([
    ['/tai-khoan', '/tai-khoan'],
    ['/san-pham/iphone-16?mau=den#danh-gia', '/san-pham/iphone-16?mau=den#danh-gia'],
  ])('keeps the customer path %s', (value, expected) => {
    expect(safeNext(value, 'customer')).toBe(expected)
  })

  test.each([
    ['/admin', '/admin'],
    ['/admin/users?page=2', '/admin/users?page=2'],
  ])('keeps the internal path %s', (value, expected) => {
    expect(safeNext(value, 'admin')).toBe(expected)
  })

  test.each([
    [null], [''], ['tai-khoan'], ['https://evil.example/'], ['//evil.example'], ['/\\evil.example'], ['/ /evil'],
    ['javascript:alert(1)'], ['/dang-nhap'], ['/dang-ky'], ['/quen-mat-khau'], ['/admin'], ['/admin/users'],
  ])('refuses %s on the customer login', (value) => {
    expect(safeNext(value, 'customer')).toBeNull()
  })

  test.each([
    ['/tai-khoan'], ['/'], ['/admin/login'], ['/admin/forgot-password'], ['//evil.example/admin'], ['/administrator'],
  ])('refuses %s on the internal login', (value) => {
    expect(safeNext(value, 'admin')).toBeNull()
  })
})

test('sessionArea follows the three roles only', () => {
  expect(sessionArea({ user: { Role: 'Customer' } })).toBe('customer')
  expect(sessionArea({ user: { Role: 'Staff' } })).toBe('internal')
  expect(sessionArea({ user: { Role: 'Admin' } })).toBe('internal')
  expect(sessionArea({ user: { Role: 'SuperAdmin' } })).toBeNull()
  expect(sessionArea(null)).toBeNull()
})

test('nextQuery encodes the current path and query', () => {
  expect(nextQuery({ pathname: '/admin/users', search: '?page=2' })).toBe('?next=%2Fadmin%2Fusers%3Fpage%3D2')
})
