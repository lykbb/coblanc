import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// public/ 里的静态原型（如 /coblanc-film/）：目录地址补上 index.html，
// 否则 Vite 会按单页应用回退，返回 Vue 版首页
const staticPrototypes = {
  name: 'static-prototype-index',
  configureServer(server) {
    server.middlewares.use((req, _res, next) => {
      const [path, query] = req.url.split('?')
      if (/^\/coblanc-film\/?$/.test(path)) req.url = '/coblanc-film/index.html' + (query ? '?' + query : '')
      next()
    })
  },
}

// 开发时 /api 转发到后端（uv run uvicorn app.api:app --port 8000）；
// 后端换了端口时用环境变量 API_TARGET 指定，例如 API_TARGET=http://127.0.0.1:8010
export default defineConfig({
  plugins: [staticPrototypes, vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': process.env.API_TARGET || 'http://127.0.0.1:8000',
    },
  },
})
