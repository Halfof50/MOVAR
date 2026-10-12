import { Link } from 'react-router'

export default function HospitalsPage() {
  return (
    <div className="stack">
      <section>
        <p className="eyebrow">NEAR YOU</p>
        <h1>내 주변 병원 찾기</h1>
        <p>현재 위치나 원하는 지역을 기준으로 병원을 찾아보세요.</p>
      </section>

      <section className="card">
        <span className="badge">검색 연결 준비 중</span>
        <h2>가까운 병원을 한눈에</h2>
        <p>
          지도와 병원 검색 기능을 연결할 공간이에요.
          현재는 실제 병원 정보가 표시되지 않아요.
        </p>

        <div className="map-placeholder">
          <span aria-hidden="true">＋</span>
          <strong>이곳에 지도와 검색 결과가 표시돼요</strong>
        </div>

        <p className="notice">
          위치 권한은 추후 ‘현재 위치로 찾기’를 눌렀을 때 요청해요.
          위치 사용을 원하지 않으면 지역 검색을 이용할 수 있도록 만들 예정이에요.
        </p>
      </section>

      <Link className="text-link" to="/">← 메인으로</Link>
    </div>
  )
}