import { useState } from 'react'
import { api } from '../api.js'

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('viewer')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [mode, setMode] = useState('login') // login | register

  async function submit(e) {
    e.preventDefault()
    setError('')
    try {
      if (mode === 'register') await api.register(username, password)
      const me = await api.login(username, password) // 응답의 Set-Cookie 는 브라우저가 저장한다
      onLogin(me)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <form onSubmit={submit} className="card">
      <h2>{mode === 'login' ? '로그인' : '가입'}</h2>
      <label>아이디 <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" /></label>
      <label>비밀번호 <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
      {error && <p className="error">{error}</p>}
      <button type="submit">{mode === 'login' ? '로그인' : '가입하고 로그인'}</button>
      <p className="muted">
        {mode === 'login' ? '계정이 없나요? ' : '이미 계정이 있나요? '}
        <a href="#" onClick={(e) => { e.preventDefault(); setMode(mode === 'login' ? 'register' : 'login') }}>
          {mode === 'login' ? '가입' : '로그인'}
        </a>
      </p>
    </form>
  )
}
