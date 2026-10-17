import { useCallback, useEffect, useRef, useState } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router'
import ResultsPage from './pages/ResultsPage'
import type { AnalysisPhoto } from './data/scalpResults'
import AppLayout from './layouts/AppLayout'
import HomePage from './pages/HomePage'
import CapturePage from './pages/CapturePage'
import LoginPage from './pages/LoginPage'
import HospitalsPage from './pages/HospitalsPage'
import MyPage from './pages/MyPage'
import CarePage from './pages/CarePage'
import HistoryDetailPage from './pages/HistoryDetailPage'
import AccountProvider from './account/AccountProvider'
import { useAccount, errorMessage } from './account/AccountContext'
import { createDemoRecord } from './services/accountApi'
import type { AnalysisRecord } from './services/accountApi'
import './account/Account.css'

function SessionRoutes() {
  const { user, save } = useAccount()
  const [resultPhoto, setResultPhoto] = useState<AnalysisPhoto | null>(null)
  const [currentRecord, setCurrentRecord] = useState<AnalysisRecord | null>(null)
  const [saveState, setSaveState] = useState('')
  const [saveError, setSaveError] = useState('')
  const resultUrl = useRef<string | null>(null)
  const persist = useCallback(async (record: AnalysisRecord) => {
    setSaveState('saving'); setSaveError('')
    try { await save(record); setSaveState('saved') }
    catch(error) { setSaveState('error'); setSaveError(errorMessage(error)) }
  }, [save])
  const completeAnalysis = useCallback((blob: Blob, name: string) => {
    const url = URL.createObjectURL(blob)
    if (resultUrl.current) URL.revokeObjectURL(resultUrl.current)
    resultUrl.current = url
    setResultPhoto({ url, name })
    if (user) {
      const record = createDemoRecord(user.id, name)
      setCurrentRecord(record)
      void persist(record)
    }
  }, [user, persist])
  useEffect(() => () => { if (resultUrl.current) URL.revokeObjectURL(resultUrl.current) }, [])
  return <Routes><Route element={<AppLayout />}>
    <Route index element={<HomePage />} />
    <Route path="login" element={<LoginPage />} />
    <Route path="hospitals" element={<HospitalsPage />} />
    <Route path="capture" element={<CapturePage onAnalysisComplete={completeAnalysis} />} />
    <Route path="results" element={<div className="stack">
      {resultPhoto && (user ? <div className="notice" role="status">{saveState === 'saved' ? <>마이페이지에 데모 기록을 저장했어요. <Link to="/mypage">기록 보기 →</Link></> : saveState === 'saving' ? '기록 저장 중…' : <><p role="alert">{saveError}</p><button className="button" onClick={()=>currentRecord && void persist(currentRecord)}>저장 다시 시도</button></>}</div> : <div className="notice">게스트 분석은 저장되지 않아요. <Link to="/login">로그인 후 새 분석부터 기록하기 →</Link></div>)}
      <ResultsPage photo={resultPhoto} record={currentRecord ?? undefined} />
    </div>} />
    <Route path="care" element={<CarePage />} />
    <Route path="mypage" element={<MyPage />} />
    <Route path="history" element={<Navigate to="/mypage" replace />} />
    <Route path="history/:id" element={<HistoryDetailPage />} />
    <Route path="*" element={<section className="card narrow"><h1>페이지를 찾을 수 없어요</h1><Link className="button" to="/">대시보드로 돌아가기</Link></section>} />
  </Route></Routes>
}
function SessionApp() {
  const { user, ready } = useAccount()
  if (!ready) return <main className="main" role="status">계정 정보를 확인하고 있어요…</main>
  // Reset transient photos and routes when identity changes, including logout.
  return <SessionRoutes key={user?.id ?? 'guest'} />
}
export default function App() {
  return <BrowserRouter><AccountProvider><SessionApp /></AccountProvider></BrowserRouter>
}
