import { Link, NavLink, Outlet } from 'react-router'

const menus = [
  { path: '/', label: '대시보드', icon: '⌂' },
  { path: '/capture', label: '두피 촬영', icon: '◎' },
  { path: '/results', label: '분석 결과', icon: '▥' },
  { path: '/care', label: '맞춤 케어', icon: '♧' },
  { path: '/history', label: '변화 기록', icon: '▦' },
]

export default function AppLayout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" to="/" aria-label="MOVAR 홈">
          <span className="brand-mark" aria-hidden="true">M</span>
          MOVAR
        </Link>

        <nav className="navigation" aria-label="주 메뉴">
          {menus.map((menu) => (
            <NavLink key={menu.path} to={menu.path} end={menu.path === '/'}>
              <span className="menu-icon" aria-hidden="true">{menu.icon}</span>
              {menu.label}
            </NavLink>
          ))}
        </nav>

        <section className="sidebar-hospital">
          <h2>내 주변 병원 찾기</h2>
          <p>가까운 병원을 찾아 두피 관리에 대한 상담을 받아보세요.</p>
          <Link className="button" to="/hospitals">병원 찾기 →</Link>
        </section>
      </aside>

      <div className="workspace">
        <header className="header">
          <span>나의 두피 케어</span>
          <div className="account">
            <span className="badge">게스트</span>
            <Link className="text-link" to="/login">로그인</Link>
          </div>
        </header>

        <main className="main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}