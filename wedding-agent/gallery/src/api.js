// 图墙接口（/api/gallery）
import { makePortal } from '@web/portal.js'

export const portal = makePortal('gallery')
const { call, json } = portal

export const refs = {
  styles: () => call('/refs/styles'),
  list: (params) => call('/refs?' + new URLSearchParams(params)),
  upload(file, meta) {
    const form = new FormData()
    form.append('files', file)
    for (const [key, value] of Object.entries(meta)) form.append(key, value ?? '')
    return call('/refs', { method: 'POST', body: form })
  },
  update: (id, changes) => json('PATCH', `/refs/${id}`, changes),
  remove: (id) => call(`/refs/${id}`, { method: 'DELETE' }),
  zipUrl: (params) => portal.prefix + '/refs/zip?' + new URLSearchParams(params),
}
export { when } from '@web/portal.js'
