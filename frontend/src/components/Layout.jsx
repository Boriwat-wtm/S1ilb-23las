import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-brand">
          <span className="topbar-logo" aria-hidden="true">฿</span>
          <span>Bank</span>
        </div>
        <div className="topbar-right">
          <span className="topbar-user">{user?.display_name}</span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => {
              logout()
              navigate('/')
            }}
          >
            ออก
          </button>
        </div>
      </header>

      <main className="content">
        <Outlet />
      </main>

      <nav className="tabbar">
        <NavLink to="/" end className={({ isActive }) => `tab${isActive ? ' active' : ''}`}>
          <span aria-hidden="true">📋</span>
          <span>รายการ</span>
        </NavLink>
        <NavLink to="/add" className={({ isActive }) => `tab tab-add${isActive ? ' active' : ''}`}>
          <span aria-hidden="true">＋</span>
          <span>เพิ่ม</span>
        </NavLink>
        <NavLink to="/summary" className={({ isActive }) => `tab${isActive ? ' active' : ''}`}>
          <span aria-hidden="true">📊</span>
          <span>สรุป</span>
        </NavLink>
      </nav>
    </div>
  )
}
