import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 图墙站点：独立构建、独立部署（nginx 见 deploy/nginx/）。设计变量、图标、请求封装、邀请码页与用户站共用 @web。
// 部署方式：SITE_MODE=path（默认，站点在 /gallery/）或 subdomain（站点在子域名根 /），与 deploy.sh 一致
const BASE = process.env.SITE_MODE === 'subdomain' ? '/' : '/gallery/'
const API = process.env.API_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  base: BASE,
  plugins: [vue()],
  resolve: {
    alias: { '@web': fileURLToPath(new URL('../web/src', import.meta.url)) },
    dedupe: ['vue'],
  },
  server: {
    port: 5175,
    // 开发时模拟 nginx：<前缀>api/ → 后端 /api/gallery/，并带上站点前缀
    proxy: {
      [BASE + 'api']: { target: API, rewrite: (p) => p.replace(BASE + 'api', '/api/gallery'), headers: { 'X-Forwarded-Prefix': BASE } },
    },
  },
})
