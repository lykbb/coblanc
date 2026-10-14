// 和后端通信的唯一出口，6 个接口对应《小囍接口约定》。
// VITE_USE_MOCK=true 时改用 src/mock 里的假数据，不需要启动后端。
import * as mock from './mock/index.js'

const BASE = import.meta.env.VITE_API_BASE || ''
const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(BASE + path, options)
  } catch {
    throw new Error('连不上服务，请检查网络或稍后再试')
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const error = new Error(data?.error?.message || '出了点问题，请稍后再试')
    error.code = data?.error?.code
    throw error
  }
  return data
}

function post(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

const real = {
  uploadImage(file) {
    const form = new FormData()
    form.append('file', file)
    return request('/api/uploads', { method: 'POST', body: form })
  },
  // 新流程传 { groomFileIds, brideFileIds }；旧调用直接传 photo_file_ids 数组仍然可用。
  createTask(photos, description) {
    const body = Array.isArray(photos)
      ? { photo_file_ids: photos }
      : { groom_photo_file_ids: photos.groomFileIds, bride_photo_file_ids: photos.brideFileIds }
    return post('/api/tasks', { ...body, description })
  },
  getTask(taskId) {
    return request(`/api/tasks/${taskId}`)
  },
  submitAnswers(taskId, answers) {
    return post(`/api/tasks/${taskId}/answers`, { answers })
  },
  review(taskId, payload) {
    return post(`/api/tasks/${taskId}/review`, payload)
  },
  pay(taskId) {
    return post(`/api/tasks/${taskId}/pay`, { method: 'mock' })
  },
}

export const api = USE_MOCK ? mock : real
export const usingMock = USE_MOCK
