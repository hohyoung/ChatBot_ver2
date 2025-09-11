import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // REST
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,         // ← WebSocket(/api/chat/)도 프록시
      },
      // 정적 원본 문서(iframe/pdf)
      '/static': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/openapi.json': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})
