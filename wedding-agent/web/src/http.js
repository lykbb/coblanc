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
  if (res.ok && !type.includes('json')) throw new Error('服务返回的不是数据，请稍后再试')
  const data = await res.json().catch(() => ({}))
  // 401（LOGIN_REQUIRED 登录过期 / ACCESS_DENIED 邀请码失效 / PORTAL_UNAUTHORIZED）：刷新页面，nginx 转到登录页或邀请码页
  if (res.status === 401) location.reload()
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

