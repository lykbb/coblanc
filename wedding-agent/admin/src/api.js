// 后台管理接口（/api/admin）
import { makePortal } from '@web/portal.js'

export const portal = makePortal('admin')
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
export const auditLog = () => call('/audit')
export { when } from '@web/portal.js'
