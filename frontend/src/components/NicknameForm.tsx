import { useState } from 'react'
import type { FormEvent } from 'react'
import { useAccount, errorMessage } from '../account/AccountContext'

export default function NicknameForm() {
  const { user, updateNickname } = useAccount()
  const [draft, setDraft] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  if (!user) return null
  const value = draft ?? user.name
  const valid = value.trim().length >= 2 && value.trim().length <= 20
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError(''); setSaved(false)
    try {
      await updateNickname(value)
      setDraft(null); setSaved(true)
    } catch (error) { setError(errorMessage(error)) }
    finally { setBusy(false) }
  }
  return <section className="card nickname-card" aria-labelledby="nickname-title">
    <h2 id="nickname-title">닉네임 변경</h2>
    <form className="account-form nickname-form" onSubmit={submit}>
      <label htmlFor="nickname">닉네임</label>
      <div className="nickname-controls">
        <input id="nickname" name="nickname" autoComplete="nickname" required maxLength={20}
          aria-describedby="nickname-help" disabled={busy} value={value}
          onChange={event => { setDraft(event.target.value); setError(''); setSaved(false) }} />
        <button className="button" disabled={busy || !valid}>{busy ? '저장 중…' : '닉네임 저장'}</button>
      </div>
      <p id="nickname-help" className="account-small">2~20자로 입력해주세요. 앞뒤 공백은 자동으로 제거돼요.</p>
      {error && <p className="account-error" role="alert">{error}</p>}
      {saved && <p className="nickname-success" role="status">닉네임을 변경했어요.</p>}
    </form>
  </section>
}
