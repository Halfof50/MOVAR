import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router'
import { useAccount, errorMessage } from '../account/AccountContext'
import { DEMO_EMAIL, DEMO_PASSWORD } from '../services/accountApi'

export default function LoginPage() {
  const { user, login } = useAccount()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (user) return <Navigate to="/mypage" replace />
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try { await login(email, password); navigate('/mypage', { replace: true }) }
    catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }
  return <section className="card narrow account-page">
    <p className="eyebrow">MY MOVAR · DEMO</p><h1>로그인</h1>
    <p>분석 기록을 모아 나의 케어를 이어가세요.</p>
    <div className="notice"><strong>공개 테스트 계정</strong><p>이메일: {DEMO_EMAIL}<br />비밀번호: {DEMO_PASSWORD}</p>
      <button type="button" className="text-link" onClick={() => { setEmail(DEMO_EMAIL); setPassword(DEMO_PASSWORD) }}>테스트 계정 채우기</button></div>
    <form onSubmit={submit} className="account-form">
      <label htmlFor="login-email">이메일</label><input id="login-email" type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} required />
      <label htmlFor="login-password">비밀번호</label><input id="login-password" type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required />
      {error && <p role="alert" className="account-error">{error}</p>}
      <button className="button" disabled={busy}>{busy ? '로그인 중…' : '로그인'}</button>
    </form>
    <p className="account-small">테스트 계정 전용 데모입니다. 기록은 이 브라우저에 저장되며, 브라우저 데이터 삭제 시 사라집니다. 원본 사진은 저장하지 않아요.</p>
    <Link className="text-link" to="/">게스트로 계속 이용하기 →</Link>
  </section>
}
