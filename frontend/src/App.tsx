import { useCallback, useEffect, useRef, useState } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router'
import ResultsPage from './pages/ResultsPage'
import type { AnalysisPhoto } from './data/scalpResults'
import AppLayout from './layouts/AppLayout'
import HomePage from './pages/HomePage'
import CapturePage from './pages/CapturePage'
import LoginPage from './pages/LoginPage'
import SignUpPage from './pages/SignUpPage'
import HospitalsPage from './pages/HospitalsPage'
import MyPage from './pages/MyPage'
import CarePage from './pages/CarePage'
import HistoryDetailPage from './pages/HistoryDetailPage'
import AccountProvider from './account/AccountProvider'
import { useAccount, errorMessage } from './account/AccountContext'
import type { AnalysisResult } from './services/api'
import './account/Account.css'

function SessionRoutes() {
  const { user, analysisSaved } = useAccount()
  const [resultPhoto, setResultPhoto] = useState<AnalysisPhoto | null>(null)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [saveError, setSaveError] = useState('')
  const resultUrl = useRef<string | null>(null)
  // The backend has already stored the analysis; signed-in users only need it linked to their account.
  const completeAnalysis = useCallback((analysis: AnalysisResult, blob: Blob, name: string) => {
    const url = URL.createObjectURL(blob)
    if (resultUrl.current) URL.revokeObjectURL(resultUrl.current)
    resultUrl.current = url
    setResultPhoto({ url, name })
    setResult(analysis)
    setSaveError('')
    if (user && analysis.analysis_id !== null)
      analysisSaved(analysis.analysis_id).catch(error => setSaveError(errorMessage(error)))
  }, [user, analysisSaved])
  useEffect(() => () => { if (resultUrl.current) URL.revokeObjectURL(resultUrl.current) }, [])
  return <Routes><Route element={<AppLayout />}>
    <Route index element={<HomePage />} />
    <Route path="login" element={<LoginPage />} />
    <Route path="signup" element={<SignUpPage />} />
    <Route path="hospitals" element={<HospitalsPage />} />
    <Route path="capture" element={<CapturePage onAnalysisComplete={completeAnalysis} />} />
    <Route path="results" element={<div className="stack">
      {result && (user ? <div className="notice" role="status">{saveError ? <p role="alert">{saveError}</p> : <>마이페이지에 분석 기록을 저장했어요. <Link to="/mypage">기록 보기 →</Link></>}</div> : <div className="notice">게스트 분석은 기록으로 저장되지 않아요. <Link to="/login">로그인 후 새 분석부터 기록하기 →</Link></div>)}
      <ResultsPage photo={resultPhoto} result={result ?? undefined} />
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
