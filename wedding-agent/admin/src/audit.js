// 审计时间线：把后端的原始记录变成中文句子、分组合并、按天归档。
export const SITES = { front: '前台', gallery: '图墙', admin: '后台' }
// fail2ban 规则名（deploy/fail2ban/wedding.jail）
const JAILS = { 'wedding-login': '登录输错太多次', 'wedding-scan': '扫描敏感路径', 'wedding-ratelimit': '频繁触发限流', sshd: 'SSH 登录失败' }
export const SECURITY = new Set(['login_failed', 'login_locked', 'forbidden', 'csrf_rejected', 'rate_limited', 'banned', 'unbanned'])
export const TYPES = {
  visit: '访问', login: '登录', logout: '退出', task_created: '创建任务',
  refs_uploaded: '上传参考图', ref_edited: '编辑参考图', ref_deleted: '删除参考图', refs_zipped: '打包下载', refs_exported: '导出元数据',
  link_added: '添加链接', link_edited: '编辑链接', link_deleted: '删除链接', link_preview_uploaded: '上传链接预览图',
  style_added: '新增风格分类', style_renamed: '重命名风格分类', style_deleted: '删除风格分类',
  codes_created: '生成邀请码', holder_revoked: '作废持有人', device_revoked: '踢掉设备', file_viewed: '查看文件', file_downloaded: '下载文件',
  usage_imported: '导入用量账单',
  login_failed: '登录失败', login_locked: '登录锁定', forbidden: '访问被拒', csrf_rejected: '拦截跨站请求', rate_limited: '限流', banned: '封禁', unbanned: '解封',
}
const VERDICT = { good: '好', bad: '不好' }
const MERGE_GAP = 5 * 60 // 同一人同一动作 5 分钟内的连续记录合并成一条

export function device(ua) {
  if (!ua) return ''
  if (/curl|python|wget|go-http|bot|spider|scan/i.test(ua)) return ua.split(/[ /]/)[0]
  const wechat = /MicroMessenger/i.test(ua)
  const os = /iPad/.test(ua) ? 'iPad' : /iPhone|Android.*Mobile|Mobile/.test(ua) ? '手机' : /Android/.test(ua) ? '平板'
    : /Macintosh/.test(ua) ? 'Mac' : /Windows/.test(ua) ? 'Windows' : /Linux/.test(ua) ? 'Linux' : ''
  const browser = wechat ? '微信' : /Edg\//.test(ua) ? 'Edge' : /Firefox\//.test(ua) ? 'Firefox' : /HeadlessChrome/.test(ua) ? '无头 Chrome'
    : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : ''
  return wechat ? `${os}微信` : [os, browser].filter(Boolean).join(' ') || ua.slice(0, 24)
}

// 后台的登录账号就是本人；前台账号可能共用（如 xiaoxi），以设备 / IP 对应的成员为准
export const who = (e) => (e.site === 'admin' && e.holder) || e.user || (e.holder && e.holder !== e.ip ? e.holder : '')
export const category = (e) => (SECURITY.has(e.action) ? 'security' : e.site || 'security')

function mergeKey(e) {
  const d = e.detail || {}
  return [e.action, who(e) || e.ip, e.site, d.style, d.verdict].join('|')
}

/** items：最新在前。连续（中间没有别的记录）的同类记录合并，参考图上传张数相加。 */
export function group(items) {
  const out = []
  for (const e of items) {
    const last = out[out.length - 1]
    const mergeable = ['refs_uploaded', 'ref_edited', 'ref_deleted', 'visit', 'forbidden', 'rate_limited', 'login_failed', 'file_viewed', 'link_edited']
    if (last && mergeable.includes(e.action) && mergeKey(last) === mergeKey(e) && last.first - e.at <= MERGE_GAP) {
      last.parts.push(e)
      last.first = e.at
      continue
    }
    out.push({ ...e, parts: [e], first: e.at })
  }
  return out
}

const n = (g, f) => g.parts.reduce((s, e) => s + f(e), 0)

export function sentence(g) {
  const d = g.detail || {}
  const site = SITES[g.site] || ''
  const p = who(g)
  const someone = p || '有人'
  const times = g.parts.length > 1 ? ` ${g.parts.length} 次` : ''
  const dev = device(g.ua)
  switch (g.action) {
    case 'visit': return `${someone} 访问了${site}${times}`
    case 'login': return `${p || g.holder} ${dev ? '用' + dev : ''}登录了${site}${g.holder && p && g.holder !== p ? `（账号 ${g.holder}）` : ''}`
    case 'logout': return `${p || g.holder} 退出了${site}`
    case 'login_failed': return `${p ? p + ' ' : '有人'}用账号「${d.username || '?'}」登录${site}失败${times}`
    case 'login_locked': return `${g.ip} 登录${site}失败太多次，已被暂时锁定`
    case 'forbidden': return `${p ? p + ' ' : '有人'}从 ${g.ip} 访问${site}被拒（${d.reason === 'ip' || !d.reason ? '不在白名单' : d.reason}）${times}`
    case 'csrf_rejected': return `拦截了一次来自 ${g.ip} 的跨站请求（${site}）`
    case 'rate_limited': return `${g.ip} 请求${site || ''}太频繁，被限流${times}`
    case 'banned': return `${g.ip} 因${JAILS[d.jail] || d.jail}被 fail2ban 封禁`
    case 'unbanned': return `${g.ip} 的封禁已解除（${JAILS[d.jail] || d.jail}）`
    case 'task_created': return `${someone} 创建了任务 ${d.task_id}`
    case 'refs_uploaded': {
      const count = n(g, (e) => (e.detail?.ids || []).length)
      return `${someone} 上传了 ${count} 张参考图到 ${d.style || ''}${d.style_name ? ' ' + d.style_name : ''}（${VERDICT[d.verdict] || d.verdict}）`
    }
    case 'ref_edited': return g.parts.length > 1 ? `${someone} 编辑了 ${g.parts.length} 张参考图` : `${someone} 编辑了参考图 ${d.id}`
    case 'ref_deleted': return g.parts.length > 1 ? `${someone} 删除了 ${g.parts.length} 张参考图` : `${someone} 删除了参考图 ${d.id}`
    case 'refs_zipped': return `${someone} 打包下载了参考图${d.style ? '（' + d.style + (d.style_name ? ' ' + d.style_name : '') + '）' : ''}`
    case 'refs_exported': return `${someone} 导出了参考图元数据（${d.format}）`
    case 'link_added': return `${someone} 添加了来源链接 ${d.domain || ''}`
    case 'link_edited': return `${someone} 编辑了来源链接${times}`
    case 'link_deleted': return `${someone} 删除了一条来源链接`
    case 'link_preview_uploaded': return `${someone} 给来源链接上传了预览图`
    case 'style_added': return `${someone} 新增了风格分类「${d.id} ${d.name}」`
    case 'style_renamed': return `${someone} 把风格分类「${d.from}」改名为「${d.to}」`
    case 'style_deleted': return `${someone} 删除了风格分类「${d.id} ${d.name}」`
    case 'codes_created': return `${someone} 生成了邀请码：${(d.holders || []).join('、')}`
    case 'holder_revoked': return `${someone} 作废了 ${d.holder} 的邀请（${d.count} 台设备）`
    case 'device_revoked': return `${someone} 踢掉了一台设备`
    case 'file_viewed': return `${someone} 查看了文件 ${d.path}${times}`
    case 'file_downloaded': return `${someone} 下载了文件 ${d.path}`
    case 'usage_imported': return `${someone} 导入了 DeepSeek 用量账单（${d.rows} 行）`
    default: return `${someone} ${TYPES[g.action] || g.action}`
  }
}

export function dayKey(ts) {
  const t = new Date(ts * 1000)
  return `${t.getFullYear()}-${t.getMonth() + 1}-${t.getDate()}`
}

export function dayLabel(ts) {
  const t = new Date(ts * 1000)
  const today = new Date()
  const diff = Math.round((new Date(today.toDateString()) - new Date(t.toDateString())) / 86400000)
  const date = `${t.getMonth() + 1}月${t.getDate()}日 周${'日一二三四五六'[t.getDay()]}`
  return diff === 0 ? `今天 · ${date}` : diff === 1 ? `昨天 · ${date}` : date
}

export function relative(ts) {
  const s = Date.now() / 1000 - ts
  if (s < 60) return '刚刚'
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`
  if (s < 86400) return `${Math.floor(s / 3600)} 小时前`
  return `${Math.floor(s / 86400)} 天前`
}

export const clock = (ts) => new Date(ts * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })

const PALETTE = ['#f3c9b8', '#d9cdf3', '#c8e3d4', '#f5dfa8', '#c9dcf2', '#f2c6d8']
export function avatar(name) {
  if (!name) return { text: '?', color: '#e9e7ee' }
  let h = 0
  for (const ch of name) h = (h * 31 + ch.codePointAt(0)) >>> 0
  const text = /^[\x00-\x7f]/.test(name) ? name[0].toUpperCase() : [...name].slice(-1)[0]
  return { text, color: PALETTE[h % PALETTE.length] }
}
export const inferred = (e) => e.user_source === 'ip' && who(e) === e.user && !(e.site === 'admin' && e.holder)
// 左侧状态条：成功（放行的访问、登录、改动、任务）绿；失败 / 被拒红；纯信息（退出、解封）灰
const INFO = new Set(['logout', 'unbanned'])
export const auditKind = (e) => (INFO.has(e.action) ? 'info' : SECURITY.has(e.action) ? 'fail' : 'ok')
