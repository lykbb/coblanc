// 假数据：在前端模拟后端的状态变化，字段和《小囍接口约定》、app/api.py 一致。
// 只在 VITE_USE_MOCK=true 时使用。
const STEP_TEXT = {
  intake: '小囍正在看你们的照片',
  styling: '妆造师在设计造型',
  framing: '摄影师在设计镜头',
  composing: '小囍在把方案写成拍摄指令',
  generating: '正在生成样片 / 套图',
  checking: '修图师在逐张质检',
  retouching: '修图师在调整不满意的地方',
  packaging: '正在制作请柬和婚礼物料',
}
const MAX_REDO = 2

const option = (value, label) => ({ value, label, image: null })

// 小囍（两轮：先确认授权和资料，再要求补传一张照片）、妆造师、摄影师依次提问
const ROUNDS = [
  {
    step: 'intake',
    speech: '我是小囍，你们这次拍摄的项目经理。先确认授权和几项资料。',
    questions: [
      { question_id: 'q_consent', type: 'single_choice', title: '是否同意照片仅用于本次生成？', options: [option('standard', '同意：仅用于本次生成，不用于训练，预览带水印，交付后删除原图'), option('keep_photos', '同意，但交付后保留原图')], recommended: 'standard', placeholder: null, allow_skip: false },
      { question_id: 'q_height', type: 'text', title: '两人身高大概多少？', options: [], recommended: null, placeholder: '例如 175 / 162', allow_skip: true },
      { question_id: 'q_materials', type: 'multi_choice', title: '需要哪些婚礼物料？', options: [option('invitation', '请柬主视觉'), option('welcome_poster', '迎宾海报'), option('led_screen', '婚礼大屏')], recommended: ['invitation', 'welcome_poster', 'led_screen'], placeholder: null, allow_skip: true },
      { question_id: 'q_invitation', type: 'text', title: '请柬上写什么：新人名字、婚礼日期、地点？', options: [], recommended: null, placeholder: '例如 张三 & 李四，2026-12-20，杭州', allow_skip: true },
    ],
  },
  {
    step: 'intake',
    speech: '新娘第 1 张照片有点模糊，麻烦补传一张清晰的正面照。',
    questions: [
      { question_id: 'q_bride_photos', type: 'upload', title: '新娘第1张：脸部模糊，请补传清晰的正面照', options: [], recommended: null, placeholder: null, allow_skip: false },
    ],
  },
  {
    step: 'styling',
    speech: '我是妆造师，按你们选的风格挑了几款妆容和婚纱，选一个最喜欢的吧。',
    questions: [
      { question_id: 'q_makeup', type: 'single_choice', title: '想要什么样的妆容？', options: [option('natural', '自然淡妆'), option('korean', '清透韩妆'), option('retro', '复古红唇')], recommended: 'natural', placeholder: null, allow_skip: true },
      { question_id: 'q_outfit', type: 'single_choice', title: '婚纱想要哪种款式？', options: [option('satin', '缎面抹胸婚纱'), option('lace', '蕾丝长袖婚纱'), option('mermaid', '鱼尾拖尾婚纱')], recommended: 'satin', placeholder: null, allow_skip: true },
    ],
  },
  {
    step: 'framing',
    speech: '我是摄影师，想再了解一下你们平时怎么相处，喜欢什么样的光线。',
    questions: [
      { question_id: 'q_interaction', type: 'single_choice', title: '你们平时相处更像哪种状态？', options: [option('gaze', '牵手对视'), option('hug', '相拥微笑'), option('side', '并肩看镜头')], recommended: 'gaze', placeholder: null, allow_skip: true },
      { question_id: 'q_light', type: 'single_choice', title: '喜欢什么样的光线？', options: [option('soft', '柔和自然光'), option('warm', '温暖的室内灯光'), option('backlight', '傍晚逆光')], recommended: 'soft', placeholder: null, allow_skip: true },
    ],
  },
]

const tasks = {}
const uploads = {}
let uploadCount = 0

function apiError(code, message, httpStatus = 400) {
  const error = new Error(message)
  error.code = code
  error.httpStatus = httpStatus
  error.body = { error: { code, message } }
  return error
}

function need(taskId, status) {
  const task = tasks[taskId]
  if (!task) throw apiError('TASK_NOT_FOUND', '找不到这个任务，可能已经过期了', 404)
  if (status && task.status !== status) throw apiError('WRONG_STATUS', '现在还不能做这一步，请刷新一下', 409)
  return task
}

// 按顺序走过几个步骤，每步约 1 秒，最后停在 finalStatus
function advance(task, steps, finalStatus, onDone) {
  task.status = steps[0] === 'packaging' ? 'delivering' : 'running'
  let index = 0
  const tick = () => {
    if (index < steps.length) {
      task.step = steps[index]
      task.step_text = STEP_TEXT[steps[index]]
      index += 1
      setTimeout(tick, 1000)
    } else {
      onDone?.()
      task.status = finalStatus
    }
  }
  tick()
}

function ask(task, n) {
  const round = ROUNDS[n]
  advance(task, [round.step], 'waiting_user', () => {
    task.round = n
    task.questions = round.questions
    task.step_text = round.speech
  })
}

// 生成一轮：样片 1 张，套图 9 张；generation 字段和后端一致
function generateRound(task, steps) {
  const count = task.stage === 'set' ? 9 : 1
  advance(task, steps, 'preview_ready', () => {
    const urls = [...task.groom, ...task.bride]
    task.previews = Array.from({ length: count }, (_, i) => ({
      image_id: `img_${task.nextImage + i}`,
      url: urls[i % urls.length],
      is_best: i === 0,
    }))
    task.nextImage += count
    task.generation = { engine: 'fake', workflow: 'fake', seconds: 1.0, total_images: task.nextImage - 1, stage: task.stage }
  })
}

export async function uploadImage(file) {
  uploadCount += 1
  const fileId = `f_mock_${uploadCount}`
  uploads[fileId] = URL.createObjectURL(file)
  return { file_id: fileId, url: uploads[fileId] }
}

export async function createTask(body) {
  const groomIds = body.groom_photo_file_ids || []
  const brideIds = body.bride_photo_file_ids || []
  const grouped = groomIds.length || brideIds.length
  if (grouped && (!groomIds.length || !brideIds.length)) throw apiError('PHOTO_INVALID', '请分别上传新郎和新娘各 1～10 张正面生活照')
  if (grouped && (groomIds.length > 10 || brideIds.length > 10)) throw apiError('PHOTO_INVALID', '新郎和新娘的照片数量都必须是 1～10 张')
  const legacy = body.photo_file_ids || []
  if (!grouped && (legacy.length < 2 || legacy.length > 10)) throw apiError('PHOTO_INVALID', '请上传 2～10 张照片，新郎新娘都要有，合照单人照都行')
  const all = grouped ? [...groomIds, ...brideIds] : legacy
  if (all.some((id) => !uploads[id])) throw apiError('FILE_INVALID', '找不到上传的照片，请重新上传')
  const taskId = `t_mock_${Date.now()}`
  tasks[taskId] = {
    status: 'running',
    step: null,
    step_text: null,
    questions: [],
    previews: [],
    deliverables: null,
    message: null,
    consent: null,
    generation: null,
    groom: (grouped ? groomIds : legacy).map((id) => uploads[id]),
    bride: (grouped ? brideIds : []).map((id) => uploads[id]),
    legacy: grouped ? 0 : legacy.length,
    stage: 'sample',
    nextImage: 1,
    redoCount: 0,
    round: 0,
  }
  ask(tasks[taskId], 0)
  return { task_id: taskId, status: 'running' }
}

export async function getTask(taskId) {
  const task = need(taskId)
  const { status } = task
  return {
    task_id: taskId,
    status,
    step: task.step,
    step_text: task.step_text,
    questions: status === 'waiting_user' ? task.questions : [],
    consent: task.consent,
    generation: task.generation,
    photo_counts: { groom: task.legacy ? 0 : task.groom.length, bride: task.bride.length, legacy: task.legacy },
    previews: status === 'preview_ready' ? task.previews : [],
    deliverables: status === 'done' ? task.deliverables : null,
    message: status === 'done' ? task.message : null,
    error: null,
    plan: {
      photos: { groom: task.legacy ? [] : task.groom, bride: task.bride, all: [...task.groom, ...task.bride] },
      brief: task.plan?.brief || null,
      look: task.plan?.look || null,
      shot: task.plan?.shot || null,
      shots: task.plan?.shots || [],
    },
  }
}

// 按每轮回答拼出 plan（和后端 GET 返回的 plan 结构一致）
const SHOT_FRAMINGS = [['全身', '两人并肩看镜头'], ['半身', '侧身额头相抵'], ['特写', '新娘回眸微笑'], ['全身', '牵手走向镜头'], ['半身', '新郎从背后环抱'], ['远景', '背影牵手'], ['半身', '两人对视微笑'], ['特写', '十指相扣'], ['全身', '新郎抱起新娘']]
function labelOf(question, answer) {
  const value = answer && !answer.skipped ? answer.value : question.recommended
  return question.options.find((o) => o.value === value)?.label || ''
}
function updatePlan(task, step, answers) {
  const byId = Object.fromEntries(answers.map((a) => [a.question_id, a]))
  const find = (id) => task.questions.find((q) => q.question_id === id)
  task.plan = task.plan || {}
  if (step === 'intake' && find('q_height')) {
    const nums = String(byId.q_height?.value || '').match(/\d{3}/g) || []
    const materials = byId.q_materials && !byId.q_materials.skipped ? byId.q_materials.value : ['invitation', 'welcome_poster', 'led_screen']
    task.plan.brief = { heights_cm: nums.length >= 2 ? [Number(nums[0]), Number(nums[1])] : [], materials, invitation: {}, keep_features: [], beautify: 'none' }
  }
  if (step === 'styling') {
    task.plan.look = {
      text: `新娘：${labelOf(find('q_makeup'), byId.q_makeup)}，低盘发，${labelOf(find('q_outfit'), byId.q_outfit)}，珍珠耳饰；新郎：利落短发，黑色修身西装，白衬衫，自然控油修饰`,
      style: 'korean_studio',
      references: [],
    }
  }
  if (step === 'framing') {
    task.plan.shot = { text: `简洁影棚，${labelOf(find('q_light'), byId.q_light)}，两人${labelOf(find('q_interaction'), byId.q_interaction)}`, pose: 'keep_original', references: [] }
    task.plan.shots = SHOT_FRAMINGS.map(([framing, text], slot) => ({ slot, pose: 'keep_original', framing, scene: '简洁影棚', text: `${framing}构图，${text}` }))
  }
}

export async function submitAnswers(taskId, answers) {
  const task = need(taskId, 'waiting_user')
  updatePlan(task, ROUNDS[task.round].step, answers)
  const consent = answers.find((a) => a.question_id === 'q_consent')
  if (consent) {
    task.consent = {
      authorization_scope: 'generation_only', retention_days: 7, allow_training: false,
      watermark: true, delete_original: consent.value !== 'keep_photos', confirmed: true,
    }
  }
  for (const answer of answers) {
    const question = task.questions.find((q) => q.question_id === answer.question_id)
    if (question?.type === 'upload' && !answer.skipped) {
      const ids = Array.isArray(answer.value) ? answer.value : [answer.value]
      if (ids.some((id) => !uploads[id])) throw apiError('FILE_INVALID', '找不到上传的照片，请重新上传')
      task.bride = [...ids.map((id) => uploads[id]), ...task.bride.slice(1)]
    }
  }
  if (task.round + 1 < ROUNDS.length) ask(task, task.round + 1)
  else generateRound(task, ['composing', 'generating', 'checking'])
  return { status: 'running' }
}

export async function review(taskId, payload) {
  const task = need(taskId, 'preview_ready')
  if (!task.previews.some((p) => p.image_id === payload.image_id)) throw apiError('WRONG_STATUS', '找不到这张预览图，请刷新一下', 409)
  if (payload.action === 'sample_only' && task.stage !== 'sample') throw apiError('WRONG_STATUS', '只有样片阶段可以选择只要这一张', 409)
  if (payload.action === 'redo') {
    if (task.redoCount >= MAX_REDO) throw apiError('REDO_LIMIT', `已经重做 ${MAX_REDO} 次了，请联系人工帮你调整`, 409)
    task.redoCount += 1
    generateRound(task, ['retouching', 'composing', 'generating', 'checking'])
    return { status: 'running' }
  }
  task.best = payload.image_id
  if (payload.action === 'confirm' && task.stage === 'sample') {
    task.stage = 'set'
    generateRound(task, ['generating', 'checking'])
    return { status: 'running' }
  }
  task.status = 'awaiting_payment'
  return { status: 'awaiting_payment' }
}

export async function pay(taskId) {
  const task = need(taskId, 'awaiting_payment')
  advance(task, ['packaging'], 'done', () => {
    const best = task.previews.find((p) => p.image_id === task.best) || task.previews[0]
    const url = best.url
    task.deliverables = { photo: url, invitation: url, welcome_poster: url, led_screen: url, moments: url }
    if (task.stage === 'set') task.deliverables.photos = [url, ...task.previews.filter((p) => p !== best).map((p) => p.url)]
    task.message = '照片里你们笑得很自然，愿你们的婚礼也像这组照片一样，温柔又闪闪发光。'
  })
  return { status: 'delivering' }
}

export async function retry(taskId) {
  const task = need(taskId, 'failed')
  task.status = 'running'
  task.error = null
  return { status: 'running' }
}
