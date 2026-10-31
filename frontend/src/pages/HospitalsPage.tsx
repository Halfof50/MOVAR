import { useState } from 'react'
import { Link } from 'react-router'
import { api } from '../services/api'
import type { Hospital } from '../services/api'
import { errorMessage } from '../account/AccountContext'
import './HospitalsPage.css'

type Search = { state: 'idle' | 'locating' | 'loading' | 'done' | 'error'; items: Hospital[]; message: string }
const radii = [1000, 3000, 5000, 10000]

function locationError(error: GeolocationPositionError) {
  if (error.code === error.PERMISSION_DENIED) return '위치 권한이 허용되지 않았어요. 주소창의 사이트 설정에서 위치 권한을 확인한 뒤 다시 시도해주세요.'
  if (error.code === error.TIMEOUT) return '위치를 확인하는 데 시간이 너무 오래 걸렸어요. 다시 시도해주세요.'
  return '현재 위치를 확인하지 못했어요. 기기의 위치 설정을 확인해주세요.'
}
const distance = (meters: number | null) => meters === null ? '' : meters < 1000 ? `${meters}m` : `${(meters / 1000).toFixed(1)}km`

export default function HospitalsPage() {
  const [query, setQuery] = useState<'피부과' | '탈모'>('피부과')
  const [radius, setRadius] = useState(5000)
  const [region, setRegion] = useState('')
  const [search, setSearch] = useState<Search>({ state: 'idle', items: [], message: '' })
  const canLocate = window.isSecureContext && !!navigator.geolocation

  function findByRegion() {
    const name = region.trim()
    if (name.length < 2) { setSearch({ state: 'error', items: [], message: '지역 이름을 2글자 이상 입력해주세요. 예: 강남구, 부산 해운대' }); return }
    setSearch({ state: 'loading', items: [], message: '' })
    api.hospitals({ region: name, radius, query })
      .then(({ items }) => setSearch({ state: 'done', items, message: '' }))
      .catch(error => setSearch({ state: 'error', items: [], message: errorMessage(error) }))
  }

  function find() {
    if (!navigator.geolocation) { setSearch({ state: 'error', items: [], message: '이 브라우저는 위치 확인을 지원하지 않아요.' }); return }
    setSearch({ state: 'locating', items: [], message: '' })
    // The location is sent to the backend only for this search and is not stored.
    navigator.geolocation.getCurrentPosition(
      position => {
        setSearch({ state: 'loading', items: [], message: '' })
        api.hospitals({ lat: position.coords.latitude, lng: position.coords.longitude, radius, query })
          .then(({ items }) => setSearch({ state: 'done', items, message: '' }))
          .catch(error => setSearch({ state: 'error', items: [], message: errorMessage(error) }))
      },
      error => setSearch({ state: 'error', items: [], message: locationError(error) }),
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 },
    )
  }
  const busy = search.state === 'locating' || search.state === 'loading'

  return (
    <div className="stack hospitals-page">
      <section>
        <p className="eyebrow">NEAR YOU</p>
        <h1>내 주변 병원 찾기</h1>
        <p>현재 위치를 기준으로 가까운 병원을 찾아보세요.</p>
      </section>

      <section className="card">
        <h2>가까운 병원을 한눈에</h2>
        <div className="hospital-controls">
          <label>진료과<select value={query} disabled={busy} onChange={event => setQuery(event.target.value as '피부과' | '탈모')}><option value="피부과">피부과</option><option value="탈모">탈모 클리닉</option></select></label>
          <label>검색 반경<select value={radius} disabled={busy} onChange={event => setRadius(Number(event.target.value))}>{radii.map(value => <option key={value} value={value}>{value / 1000}km</option>)}</select></label>
          <button className="button" onClick={find} disabled={busy || !canLocate}>{search.state === 'locating' ? '위치 확인 중…' : '현재 위치로 찾기'}</button>
        </div>
        <form className="hospital-controls hospital-region" onSubmit={event => { event.preventDefault(); if (!busy) findByRegion() }}>
          <label>지역 이름으로 찾기<input value={region} maxLength={40} placeholder="예: 강남구, 부산 해운대" disabled={busy} onChange={event => setRegion(event.target.value)} /></label>
          <button className="button capture-secondary" type="submit" disabled={busy}>{search.state === 'loading' ? '검색 중…' : '지역으로 찾기'}</button>
        </form>
        <p className="notice">{canLocate ? '위치 권한은 ‘현재 위치로 찾기’를 눌렀을 때만 요청해요. 위치는 검색에만 쓰이고 저장하지 않아요.' : '이 주소에서는 브라우저가 현재 위치 확인을 막아요(HTTPS 또는 localhost에서만 가능). 지역 이름으로 찾아보세요.'} 지역 이름으로 찾으면 거리는 표시되지 않아요.</p>

        <div aria-live="polite">
          {search.state === 'error' && <p className="capture-error" role="alert">{search.message}</p>}
          {search.state === 'done' && (search.items.length === 0
            ? <p>이 반경에서는 찾지 못했어요. 검색 반경을 넓혀 보세요.</p>
            : <ul className="hospital-list">{search.items.map(item => (
              <li key={`${item.lat},${item.lng},${item.name}`} className="hospital-item">
                <div className="hospital-main"><h3>{item.name}</h3>{item.distance_m !== null && <span className="badge">{distance(item.distance_m)}</span>}</div>
                {item.category && <p className="hospital-category">{item.category.split('>').pop()?.trim()}</p>}
                <p>{item.road_address || item.address}</p>
                <div className="hospital-links">
                  {item.phone && <a href={`tel:${item.phone.replace(/[^0-9+]/g, '')}`}>{item.phone}</a>}
                  {item.place_url && /^https?:\/\//i.test(item.place_url) && <a href={item.place_url} target="_blank" rel="noopener noreferrer" aria-label={`${item.name} 카카오맵에서 보기 (새 창)`}>카카오맵에서 보기 ↗</a>}
                </div>
              </li>
            ))}</ul>)}
        </div>
        {search.state === 'done' && <p className="account-small">검색 결과는 카카오맵의 장소 정보이며 진료과목과 운영 여부는 방문 전에 확인해주세요.</p>}
      </section>

      <Link className="text-link" to="/">← 메인으로</Link>
    </div>
  )
}
