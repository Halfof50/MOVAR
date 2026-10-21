import { isLocalAuth } from '../services/authMode'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate } from 'react-router'
import { useAccount, errorMessage } from '../account/AccountContext'
import { accountApi } from '../services/accountApi'
import { authConfigError } from '../services/supabase'

export default function SignUpPage() {
  const { user } = useAccount()
  const [nickname, setNickname] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [submitted, setSubmitted] = useState(false)
  if (user) return <Navigate to="/mypage" replace />
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setError('')
    if (password !== confirm) { setError('비밀번호가 서로 일치하지 않아요.'); return }
    setBusy(true)
    try {
      const signedIn = await accountApi.signUp(email, password, nickname)
      setPassword(''); setConfirm('')
      if (!signedIn) setSubmitted(true)
    } catch (error) { setError(errorMessage(error)) }
    finally { setBusy(false) }
  }
  return <section className="card narrow account-page">
    <p className="eyebrow">MY MOVAR</p><h1>회원가입</h1>
    {submitted ? <div className="signup-confirmation" role="status">
      <h2>이메일을 확인해주세요</h2>
      <p><strong>{email.trim()}</strong> 주소로 받은 인증 메일의 링크를 눌러 가입을 완료해주세요.</p>
      <p>이미 가입한 주소라면 새 메일이 오지 않을 수 있어요. 기존 계정으로 로그인해주세요.</p>
      <p className="account-small">메일이 보이지 않으면 스팸함을 확인해주세요. 발송이 계속되지 않으면 관리자에게 문의해주세요.</p>
      <Link className="button" to="/login">로그인으로 이동</Link>
      <button className="text-link signup-back" type="button" onClick={() => { setSubmitted(false); setError('') }}>입력 화면으로 돌아가기</button>
    </div> : <>
      <p>나만의 닉네임으로 두피 케어를 시작하세요.</p>
      {isLocalAuth && <p className="notice">로컬 시연용 계정이에요. 이메일 인증 없이 바로 가입되며, 이 브라우저에서만 사용할 수 있어요. 시연용 비밀번호를 입력해주세요.</p>}
      <form className="account-form" onSubmit={submit}>
        <label htmlFor="signup-nickname">닉네임</label>
        <input id="signup-nickname" autoComplete="nickname" value={nickname} onChange={e=>setNickname(e.target.value)} required minLength={2} maxLength={20} disabled={busy} aria-describedby="signup-nickname-help" />
        <p id="signup-nickname-help" className="field-help">2~20자, 가입 후 변경할 수 있어요.</p>
        <label htmlFor="signup-email">이메일</label>
        <input id="signup-email" type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} required disabled={busy} />
        <label htmlFor="signup-password">비밀번호</label>
        <input id="signup-password" type="password" autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)} required minLength={8} disabled={busy} aria-describedby="signup-password-help" />
        <p id="signup-password-help" className="field-help">8자 이상 입력해주세요.</p>
        <label htmlFor="signup-confirm">비밀번호 확인</label>
        <input id="signup-confirm" type="password" autoComplete="new-password" value={confirm} onChange={e=>setConfirm(e.target.value)} required minLength={8} disabled={busy} />
        {(error || authConfigError) && <p role="alert" className="account-error">{error || authConfigError}</p>}
        <button className="button" disabled={busy || !!authConfigError}>{busy ? '가입 요청 중…' : '회원가입'}</button>
      </form>
      <p>이미 계정이 있나요? <Link className="text-link" to="/login">로그인</Link></p>
    </>}
    <Link className="text-link" to="/">게스트로 계속 이용하기 →</Link>
  </section>
}
