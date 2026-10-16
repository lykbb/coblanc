// 创作流程的状态：当前任务、轮询、用户操作。所有页面共用这一份。
// 只通过 api.js 的 6 个接口和后端通信；浏览器里只记当前任务编号和"我的项目"列表。
import { computed, reactive, watch } from 'vue'
import { api } from './api.js'
import { speakerOf } from './agents.js'

// 有独立地址的页面（可直接打开、可分享）；其余页面都在 /
const VIEW_PATHS = { refs: '/gallery' }
function viewFromPath() {
  return Object.keys(VIEW_PATHS).find((view) => VIEW_PATHS[view] === location.pathname.replace(/\/$/, '')) || 'overview'
}

const POLL_MS = 1500
const STALL_MS = 3 * 60 * 1000 // 超过这么久没进展：提示一句，改成慢速轮询（不停止）
const SLOW_POLL_MS = 10000
const MAX_ERROR_POLL_MS = 30000 // 网络/服务出错时逐次加倍等待，最多 30 秒
const PAUSED = ['waiting_user', 'preview_ready', 'awaiting_payment', 'done', 'failed']
const CURRENT_KEY = 'coblanc.currentTask'
const PROJECTS_KEY = 'coblanc.projects'
const MAX_PHOTOS = 10
const MAX_BYTES = 10 * 1024 * 1024
export const MAX_REDO = 2

function readJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : fallback
  } catch {
    return fallback
  }
}

function writeJson(key, value) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // 无痕模式等情况下存不了，不影响使用
  }
}

export const state = reactive({
  view: viewFromPath(),
  taskId: null,
  task: null,
  busy: false,
  error: null, // { code, message }
  notice: null, // 一句轻提示
  dialog: null, // 'questions' | 'redo' | 'pay'
  redoPreset: null, // { reason, note }
  lightbox: null, // 图片地址
  draft: { photos: [], description: '' }, // 一个上传框：合照、单人照混传
  uploading: 0,
  log: [], // { at, who, text, mine }
  sampleUrl: null,
  picked: null, // 预览里选中的那张
  redoUsed: 0,
  lastPhase: 'start',
  projects: readJson(PROJECTS_KEY, []),
})

// ---------- 流程阶段 ----------

export const STAGES = [
  { key: 'photos', title: '双方照片' },
  { key: 'style', title: '风格方案' },
  { key: 'bride', title: '女生造型' },
  { key: 'groom', title: '男生造型' },
  { key: 'scene', title: '摄影场景' },
  { key: 'sample', title: '样片确认' },
  { key: 'set', title: '九张成片' },
]

function phaseOf(task, hasTask) {
  if (!hasTask) return 'start'
  if (!task) return 'loading'
  switch (task.status) {
    case 'failed': return 'failed'
    case 'done': return 'done'
    case 'delivering': return 'delivering'
    case 'awaiting_payment': return 'pay'
    case 'preview_ready': return task.generation?.stage === 'set' ? 'set_review' : 'sample_review'
    case 'waiting_user': return `${task.step || 'intake'}_ask`
    default: break
  }
  if (['generating', 'checking', 'retouching'].includes(task.step)) {
    return task.generation?.stage === 'set' ? 'set_gen' : 'sample_gen'
  }
  return task.step || 'intake'
}

export const phase = computed(() => phaseOf(state.task, Boolean(state.taskId)))

const ACTIVE = {
  start: 0, loading: 0, intake: 0, intake_ask: 0,
  styling: 1, styling_ask: 1,
  framing: 4, framing_ask: 4,
  composing: 5, sample_gen: 5, sample_review: 5,
  set_gen: 6, set_review: 6,
  pay: 7, delivering: 7, done: 7,
}

// 当前进行到第几张卡片（0～6），7 表示全部完成
export const activeStage = computed(() => {
  const current = phase.value === 'failed' ? state.lastPhase : phase.value
  return ACTIVE[current] ?? 0
})

export function stageStatus(index) {
  const active = activeStage.value
  if (active >= 7) return 'done'
  if (active === 1 && index >= 1 && index <= 3) return 'active' // 风格和两人造型由妆造师一起定
  if (index < active) return 'done'
  if (index === active) return phase.value === 'failed' ? 'failed' : 'active'
  return 'todo'
}

export const progress = computed(() => {
  if (phase.value === 'start') return 0
  if (phase.value === 'done') return 100
  if (phase.value === 'delivering') return 96
  if (phase.value === 'pay') return 92
  return Math.round(((activeStage.value + 0.5) / STAGES.length) * 100)
})

// ---------- 记录与提示 ----------

function now() {
  return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

export function addLog(who, text, mine = false) {
  state.log.push({ at: now(), who, text, mine })
  if (state.log.length > 40) state.log.splice(0, state.log.length - 40)
}

const LOST_TEXT = '这个任务找不到了（可能已过期或服务刚更新），照片不会丢在别处，点「重新开始」再来一次就好'

function showError(error) {
  if (error.code === 'TASK_NOT_FOUND') {
    if (state.taskId) removeProject(state.taskId)
    state.error = { code: error.code, lost: true, message: LOST_TEXT }
    return
  }
  state.error = { code: error.code || null, message: error.message || '出了点问题，请稍后再试' }
}

export function clearError() {
  state.error = null
}

// ---------- 我的项目（只存在这台电脑的浏览器里） ----------

function saveProjects() {
  writeJson(PROJECTS_KEY, state.projects)
}

function touchProject(taskId, patch) {
  const found = state.projects.find((p) => p.task_id === taskId)
  if (found) Object.assign(found, patch)
  else state.projects.unshift({ task_id: taskId, created_at: new Date().toISOString(), ...patch })
  saveProjects()
}

export function removeProject(taskId) {
  state.projects = state.projects.filter((p) => p.task_id !== taskId)
  saveProjects()
  if (state.taskId === taskId) restart()
}

// ---------- 轮询 ----------

let timer = null
let lastKey = ''
let lastChange = 0
let lastQuestionsKey = ''
let errorStreak = 0

function stopPolling() {
  clearTimeout(timer)
  timer = null
}

function onTask(data) {
  const prev = state.task
  state.task = data
  const current = phaseOf(data, true)
  if (current !== 'failed') state.lastPhase = current

  const key = `${data.status}|${data.step}|${data.step_text}`
  if (key !== lastKey) {
    lastKey = key
    lastChange = Date.now()
    if (data.step_text && data.step_text !== prev?.step_text) addLog(speakerOf(data.step).name, data.step_text)
  }
  // 补传照片题不弹窗：在右下角对话框里补传或留言
  if (data.status === 'waiting_user' && !data.questions.some((q) => q.type === 'upload')) {
    const qKey = data.step + ':' + data.questions.map((q) => q.question_id).join(',')
    if (qKey !== lastQuestionsKey) {
      lastQuestionsKey = qKey
      state.dialog = 'questions'
    }
  }
  if (data.status === 'preview_ready' && data.previews.length) {
    const best = data.previews.find((p) => p.is_best) || data.previews[0]
    if (!data.previews.some((p) => p.image_id === state.picked)) state.picked = best.image_id
    if (data.generation?.stage !== 'set') state.sampleUrl = best.url
  }
  if (data.status === 'awaiting_payment' && prev?.status !== 'awaiting_payment') state.dialog = 'pay'
  if (data.status === 'done' && prev?.status !== 'done') addLog('Amie', data.message || '你们的作品完成啦')
  if (data.status === 'failed' && prev?.status !== 'failed') addLog('Amie', failureText(data.error))

  const cover = data.deliverables?.photo || state.sampleUrl || data.plan?.photos?.all?.[0] || null
  touchProject(data.task_id, { status: data.status, cover })
}

async function poll() {
  if (!state.taskId) return
  const taskId = state.taskId
  let delay = POLL_MS
  try {
    const data = await api.getTask(taskId)
    if (taskId !== state.taskId) return
    if (errorStreak) state.error = null
    errorStreak = 0
    onTask(data)
    if (PAUSED.includes(data.status)) return stopPolling()
    if (Date.now() - lastChange > STALL_MS) {
      if (!state.notice) state.notice = '比平时慢了一些，可以稍后再回来看看'
      delay = SLOW_POLL_MS
    }
  } catch (error) {
    if (taskId !== state.taskId) return
    if (error.code === 'TASK_NOT_FOUND') {
      removeProject(taskId)
      state.error = { code: error.code, lost: true, message: LOST_TEXT }
      return
    }
    errorStreak += 1
    if (errorStreak === 1) showError(error)
    delay = Math.min(POLL_MS * 2 ** errorStreak, MAX_ERROR_POLL_MS)
  }
  timer = setTimeout(poll, delay)
}

function startPolling() {
  stopPolling()
  errorStreak = 0
  lastChange = Date.now()
  poll()
}

async function act(action) {
  if (state.busy) return false
  state.busy = true
  state.error = null
  try {
    await action()
    startPolling()
    return true
  } catch (error) {
    showError(error)
    if (error.code === 'WRONG_STATUS') startPolling()
    return false
  } finally {
    state.busy = false
  }
}

// ---------- 用户操作 ----------

export async function addPhotos(files) {
  const list = state.draft.photos
  for (const file of files) {
    if (list.length >= MAX_PHOTOS) {
      state.notice = `最多 ${MAX_PHOTOS} 张，挑最清晰的几张就好`
      break
    }
    if (!['image/jpeg', 'image/png'].includes(file.type)) {
      state.notice = '只支持 jpg 和 png 图片'
      continue
    }
    if (file.size > MAX_BYTES) {
      state.notice = '单张图片不能超过 10 MB'
      continue
    }
    list.push({ key: `${Date.now()}-${Math.random()}`, name: file.name, preview: URL.createObjectURL(file), file_id: null, failed: false })
    const item = list[list.length - 1]
    state.uploading += 1
    try {
      const res = await api.uploadImage(file)
      item.file_id = res.file_id
    } catch (error) {
      item.failed = true
      showError(error)
    } finally {
      state.uploading -= 1
    }
  }
}

export function removePhoto(index) {
  const [item] = state.draft.photos.splice(index, 1)
  if (item?.preview) URL.revokeObjectURL(item.preview)
}

export async function startTask() {
  const photos = state.draft.photos.filter((p) => p.file_id)
  if (state.uploading) {
    state.notice = '照片还在上传，请稍等一下'
    return
  }
  if (!photos.length) {
    state.notice = '先上传你们的照片，合照、单人照都可以'
    return
  }
  await act(async () => {
    const created = await api.createTask({
      photo_file_ids: photos.map((p) => p.file_id),
      description: state.draft.description.trim(),
    })
    state.taskId = created.task_id
    state.task = null
    state.log = []
    state.sampleUrl = null
    state.redoUsed = 0
    lastKey = ''
    lastQuestionsKey = ''
    writeJson(CURRENT_KEY, created.task_id)
    touchProject(created.task_id, { status: created.status, cover: null })
    addLog('你', `上传了 ${photos.length} 张照片${state.draft.description.trim() ? '，并说了你们的想法' : ''}`, true)
  })
}

export function failureText(error) {
  if (!error) return '出了点问题，请稍后再试'
  return error.title ? `${error.title}：${error.message}` : error.message
}

// 补传照片：用右下角对话框里新加的照片 + 留言回答 upload 题，然后从小囍那一步继续
export async function submitPhotoFix(text) {
  const question = state.task?.questions?.find((q) => q.type === 'upload')
  if (!question) return false
  if (state.uploading) {
    state.notice = '照片还在上传，请稍等一下'
    return false
  }
  const ids = state.draft.photos.filter((p) => p.file_id).map((p) => p.file_id)
  if (!ids.length && !text) {
    state.notice = '先补传照片，或者告诉 Amie 你的想法'
    return false
  }
  const answers = [{ question_id: question.question_id, value: ids }]
  if (text) answers.push({ question_id: 'q_photos_note', value: text })
  const ok = await act(() => api.submitAnswers(state.taskId, answers))
  if (ok) {
    addLog('你', `${ids.length ? `补传了 ${ids.length} 张照片` : ''}${ids.length && text ? '，' : ''}${text ? `说：${text}` : ''}`, true)
    state.draft.photos = []
  }
  return ok
}

export async function retryTask() {
  await act(() => api.retry(state.taskId))
}

export async function submitAnswers(answers) {
  const ok = await act(() => api.submitAnswers(state.taskId, answers))
  if (ok) {
    state.dialog = null
    const answered = answers.filter((a) => !a.skipped).length
    addLog('你', answered ? `回答了 ${answered} 个问题` : '都用了推荐选项', true)
  }
  return ok
}

export async function review(action, imageId, extra = {}) {
  const ok = await act(() => api.review(state.taskId, { action, image_id: imageId, ...extra }))
  if (!ok) return false
  state.dialog = null
  if (action === 'redo') {
    state.redoUsed += 1
    addLog('你', `请修图师重做${extra.note ? `：${extra.note}` : ''}`, true)
  } else if (action === 'sample_only') {
    addLog('你', '只要这一张样片', true)
  } else {
    addLog('你', phase.value === 'set_review' ? '确认了这组套图' : '样片方向对了，开始拍 9 张', true)
  }
  return true
}

export function openRedo(reason = 'face', note = '') {
  state.redoPreset = { reason, note }
  state.dialog = 'redo'
}

export async function pay() {
  const ok = await act(() => api.pay(state.taskId, 'mock'))
  if (ok) {
    state.dialog = null
    addLog('你', '完成了模拟支付', true)
  }
}

export function restart() {
  stopPolling()
  state.draft.photos.forEach((p) => p.preview && URL.revokeObjectURL(p.preview))
  state.taskId = null
  state.task = null
  state.dialog = null
  state.error = null
  state.log = []
  state.sampleUrl = null
  state.redoUsed = 0
  state.lastPhase = 'start'
  state.draft = { photos: [], description: '' }
  lastKey = ''
  lastQuestionsKey = ''
  writeJson(CURRENT_KEY, null)
  state.view = 'studio'
}

export function openProject(taskId) {
  stopPolling()
  state.taskId = taskId
  state.task = null
  state.log = []
  state.sampleUrl = null
  state.redoUsed = 0
  state.error = null
  lastKey = ''
  lastQuestionsKey = ''
  writeJson(CURRENT_KEY, taskId)
  state.view = 'studio'
  startPolling()
}

export function resumeLastTask() {
  const saved = readJson(CURRENT_KEY, null)
  if (!saved) return
  const deepLinked = state.view !== 'overview' // 直接打开 /gallery 等地址时留在该页，任务在后台恢复
  const view = state.view
  openProject(saved)
  if (deepLinked) state.view = view
}

export function refresh() {
  if (state.taskId) startPolling()
}

// 页面和地址栏同步：切到参考图墙地址变成 /gallery，浏览器前进后退也能切回来
watch(() => state.view, (view) => {
  const path = VIEW_PATHS[view] || '/'
  if (location.pathname !== path) history.pushState(null, '', path + location.search)
})
window.addEventListener('popstate', () => { state.view = viewFromPath() })
