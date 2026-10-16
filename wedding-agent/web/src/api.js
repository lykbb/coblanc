// 和后端通信的唯一出口，6 个接口对应《小囍接口约定》。
// VITE_USE_MOCK=true 时改用 src/mock 里的假数据，不需要启动后端。
// 每个接口最近一次的请求和返回记在 apiLog 里，给页面上的「接口调试」面板看。
import { reactive } from 'vue'
import * as mock from './mock/index.js'
import { BASE, post, request } from './http.js'

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

export const ENDPOINTS = {
  uploadImage: 'POST /api/uploads',
  createTask: 'POST /api/tasks',
  getTask: 'GET /api/tasks/{task_id}',
  submitAnswers: 'POST /api/tasks/{task_id}/answers',
  review: 'POST /api/tasks/{task_id}/review',
  pay: 'POST /api/tasks/{task_id}/pay',
  retry: 'POST /api/tasks/{task_id}/retry',
}
export const apiLog = reactive({})

const real = {
  uploadImage(file) {
    const form = new FormData()
    form.append('file', file)
    return request('/api/uploads', { method: 'POST', body: form })
  },
  createTask(body) {
    return post('/api/tasks', body)
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
  pay(taskId, method = 'mock') {
    return post(`/api/tasks/${taskId}/pay`, { method })
  },
  retry(taskId) {
    return post(`/api/tasks/${taskId}/retry`, {})
  },
}

// 邀请码不进调试面板；mock 模式不需要邀请码
export function accessStatus() {
  return USE_MOCK ? Promise.resolve({ authorized: true }) : request('/api/access/status')
}
export function redeemInvite(code) {
  return post('/api/access/redeem', { code })
}

const impl = USE_MOCK ? mock : real

// 调试面板里展示的请求体（上传只记文件名和大小）
function describe(name, args) {
  if (name === 'uploadImage') return { file: args[0]?.name, size: args[0]?.size, type: args[0]?.type }
  if (name === 'createTask') return args[0]
  if (name === 'getTask') return { task_id: args[0] }
  if (name === 'submitAnswers') return { task_id: args[0], body: { answers: args[1] } }
  if (name === 'review') return { task_id: args[0], body: args[1] }
  if (name === 'pay') return { task_id: args[0], body: { method: args[1] || 'mock' } }
  return args
}

export const api = Object.fromEntries(
  Object.keys(ENDPOINTS).map((name) => [
    name,
    async (...args) => {
      const entry = { at: new Date().toLocaleTimeString(), request: describe(name, args), response: null, error: null }
      try {
        entry.response = await impl[name](...args)
        return entry.response
      } catch (error) {
        entry.error = { http_status: error.httpStatus ?? null, code: error.code ?? null, message: error.message, body: error.body ?? null }
        throw error
      } finally {
        apiLog[name] = entry
      }
    },
  ]),
)
export const usingMock = USE_MOCK
