import { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function History() {
  const [orders, setOrders] = useState([])
  const [error, setError] = useState('')

  // 화면이 뜰 때 한 번 받아온다.
  useEffect(() => {
    api.orders().then(setOrders).catch((err) => setError(err.message))
  }, [])

  if (error) return <p className="error">{error}</p>

  return (
    <section className="card">
      <h2>내 주문 이력 <span className="muted">{orders.length}건</span></h2>
      <table>
        <thead>
          <tr><th>#</th><th>거리</th><th>대기</th><th>예상</th><th>모델</th><th>시각</th></tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id}>
              <td>{o.id}</td>
              <td>{o.distance_km} km</td>
              <td>{o.pending_orders}</td>
              <td>{o.minutes.toFixed(1)} 분</td>
              <td>{o.model}</td>
              <td>{new Date(o.created_at).toLocaleString('ko-KR')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
