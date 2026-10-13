// 假数据：在前端模拟后端的状态变化，字段和《小囍接口约定》一致。
// 只在 VITE_USE_MOCK=true 时使用。
const STEP_TEXT = {
  intake: '小囍正在看你们的照片',
  styling: '妆造师在设计造型',
  framing: '摄影师在安排构图和姿势',
  generating: '正在拍摄 4 张候选',
  checking: '修图师在逐张质检',
  retouching: '修图师在调整不满意的地方',
  packaging: '正在制作请柬和婚礼物料',
}

const QUESTIONS = [
  {
    question_id: 'q_style',
    type: 'single_choice',
    title: '想要哪种风格？',
    options: [
      { value: 'korean_studio', label: '韩式影棚', image: null },
      { value: 'keep_original', label: '保留原图场景', image: null },
    ],
    recommended: 'korean_studio',
    allow_skip: true,
  },
  {
    question_id: 'q_height',
    type: 'text',
    title: '两人身高大概多少？',
    placeholder: '例如 175 / 162',
    allow_skip: true,
  },
]

const tasks = {}
let lastUploadUrl = ''

function apiError(code, message) {
  const error = new Error(message)
  error.code = code
  return error
}

function need(taskId, status) {
  const task = tasks[taskId]
  if (!task) throw apiError('TASK_NOT_FOUND', '找不到这个任务，可能已经过期了')
  if (task.status !== status) throw apiError('WRONG_STATUS', '现在还不能做这一步，请刷新一下')
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

function makePreviews(task) {
  const start = task.nextImage
  task.nextImage += 4
  return [0, 1, 2, 3].map((i) => ({ image_id: `img_${start + i}`, url: task.photo, is_best: i === 0 }))
}

export async function uploadImage(file) {
  lastUploadUrl = URL.createObjectURL(file)
  return { file_id: 'f_mock', url: lastUploadUrl }
}

export async function createTask() {
  const taskId = `t_mock_${Date.now()}`
  const task = (tasks[taskId] = {
    status: 'running',
    step: null,
    step_text: null,
    questions: [],
    previews: [],
    deliverables: null,
    message: null,
    photo: lastUploadUrl,
    nextImage: 1,
    redoCount: 0,
  })
  advance(task, ['intake'], 'waiting_user', () => {
    task.questions = QUESTIONS
  })
  return { task_id: taskId, status: 'running' }
}

export async function getTask(taskId) {
  const task = tasks[taskId]
  if (!task) throw apiError('TASK_NOT_FOUND', '找不到这个任务，可能已经过期了')
  const { status } = task
  return {
    task_id: taskId,
    status,
    step: task.step,
    step_text: task.step_text,
    questions: status === 'waiting_user' ? task.questions : [],
    previews: status === 'preview_ready' ? task.previews : [],
    deliverables: status === 'done' ? task.deliverables : null,
    message: status === 'done' ? task.message : null,
    error: null,
  }
}

export async function submitAnswers(taskId) {
  const task = need(taskId, 'waiting_user')
  advance(task, ['intake', 'styling', 'framing', 'generating', 'checking'], 'preview_ready', () => {
    task.previews = makePreviews(task)
  })
  return { status: 'running' }
}

export async function review(taskId, payload) {
  const task = need(taskId, 'preview_ready')
  if (payload.action === 'confirm') {
    task.status = 'awaiting_payment'
    return { status: 'awaiting_payment' }
  }
  if (task.redoCount >= 2) throw apiError('REDO_LIMIT', '已经重做 2 次了，请联系人工帮你调整')
  task.redoCount += 1
  advance(task, ['retouching', 'generating', 'checking'], 'preview_ready', () => {
    task.previews = makePreviews(task)
  })
  return { status: 'running' }
}

export async function pay(taskId) {
  const task = need(taskId, 'awaiting_payment')
  advance(task, ['packaging'], 'done', () => {
    const url = task.photo
    task.deliverables = { photo: url, invitation: url, welcome_poster: url, led_screen: url, moments: url }
    task.message = '照片里你们笑得很自然，愿你们的婚礼也像这组照片一样，温柔又闪闪发光。'
  })
  return { status: 'delivering' }
}
