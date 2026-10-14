// 假数据：在前端模拟后端的状态变化，字段和《小囍接口约定》一致。
// 只在 VITE_USE_MOCK=true 时使用。
const STEP_TEXT = {
  intake: '小囍正在看你们的照片',
  styling: '妆造师在设计造型',
  framing: '摄影师在设计镜头',
  composing: '小囍在把方案写成拍摄指令',
  generating: '正在拍摄 4 张候选',
  checking: '修图师在逐张质检',
  retouching: '修图师在调整不满意的地方',
  packaging: '正在制作请柬和婚礼物料',
}

const option = (value, label) => ({ value, label, image: null })

// 小囍、妆造师、摄影师依次和用户对话，每人一轮
const ROUNDS = [
  {
    step: 'intake',
    speech: '我是小囍，你们这次拍摄的项目经理。先确认两件事，后面妆造师和摄影师还会跟你们细聊。',
    questions: [
      { question_id: 'q_style', type: 'single_choice', title: '想要哪种风格？', options: [option('korean_studio', '韩式影棚'), option('keep_original', '保留原图场景')], recommended: 'korean_studio', allow_skip: true },
      { question_id: 'q_height', type: 'text', title: '两人身高大概多少？', placeholder: '例如 175 / 162', allow_skip: true },
    ],
  },
  {
    step: 'styling',
    speech: '我是妆造师，按你们选的风格挑了几款妆容和婚纱，选一个最喜欢的吧。',
    questions: [
      { question_id: 'q_makeup', type: 'single_choice', title: '想要什么样的妆容？', options: [option('natural', '自然淡妆'), option('korean', '清透韩妆'), option('retro', '复古红唇')], recommended: 'natural', allow_skip: true },
      { question_id: 'q_outfit', type: 'single_choice', title: '婚纱想要哪种款式？', options: [option('satin', '缎面抹胸婚纱'), option('lace', '蕾丝长袖婚纱'), option('mermaid', '鱼尾拖尾婚纱')], recommended: 'satin', allow_skip: true },
    ],
  },
  {
    step: 'framing',
    speech: '我是摄影师，想再了解一下你们平时怎么相处，喜欢什么样的光线。',
    questions: [
      { question_id: 'q_interaction', type: 'single_choice', title: '你们平时相处更像哪种状态？', options: [option('gaze', '牵手对视'), option('hug', '相拥微笑'), option('side', '并肩看镜头')], recommended: 'gaze', allow_skip: true },
      { question_id: 'q_light', type: 'single_choice', title: '喜欢什么样的光线？', options: [option('soft', '柔和自然光'), option('warm', '温暖的室内灯光'), option('backlight', '傍晚逆光')], recommended: 'soft', allow_skip: true },
    ],
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

// 让第 n 位上场提问
function ask(task, n) {
  const round = ROUNDS[n]
  advance(task, [round.step], 'waiting_user', () => {
    task.round = n
    task.questions = round.questions
    task.step_text = round.speech
  })
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
  tasks[taskId] = {
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
    round: 0,
  }
  ask(tasks[taskId], 0)
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
  if (task.round + 1 < ROUNDS.length) {
    ask(task, task.round + 1)
  } else {
    advance(task, ['composing', 'generating', 'checking'], 'preview_ready', () => {
      task.previews = makePreviews(task)
    })
  }
  return { status: 'running' }
}

export async function review(taskId, payload) {
  const task = need(taskId, 'preview_ready')
  if (payload.action === 'confirm' || payload.action === 'sample_only') {
    task.status = 'awaiting_payment'
    return { status: 'awaiting_payment' }
  }
  if (task.redoCount >= 2) throw apiError('REDO_LIMIT', '已经重做 2 次了，请联系人工帮你调整')
  task.redoCount += 1
  advance(task, ['retouching', 'composing', 'generating', 'checking'], 'preview_ready', () => {
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
