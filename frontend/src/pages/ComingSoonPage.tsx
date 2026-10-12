import { Link } from 'react-router'

type Props = {
  title: string
  description: string
}

export default function ComingSoonPage({ title, description }: Props) {
  return (
    <section className="card narrow">
      <span className="badge">준비 중</span>
      <h1>{title}</h1>
      <p>{description}</p>
      <Link className="button" to="/">대시보드로 돌아가기</Link>
    </section>
  )
}