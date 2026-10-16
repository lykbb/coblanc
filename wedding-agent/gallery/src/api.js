// 图墙接口（/api/gallery）
import { makePortal } from '@web/portal.js'

export const portal = makePortal()
const { call, json } = portal

export const refs = {
  styles: () => call('/refs/styles'),
  tags: () => call('/refs/tags'),
  list: (params) => call('/refs?' + new URLSearchParams(params)),
  upload(file, meta) {
    const form = new FormData()
    form.append('files', file)
    for (const [key, value] of Object.entries(meta)) form.append(key, value ?? '')
    return call('/refs', { method: 'POST', body: form })
  },
  update: (id, changes) => json('PATCH', `/refs/${id}`, changes),
  remove: (id) => call(`/refs/${id}`, { method: 'DELETE' }),
  zipUrl: (params) => portal.url('refs/zip?' + new URLSearchParams(params)),
  url: portal.url,
}
export const links = {
  list: (params) => call('/links?' + new URLSearchParams(params)),
  add: (body) => json('POST', '/links', body),
  update: (id, changes) => json('PATCH', `/links/${id}`, changes),
  remove: (id) => call(`/links/${id}`, { method: 'DELETE' }),
  refetch: (id) => call(`/links/${id}/refetch`, { method: 'POST' }),
  preview(id, file) {
    const form = new FormData()
    form.append('file', file)
    return call(`/links/${id}/preview`, { method: 'POST', body: form })
  },
}
export { when } from '@web/portal.js'
