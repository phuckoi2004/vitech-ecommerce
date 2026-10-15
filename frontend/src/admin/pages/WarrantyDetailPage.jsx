import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import { warrantyListSearch } from '../lib/warranties.js'
import useServiceRequestWorkflow from '../hooks/useServiceRequestWorkflow.js'
import { WarrantyButton } from '../components/WarrantyUi.jsx'
import WarrantyInformation from '../components/WarrantyInformation.jsx'
import WarrantyRejectDialog from '../components/WarrantyRejectDialog.jsx'
import WarrantyResult from '../components/WarrantyResult.jsx'
import ServiceRequestActions from '../components/ServiceRequestActions.jsx'

function WarrantyWorkspace({ requestId }) {
  const [params] = useSearchParams(), navigate = useNavigate()
  const workflow = useServiceRequestWorkflow('warranty', requestId)
  const { item, detail, busy, auth } = workflow
  return <section aria-label="Chi tiết yêu cầu bảo hành" className="-my-1 flex min-w-0 flex-col gap-4 font-admin text-admin-text">
    <header className="mb-1.5 flex min-h-[33px] items-center justify-between gap-4"><h2 className="m-0 text-xl leading-[normal] font-bold">{item ? 'Yêu cầu ' + item.RequestCode : 'Chi tiết yêu cầu bảo hành'}</h2><WarrantyButton secondary className="text-admin-text!" disabled={busy} onClick={() => navigate('/admin/warranties' + warrantyListSearch(params))}>← Danh sách bảo hành</WarrantyButton></header>
    {!item && detail.loading ? <LoadingState label="Đang tải yêu cầu bảo hành…" /> : !item && detail.error ? <ErrorState message={detail.error} onRetry={workflow.refresh} /> : item && <>
      <WarrantyInformation item={item} assignedName={item.AssignedStaffId === auth.user.UserId ? auth.user.FullName : null}><WarrantyResult workflow={workflow} /></WarrantyInformation>
      <ServiceRequestActions workflow={workflow} warranty />
      {workflow.rejecting && <WarrantyRejectDialog open busy={busy} error={workflow.error} onClose={workflow.closeReject} onSubmit={workflow.reject} />}
    </>}
  </section>
}
export default function WarrantyDetailPage() {
  const { requestId } = useParams()
  return <WarrantyWorkspace key={requestId} requestId={requestId} />
}
