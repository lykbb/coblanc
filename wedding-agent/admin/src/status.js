// 全后台的状态定义（唯一来源）：每个状态一种颜色 + 名字 + 一句解释。
// 列表行左侧的细条（StatusBar.vue）、各页图例（StatusLegend.vue）都从这里取，页面上不再单独写状态文字。
export const STATUSES = {
  // 任务
  done: { color: '#7fbf98', label: '完成', tip: '已交付成片' },
  failed: { color: '#e08b78', label: '失败', tip: '流程中断，需要重新开始' },
  preview_ready: { color: '#e6b85c', label: '待确认', tip: '预览已出，等用户确认' },
  waiting_user: { color: '#f0d36b', label: '等用户回答', tip: '小囍或师傅在等用户回答问题' },
  awaiting_payment: { color: '#b79be0', label: '待支付', tip: '用户确认了，等付款' },
  running: { color: '#8fb0e3', label: '进行中', tip: '正在生成或审片' },
  delivering: { color: '#6fc2c0', label: '交付中', tip: '正在出高清成片' },
  // 邀请码
  active: { color: '#7fbf98', label: '有效', tip: '已绑定设备，正在使用' },
  unused: { color: '#d4d1da', label: '未使用', tip: '邀请码还没被兑换' },
  revoked: { color: '#b4584a', label: '已作废', tip: '设备已踢下线、邀请码失效' },
  // Token 用量
  in_use: { color: '#7fbf98', label: '在用', tip: '当前配置正在用的模型' },
  history: { color: '#bdb9c6', label: '历史', tip: '以前用过，现在已不用' },
  disabled: { color: '#d4d1da', label: '未启用', tip: '配置里的备用模型，未启用' },
  // 服务器服务
  svc_active: { color: '#7fbf98', label: '运行中', tip: 'systemd 服务正常运行' },
  svc_inactive: { color: '#e08b78', label: '已停止', tip: '服务没有在运行' },
  svc_failed: { color: '#b4584a', label: '故障', tip: '服务异常退出' },
  svc_unknown: { color: '#d4d1da', label: '未知', tip: '读不到服务状态' },
  // 审计
  ok: { color: '#7fbf98', label: '成功', tip: '操作成功 / 访问已放行' },
  fail: { color: '#e08b78', label: '失败 / 被拒', tip: '登录失败、拒绝访问、限流、拦截或封禁' },
  info: { color: '#d4d1da', label: '信息', tip: '退出、解封等纯信息记录' },
}
export const TASK_STATUS = Object.fromEntries(['running', 'waiting_user', 'preview_ready', 'awaiting_payment', 'delivering', 'done', 'failed'].map((k) => [k, STATUSES[k].label]))
export const status = (key) => STATUSES[key] || { color: '#d4d1da', label: key || '未知', tip: '' }
/** 图例：按 STATUSES 的顺序列出 keys 里出现过的状态 */
export const legendKeys = (keys) => { const set = new Set(keys); return Object.keys(STATUSES).filter((k) => set.has(k)) }
export const serviceKey = (state) => `svc_${['active', 'inactive', 'failed'].includes(state) ? state : 'unknown'}`
export const inviteKey = (h) => (h.devices.length ? 'active' : h.unused ? 'unused' : 'revoked')
