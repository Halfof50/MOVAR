import { BrowserRouter, Link, Route, Routes } from 'react-router'
import AppLayout from './layouts/AppLayout'
import HomePage from './pages/HomePage'
import CapturePage from './pages/CapturePage'
import LoginPage from './pages/LoginPage'
import HospitalsPage from './pages/HospitalsPage'
import ComingSoonPage from './pages/ComingSoonPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<HomePage />} />
          <Route path="login" element={<LoginPage />} />
          <Route path="hospitals" element={<HospitalsPage />} />
          <Route path="capture" element={<CapturePage />} />
          <Route
            path="results"
            element={
              <ComingSoonPage
                title="분석 결과"
                description="두피 사진의 분석 결과를 확인할 공간이에요."
              />
            }
          />
          <Route
            path="care"
            element={
              <ComingSoonPage
                title="맞춤 케어"
                description="문진과 분석 결과를 바탕으로 관리 방법을 안내할 예정이에요."
              />
            }
          />
          <Route
            path="history"
            element={
              <ComingSoonPage
                title="변화 기록"
                description="이전 분석 결과와 두피 상태 변화를 확인할 공간이에요."
              />
            }
          />
          <Route
            path="*"
            element={
              <section className="card narrow">
                <h1>페이지를 찾을 수 없어요</h1>
                <Link className="button" to="/">대시보드로 돌아가기</Link>
              </section>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}