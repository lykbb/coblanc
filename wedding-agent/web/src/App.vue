<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { showToast } from 'vant'
import { api, usingMock } from './api.js'
import UploadStep from './components/UploadStep.vue'
import ProgressStep from './components/ProgressStep.vue'
import QuestionStep from './components/QuestionStep.vue'
import PreviewStep from './components/PreviewStep.vue'
import PayStep from './components/PayStep.vue'
import RevealStep from './components/RevealStep.vue'
import DebugPanel from './components/DebugPanel.vue'

const POLL_MS = 1500
const STALL_MS = 3 * 60 * 1000
// 到这些状态就停止轮询，等用户操作
const PAUSED = ['waiting_user', 'preview_ready', 'awaiting_payment', 'done', 'failed']
const STEPS = [
  { key: 'upload', label: '上传照片' },
  { key: 'waiting_user', label: '确认需求' },
  { key: 'running', label: '制作中' },
  { key: 'preview_ready', label: '挑选预览' },
  { key: 'awaiting_payment', label: '支付' },
  { key: 'done', label: '交付' },
]

const taskId = ref(null)
const task = ref(null)
const busy = ref(false)
const status = computed(() => task.value?.status)
const currentStep = computed(() => {
  if (!task.value) return 'upload'
  if (status.value === 'delivering') return 'done'
  return status.value === 'failed' ? null : status.value
})
const stepIndex = computed(() => STEPS.findIndex((s) => s.key === currentStep.value))

let timer = null
let lastKey = ''
let lastChange = 0

function stopPolling() {
  clearTimeout(timer)
  timer = null
}

async function poll() {
  try {
    const data = await api.getTask(taskId.value)
    task.value = data
    const key = `${data.status}|${data.step}|${data.step_text}`
    if (key !== lastKey) {
      lastKey = key
      lastChange = Date.now()
    }
    if (PAUSED.includes(data.status)) return stopPolling()
    if (Date.now() - lastChange > STALL_MS) {
      showToast('比平时慢了一些，可以点“刷新状态”再看看')
      return stopPolling()
    }
  } catch (error) {
    showToast(error.message)
    if (error.code === 'TASK_NOT_FOUND') return restart()
  }
  timer = setTimeout(poll, POLL_MS)
}

function startPolling() {
  stopPolling()
  lastChange = Date.now()
  poll()
}

async function act(action) {
  busy.value = true
  try {
    await action()
    startPolling()
  } catch (error) {
    showToast(error.code ? `${error.code}：${error.message}` : error.message)
  } finally {
    busy.value = false
  }
}

function onStart({ groomFileIds, brideFileIds, description }) {
  act(async () => {
    const created = await api.createTask({
      groom_photo_file_ids: groomFileIds,
      bride_photo_file_ids: brideFileIds,
      description,
    })
    taskId.value = created.task_id
    task.value = { status: created.status }
  })
}

const onAnswer = (answers) => act(() => api.submitAnswers(taskId.value, answers))
const onReview = (payload) => act(() => api.review(taskId.value, payload))
const onPay = () => act(() => api.pay(taskId.value, 'mock'))

function restart() {
  stopPolling()
  taskId.value = null
  task.value = null
  lastKey = ''
}

onBeforeUnmount(stopPolling)
</script>

<template>
  <main class="page">
    <header class="header">
      <div class="logo">囍</div>
      <div>
        <h1>小囍 · AI 婚纱照</h1>
        <p>新郎、新娘分别上传照片，确认需求后先出样片，再出 9 张套图</p>
      </div>
      <van-tag v-if="usingMock" type="warning">假数据模式</van-tag>
    </header>

    <nav class="steps">
      <span
        v-for="(s, i) in STEPS"
        :key="s.key"
        :class="{ current: s.key === currentStep, done: stepIndex > i }"
      >{{ i + 1 }}. {{ s.label }}</span>
    </nav>

    <UploadStep v-if="!task" :busy="busy" @start="onStart" />
    <ProgressStep v-else-if="status === 'running' || status === 'delivering'" :task="task" @refresh="startPolling" />
    <QuestionStep
      v-else-if="status === 'waiting_user'"
      :key="task.step + task.questions.map((q) => q.question_id).join()"
      :questions="task.questions"
      :step="task.step"
      :text="task.step_text"
      :busy="busy"
      @submit="onAnswer"
    />
    <PreviewStep
      v-else-if="status === 'preview_ready'"
      :key="task.previews.map((p) => p.image_id).join()"
      :previews="task.previews"
      :generation="task.generation"
      :busy="busy"
      @review="onReview"
    />
    <PayStep v-else-if="status === 'awaiting_payment'" :task="task" :busy="busy" @pay="onPay" />
    <RevealStep v-else-if="status === 'done'" :message="task.message" :deliverables="task.deliverables" @restart="restart" />
    <section v-else-if="status === 'failed'" class="card">
      <h2>这次没做成</h2>
      <table class="kv">
        <tr><td>错误码</td><td class="error-code">{{ task.error?.code || '（无）' }}</td></tr>
        <tr><td>说明</td><td>{{ task.error?.message || '出了点问题，请稍后重新开始' }}</td></tr>
        <tr><td>停在哪一步</td><td>{{ task.step || '（无）' }}</td></tr>
      </table>
      <div class="actions">
        <van-button type="primary" block @click="restart">重新开始</van-button>
      </div>
    </section>

    <DebugPanel :task-id="taskId" :task="task" @refresh="taskId && startPolling()" />
  </main>
</template>
