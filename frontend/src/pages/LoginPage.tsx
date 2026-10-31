import { isLocalAuth } from '../services/authMode'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router'
import { useAccount, errorMessage } from '../account/AccountContext'
import { authConfigError } from '../services/supabase'

export default function LoginPage() {
  const { user, login, authError } = useAccount()
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
    <p className="eyebrow">MY MOVAR</p><h1>로그인</h1>
    <p>분석 기록을 모아 나의 케어를 이어가세요.</p>
    {isLocalAuth && <p className="notice">이 브라우저에서 가입한 시연용 계정으로 로그인해주세요.</p>}
    <form onSubmit={submit} className="account-form">
      <label htmlFor="login-email">이메일</label><input id="login-email" type="email" autoComplete="username" disabled={busy} value={email} onChange={e=>setEmail(e.target.value)} required />
      <label htmlFor="login-password">비밀번호</label><input id="login-password" type="password" autoComplete="current-password" disabled={busy} value={password} onChange={e=>setPassword(e.target.value)} required />
      {(error || authError) && <p role="alert" className="account-error">{error || authError}</p>}
      <button className="button" disabled={busy || !!authConfigError}>{busy ? '로그인 중…' : '로그인'}</button>
    </form>
    <p>아직 계정이 없나요? <Link className="text-link" to="/signup">회원가입</Link></p>
    <Link className="text-link" to="/">게스트로 계속 이용하기 →</Link>
  </section>
}
