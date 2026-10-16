// 和后端通信的底层：错误统一成 Error（带 code / httpStatus）。用户站 api.js 和后台共用。
export const BASE = import.meta.env.VITE_API_BASE || ''

export async function request(path, options = {}) {
  let res
  try {
    res = await fetch(BASE + path, options)
  } catch {
    throw new Error('连不上服务，请检查网络或稍后再试')
  }
  const type = res.headers.get('content-type') || ''
  if (res.ok && (res.redirected || !type.includes('json'))) {
    // 会话过期时 nginx 把接口请求转到登录页（HTML）：回到登录页，不把空数据交给页面
    location.reload()
    const error = new Error('登录已过期，请重新登录')
    error.code = 'SESSION_EXPIRED'
    throw error
  }
  const data = await res.json().catch(() => ({}))
  if (res.status === 401 && data?.error?.code === 'ACCESS_DENIED') {
    location.reload() // 用户站设备凭证失效或被作废：回到邀请码页
  }
  if (!res.ok) {
    const fallback = res.status === 413 ? '图片太大了，单张请控制在 10 MB 以内' : '出了点问题，请稍后再试'
    const error = new Error(data?.error?.message || fallback)
    error.code = data?.error?.code
    error.httpStatus = res.status
    error.body = data
    throw error
  }
  return data
}

export function post(path, body, headers = {}) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
  })
}

