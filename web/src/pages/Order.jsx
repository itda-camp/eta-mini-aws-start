import { useState } from 'react'
import { api } from '../api.js'

export default function Order() {
  const [distance, setDistance] = useState(3)
  const [pending, setPending] = useState(2)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  async function submit(e) {
    e.preventDefault()
    setError('')
    try {
      setResult(await api.eta(Number(distance), Number(pending)))
    } catch (err) {
      setError(err.message) // 422 면 서버가 어떤 필드가 왜 틀렸는지 알려준다 — /api/docs 의 스키마와 같다
    }
  }

  return (
    <form onSubmit={submit} className="card">
      <h2>도착 예정시간</h2>
      <label>거리 (km) <input type="number" step="0.1" min="0" max="20" value={distance} onChange={(e) => setDistance(e.target.value)} /></label>
      <label>대기 주문 (건) <input type="number" min="0" max="100" value={pending} onChange={(e) => setPending(e.target.value)} /></label>
      <button type="submit">예측</button>
      {error && <p className="error">{error}</p>}
      {result && (
        <p className="result">
          약 <strong>{result.minutes.toFixed(1)}분</strong> 후 도착
          <span className="muted"> · 주문 #{result.order_id} · 모델 {result.model}</span>
        </p>
      )}
    </form>
  )
}
