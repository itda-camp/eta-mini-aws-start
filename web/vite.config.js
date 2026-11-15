import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 개발 서버(npm run dev, 5173)에서도 /api 는 FastAPI(8000)로 넘긴다.
// 운영(Compose)에서는 nginx.conf 가 같은 일을 한다. 둘 다 "같은 출처" 를 만들어 CORS 를 피한다.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
})
