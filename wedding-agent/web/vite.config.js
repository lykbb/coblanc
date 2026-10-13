import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发时 /api 转发到后端（uv run uvicorn app.api:app --port 8000）
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
