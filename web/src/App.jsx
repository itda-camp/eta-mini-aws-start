import { useEffect, useState } from 'react'
import { Link, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { api } from './api.js'
import Login from './pages/Login.jsx'
import Order from './pages/Order.jsx'
import History from './pages/History.jsx'

// 컴포넌트 = 함수. 화면에 보일 상태(user)를 useState 로 들고, 바뀌면 다시 그린다.
export default function App() {
  const [user, setUser] = useState(undefined) // undefined: 아직 모름, null: 비로그인
  const navigate = useNavigate()

  // 처음 열 때 한 번 : 쿠키가 살아 있으면 /api/me 가 200 → 로그인 상태로 시작
  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null))
  }, [])

  async function handleLogout() {
    await api.logout()
    setUser(null)
    navigate('/login')
  }

  if (user === undefined) return <p className="muted">확인 중…</p>

  return (
    <>
      <header>
        <Link to="/" className="brand">eta-mini on AWS</Link>
        <nav>
          {user ? (
            <>
              <Link to="/">주문</Link>
              <Link to="/history">내 이력</Link>
              <span className="muted">{user.username} ({user.role})</span>
              <button onClick={handleLogout}>로그아웃</button>
            </>
          ) : (
            <Link to="/login">로그인</Link>
          )}
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/login" element={user ? <Navigate to="/" /> : <Login onLogin={setUser} />} />
          <Route path="/" element={user ? <Order /> : <Navigate to="/login" />} />
          <Route path="/history" element={user ? <History /> : <Navigate to="/login" />} />
        </Routes>
      </main>
    </>
  )
}
