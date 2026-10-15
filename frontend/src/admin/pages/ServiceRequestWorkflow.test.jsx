import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), request: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData }))
vi.mock('../../services/api/client.js', async (original) => ({ ...await original(), request: api.request }))
const base = { CustomerName:'Nguyễn Văn An', ProductName:'Điện thoại đen', Sku:'SKU-01', OrderCode:'DH-123', AssignedStaffId:null, RequestedAt:'2026-10-15T03:00:00Z', ReceivedAt:null, ResultApprovedAt:null, Attachments:[], Histories:[] }
let returned, warranty
function renderPage(kind = 'returns', granted = true) {
  const router = createMemoryRouter(adminRoutes, { initialEntries:[`/admin/${kind}/id`] })
  const permissions=['admin.portal',kind+':view',...(granted?[kind+':update']:[])]
  render(<AuthContext.Provider value={makeAuth({role:'Staff',permissions})}><RouterProvider router={router}/></AuthContext.Provider>)
  return router
}
beforeEach(()=>{
  vi.resetAllMocks()
  returned={...base,ReturnRequestId:'id',RequestCode:'DT-1',RequestType:'Exchange',Status:'Pending',Reason:'Lỗi hiển thị'}
  warranty={...base,WarrantyRequestId:'id',RequestCode:'BH-1',Status:'New',EligibilityStatus:'Pending',IssueDescription:'Không nhận sạc'}
  api.getAdminData.mockImplementation(async(_,path)=>{
    if(path.endsWith('unread-count'))return{Count:0}
    if(path==='/admin/return-requests/id')return structuredClone(returned)
    if(path==='/admin/warranty-requests/id')return structuredClone(warranty)
    throw new Error('Không tìm thấy phiếu.')
  })
  api.request.mockResolvedValue(null)
})

test('pending return exposes exactly two actions and reception becomes forward progress without extra inputs', async()=>{
  api.request.mockResolvedValue({...returned,Status:'Approved'})
  renderPage()
  const actions=await screen.findByLabelText('Thao tác phiếu')
  expect(within(actions).getAllByRole('button').map(b=>b.textContent)).toEqual(['Từ chối','Tiếp nhận yêu cầu'])
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Tiếp nhận yêu cầu'}))
  await screen.findByRole('button',{name:'Giai đoạn kế tiếp'})
  expect(api.request).toHaveBeenCalledExactlyOnceWith('/admin/return-requests/id/advance',{method:'POST',accessToken:'access-for-test',body:{ExpectedStatus:'Pending'}})
  expect(screen.queryByRole('button',{name:/Hủy phiếu|Quay lại giai đoạn/})).not.toBeInTheDocument()
})

test('rejection only sends a trimmed public reason and closes the request', async()=>{
  api.request.mockResolvedValue({...returned,Status:'Rejected',DecisionReason:'Sai sản phẩm'})
  renderPage()
  fireEvent.click(await screen.findByRole('button',{name:'Từ chối',exact:true}))
  const dialog=screen.getByRole('dialog',{name:'Từ chối yêu cầu đổi trả'})
  fireEvent.click(within(dialog).getByRole('button',{name:'Xác nhận từ chối'}))
  expect(api.request).not.toHaveBeenCalled()
  fireEvent.change(within(dialog).getByRole('textbox',{name:'Lý do từ chối'}),{target:{value:'  Sai sản phẩm  '}})
  fireEvent.click(within(dialog).getByRole('button',{name:'Xác nhận từ chối'}))
  await screen.findByText('Đóng phiếu')
  expect(api.request).toHaveBeenCalledExactlyOnceWith('/admin/return-requests/id/reject',{method:'POST',accessToken:'access-for-test',body:{Reason:'Sai sản phẩm'}})
  expect(screen.getByText('Sai sản phẩm')).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test.each(['returns','warranties'])('repeated clicks in %s cannot skip stages while the write is pending',async(kind)=>{
  let complete
  api.request.mockImplementation(()=>new Promise(resolve=>{complete=resolve}))
  renderPage(kind)
  const button=await screen.findByRole('button',{name:kind==='returns'?'Tiếp nhận yêu cầu':'Tiếp nhận & kiểm tra'})
  fireEvent.click(button);fireEvent.click(button)
  expect(api.request).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('button',{name:'Đang xử lý…'})).toBeDisabled()
  await act(async()=>complete(kind==='returns'?{...returned,Status:'Approved'}:{...warranty,ReceivedAt:'2026-10-15T04:00:00Z'}))
  await screen.findByRole('button',{name:'Giai đoạn kế tiếp'})
})

test.each(['Completed','Rejected','Cancelled'])('closed %s return has no mutation actions',async(status)=>{
  returned.Status=status
  renderPage()
  await screen.findByText('Đóng phiếu')
  expect(within(screen.getByLabelText('Thao tác phiếu')).queryByRole('button')).not.toBeInTheDocument()
  expect(api.request).not.toHaveBeenCalled()
})

test('warranty requires one of three actual results and a customer message before advancing',async()=>{
  warranty={...warranty,Status:'Processing',ReceivedAt:'2026-10-15T04:00:00Z'}
  api.request.mockImplementation(async()=>({...warranty,ResultType:'PartReplaced',ResultNote:'Đã thay cổng sạc.',ResultApprovedAt:'2026-10-15T05:00:00Z'}))
  renderPage('warranties')
  const select=await screen.findByRole('combobox',{name:'Kết quả bảo hành'})
  expect(within(select).getAllByRole('option').filter(o=>o.value).map(o=>o.textContent)).toEqual(['Sửa chữa','Thay linh kiện','Không thể sửa chữa'])
  const next=screen.getByRole('button',{name:'Giai đoạn kế tiếp'})
  expect(next).toBeDisabled()
  fireEvent.change(select,{target:{value:'PartReplaced'}})
  expect(next).toBeDisabled()
  fireEvent.change(screen.getByRole('textbox',{name:'Nội dung kết quả gửi khách hàng'}),{target:{value:'  Đã thay cổng sạc.  '}})
  expect(next).toBeEnabled()
  fireEvent.click(next)
  await screen.findByText('Đã thay cổng sạc.')
  expect(api.request).toHaveBeenCalledExactlyOnceWith('/admin/warranty-requests/id/advance',{method:'POST',accessToken:'access-for-test',body:{ExpectedStage:'Repairing',ResultType:'PartReplaced',ResultNote:'Đã thay cổng sạc.'}})
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
})

test('stale response is shown in a dialog; reload fetches the actual terminal state',async()=>{
  api.request.mockRejectedValue(new Error('Phiếu đã thay đổi; hãy tải lại.'))
  renderPage()
  fireEvent.click(await screen.findByRole('button',{name:'Tiếp nhận yêu cầu'}))
  const dialog=await screen.findByRole('dialog',{name:'Không cập nhật được phiếu'})
  expect(within(dialog).getByRole('alert')).toHaveTextContent('Phiếu đã thay đổi')
  expect(screen.queryByRole('button',{name:'Giai đoạn kế tiếp'})).not.toBeInTheDocument()
  returned.Status='Cancelled'
  fireEvent.click(within(dialog).getByRole('button',{name:'Tải lại phiếu'}))
  await screen.findByText('Đóng phiếu')
  expect(api.request).toHaveBeenCalledTimes(1)
})

test('view permission alone cannot submit status changes or publish results',async()=>{
  warranty.Status='Processing'
  renderPage('warranties',false)
  await screen.findByRole('heading',{name:'Yêu cầu BH-1'})
  expect(within(screen.getByLabelText('Thao tác phiếu')).queryByRole('button')).not.toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  await waitFor(()=>expect(api.request).not.toHaveBeenCalled())
})

test('pending rejection prevents duplicate submissions and closing the dialog',async()=>{
  let complete
  api.request.mockImplementation(()=>new Promise(resolve=>{complete=resolve}))
  renderPage()
  fireEvent.click(await screen.findByRole('button',{name:'Từ chối',exact:true}))
  const dialog=screen.getByRole('dialog',{name:'Từ chối yêu cầu đổi trả'})
  fireEvent.change(within(dialog).getByRole('textbox'),{target:{value:'Lý do thực tế'}})
  const button=within(dialog).getByRole('button',{name:'Xác nhận từ chối'})
  fireEvent.click(button);fireEvent.click(button)
  fireEvent.click(within(dialog).getByRole('button',{name:'Đóng'}))
  fireEvent(dialog,new Event('cancel',{bubbles:false,cancelable:true}))
  expect(api.request).toHaveBeenCalledTimes(1)
  expect(dialog).toBeInTheDocument()
  expect(within(dialog).getByRole('button',{name:'Đang xử lý…'})).toBeDisabled()
  await act(async()=>complete({...returned,Status:'Rejected',DecisionReason:'Lý do thực tế'}))
  await screen.findByText('Đóng phiếu')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})
