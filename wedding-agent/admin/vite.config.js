import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后台站点：独立构建、独立部署（nginx 见 deploy/nginx/）。设计变量、图标、请求封装、邀请码页与用户站共用 @web。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@web': fileURLToPath(new URL('../web/src', import.meta.url)) },
    dedupe: ['vue'],
  },
  server: {
    port: 5174,
    proxy: {
      '/api': process.env.API_TARGET || 'http://127.0.0.1:8000',
      '/files': process.env.API_TARGET || 'http://127.0.0.1:8000',
    },
  },
})
