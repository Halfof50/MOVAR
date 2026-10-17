import { Link } from 'react-router'
import { useAccount } from '../account/AccountContext'
import { getCareSummary } from '../services/careSummary'
export default function CarePage() {
  const { user, records, historyError, refresh } = useAccount()
  const summary = getCareSummary(records)
  if (!user) return <section className="card narrow"><h1>맞춤 케어</h1><p>로그인 후 저장한 분석 기록을 바탕으로 케어 내용을 확인할 수 있어요.</p><Link className="button" to="/login">로그인하기</Link></section>
  if (historyError) return <section className="card"><h1>맞춤 케어</h1><p role="alert">{historyError}</p><button className="button" onClick={()=>void refresh()}>다시 불러오기</button></section>
  if (!summary) return <section className="card narrow"><h1>첫 기록부터 시작해요</h1><p>맞춤 케어를 표시하려면 저장된 분석이 필요해요.</p><Link className="button" to="/capture">두피 촬영하기</Link><p><Link to="/mypage">마이페이지에서 체험용 기록 추가 →</Link></p></section>
  return <div className="stack account-page"><section className="page-heading"><p className="eyebrow">MY CARE · DEMO</p><h1>기록으로 살펴보는 나의 케어</h1><p>최근 {summary.count}건의 예시 기록을 바탕으로 구성했어요.</p></section>
    <div className="notice">실제 개인화 추천이 아닌 데모예요. 최근 최대 3건의 항목별 평균 단계가 높은 순서로 표시합니다. 문진·추천 모델·상품 매칭은 아직 연결하지 않았어요.</div>
    <section className="card"><h2>다음 기록에서 살펴볼 항목</h2><div className="care-priorities">{summary.priorities.map(item=><article key={item.id}><h3>{item.name}</h3><strong>평균 {item.average.toFixed(1)}단계</strong><p>다음 촬영 시 같은 부위를 기록해 변화를 비교해보세요.</p></article>)}</div></section>
    <section className="card"><h2>나의 기록 루틴</h2><ol><li>같은 위치와 비슷한 조명에서 두피 사진을 남겨요.</li><li>사용한 헤어케어 제품과 느낀 변화를 따로 메모해요.</li><li>마이페이지에서 이전 결과와 최신 기록을 함께 확인해요.</li></ol><p className="account-small">위 안내는 기록 관리를 위한 예시이며 의료적 판단이나 치료 안내가 아닙니다.</p><Link className="button" to="/mypage">분석 기록 보기</Link></section>
  </div>
}
