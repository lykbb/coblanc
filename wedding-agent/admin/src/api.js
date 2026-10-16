// 后台管理接口（/api/admin）
import { makePortal } from '@web/portal.js'

export const portal = makePortal()
const { call, json } = portal

export const invites = {
  list: () => call('/access'),
  create: (body) => json('POST', '/access/codes', body),
  revokeHolder: (holder) => json('POST', '/access/revoke', { holder }),
  revokeDevice: (id) => call(`/access/devices/${id}`, { method: 'DELETE' }),
}
export const tasks = {
  list: () => call('/tasks'),
  get: (id) => call(`/tasks/${id}`),
}
export const outputs = {
  list: () => call('/outputs'),
  get: (id) => call(`/outputs/${id}`),
}
export const auditLog = () => call('/audit')
export { when } from '@web/portal.js'
export const ops = {
  usage: (period) => call('/usage?period=' + period),
  importUsage: (file) => { const body = new FormData(); body.append('file', file); return call('/usage/import', { method: 'POST', body }) },
  server: () => call('/server'),
  balance: () => call('/balance'),
  list: (path) => call('/files/list?' + new URLSearchParams({ path })),
  view: (path) => call('/files/view?' + new URLSearchParams({ path })),
  raw: (path, download = false) => portal.url('files/raw?' + new URLSearchParams(download ? { path, download: 1 } : { path })),
}
export const bytes = (n) => {
  if (n == null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`
}
