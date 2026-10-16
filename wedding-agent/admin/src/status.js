// 列表左侧细状态条（审计、任务、生成记录、邀请码、Token 用量、服务器共用）：class="st-bar st-<tone>"，样式见 admin.css。
export const TASK_STATUS = { running: '进行中', waiting_user: '等用户回答', preview_ready: '待确认', awaiting_payment: '待支付', delivering: '交付中', done: '完成', failed: '失败' }
const TASK_TONE = { done: 'ok', failed: 'fail', waiting_user: 'wait', preview_ready: 'wait', awaiting_payment: 'wait', running: 'run', delivering: 'run' }
export const taskTone = (status) => TASK_TONE[status] || 'info'
export const bar = (tone) => `st-bar st-${tone}`
export const TASK_LEGEND = [['ok', '完成'], ['fail', '失败'], ['wait', '等确认 / 等回答'], ['run', '进行中']]
