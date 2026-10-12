import { Link } from 'react-router'

export default function LoginPage() {
  return (
    <section className="card narrow">
      <p className="eyebrow">ACCOUNT</p>
      <h1>로그인</h1>
      <p>현재는 게스트로 이용 중이에요.</p>

      <div className="notice">
        로그인 기능은 준비 중이에요.
        계정 연결이 완료되면 이 화면에서 로그인할 수 있어요.
      </div>

      <Link className="button" to="/">게스트로 계속 이용하기</Link>
    </section>
  )
}