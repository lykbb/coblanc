// 后台接口：全部带 CSRF 头；登录失效时回到邀请码页。
import { request } from '@web/http.js'

const CSRF = { 'X-Admin-CSRF': '1' }

async function call(path, options = {}) {
  try {
    return await request(path, { ...options, headers: { ...CSRF, ...(options.headers || {}) } })
  } catch (e) {
    if (e.code === 'ADMIN_UNAUTHORIZED' || e.code === 'ADMIN_FORBIDDEN') location.reload()
    throw e
  }
}
const json = (method, path, body) => call(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const status = () => request('/api/admin/status')
export const redeem = (code) => request('/api/admin/redeem', { method: 'POST', headers: { ...CSRF, 'Content-Type': 'application/json' }, body: JSON.stringify({ code }) })
export const logout = () => call('/api/admin/logout', { method: 'POST' })

export const invites = {
  list: () => call('/api/admin/access'),
  create: (body) => json('POST', '/api/admin/access/codes', body),
  revokeHolder: (holder) => json('POST', '/api/admin/access/revoke', { holder }),
  revokeDevice: (id) => call(`/api/admin/access/devices/${id}`, { method: 'DELETE' }),
}

export const tasks = {
  list: () => call('/api/admin/tasks'),
  get: (id) => call(`/api/admin/tasks/${id}`),
}

export const auditLog = () => call('/api/admin/audit')

export const refs = {
  styles: () => call('/api/admin/refs/styles'),
  list: (params) => call('/api/admin/refs?' + new URLSearchParams(params)),
  upload(file, meta) {
    const form = new FormData()
    form.append('files', file)
    for (const [key, value] of Object.entries(meta)) form.append(key, value ?? '')
    return call('/api/admin/refs', { method: 'POST', body: form })
  },
  update: (id, changes) => json('PATCH', `/api/admin/refs/${id}`, changes),
  remove: (id) => call(`/api/admin/refs/${id}`, { method: 'DELETE' }),
  zipUrl: (params) => '/api/admin/refs/zip?' + new URLSearchParams(params),
}

export const when = (ts) => (ts ? new Date(ts * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—')
