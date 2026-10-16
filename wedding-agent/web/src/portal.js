// 内部站点（后台 /api/admin、图墙 /api/gallery）的请求封装：全部带 CSRF 头；登录失效时回到邀请码页。
import { request } from './http.js'

const CSRF = { 'X-Portal-CSRF': '1' }

export function makePortal(site) {
  const prefix = `/api/${site}`
  async function call(path, options = {}) {
    try {
      return await request(prefix + path, { ...options, headers: { ...CSRF, ...(options.headers || {}) } })
    } catch (e) {
      if (e.code === 'PORTAL_UNAUTHORIZED' || e.code === 'PORTAL_FORBIDDEN') location.reload()
      throw e
    }
  }
  const json = (method, path, body) => call(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  return {
    prefix,
    call,
    json,
    status: () => request(prefix + '/status'),
    redeem: (code) => request(prefix + '/redeem', { method: 'POST', headers: { ...CSRF, 'Content-Type': 'application/json' }, body: JSON.stringify({ code }) }),
    logout: () => call('/logout', { method: 'POST' }),
  }
}

export const when = (ts) => (ts ? new Date(ts * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—')
