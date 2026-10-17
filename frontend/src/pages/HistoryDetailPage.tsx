import { Link, useParams } from 'react-router'
import { useAccount } from '../account/AccountContext'
import ResultsPage from './ResultsPage'
export default function HistoryDetailPage() {
  const { id } = useParams()
  const { user, records, historyError, refresh } = useAccount()
  if (!user) return <section className="card"><h1>로그인이 필요해요</h1><Link className="button" to="/login">로그인</Link></section>
  if (historyError) return <section className="card"><p role="alert">{historyError}</p><button className="button" onClick={()=>void refresh()}>다시 불러오기</button></section>
  const record = records.find(r => r.id === id && r.userId === user.id)
  if (!record) return <section className="card"><h1>기록을 찾을 수 없어요</h1><Link to="/mypage">마이페이지로 돌아가기</Link></section>
  return <div className="stack"><Link className="text-link" to="/mypage">← 전체 기록</Link><ResultsPage photo={null} record={record} /></div>
}
