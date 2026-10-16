// 内部站点（后台、图墙）的请求封装：全部带 CSRF 头；后台会话失效时回登录页。
// 站点接口根是 <站点前缀>api（path 模式 /gallery/api，子域名模式 /api），nginx 转到后端 /api/<站点>/。
import { request } from './http.js'

const CSRF = { 'X-Portal-CSRF': '1' }
const ROOT = import.meta.env.BASE_URL + 'api'

export function makePortal() {
  const prefix = ROOT
  async function call(path, options = {}) {
    try {
      return await request(prefix + path, { ...options, headers: { ...CSRF, ...(options.headers || {}) } })
    } catch (e) {
      if (e.code === 'PORTAL_UNAUTHORIZED' || e.code === 'PORTAL_FORBIDDEN') location.reload() // nginx 会转到登录页或拒绝
      throw e
    }
  }
  const json = (method, path, body) => call(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  return {
    prefix,
    call,
    json,
    status: () => request(prefix + '/status'),
    url: (rel) => `${ROOT}/${rel}`, // 后端返回的相对接口地址（如 refs/<id>/image）
    asset: (path) => import.meta.env.BASE_URL + path.replace(/^\//, ''), // 用户站文件 /files/...，经本站前缀转发
  }
}

export const when = (ts) => (ts ? new Date(ts * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—')
