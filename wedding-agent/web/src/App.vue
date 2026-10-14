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

const POLL_MS = 1500
const STALL_MS = 3 * 60 * 1000
// 到这些状态就停止轮询，等用户操作
const PAUSED = ['waiting_user', 'preview_ready', 'awaiting_payment', 'done', 'failed']

const taskId = ref(null)
const task = ref(null)
const busy = ref(false)
const status = computed(() => task.value?.status)

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
      showToast('比平时慢了一些，请稍后再试')
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
    showToast(error.message)
  } finally {
    busy.value = false
  }
}

function onStart({ groomFiles, brideFiles, description }) {
  act(async () => {
    const upload = async (files) => (await Promise.all(files.map((file) => api.uploadImage(file)))).map((item) => item.file_id)
    const groomFileIds = await upload(groomFiles)
    const brideFileIds = await upload(brideFiles)
    const created = await api.createTask({ groomFileIds, brideFileIds }, description)
    taskId.value = created.task_id
    task.value = { status: created.status }
  })
}

const onAnswer = (answers) => act(() => api.submitAnswers(taskId.value, answers))
const onReview = (payload) => act(() => api.review(taskId.value, payload))
const onPay = () => act(() => api.pay(taskId.value))

function restart() {
  stopPolling()
  taskId.value = null
  task.value = null
}

onBeforeUnmount(stopPolling)
</script>

<template>
  <main class="page">
    <header class="hero">
      <div class="logo">囍</div>
      <div>
        <h1>小囍</h1>
        <p>传上你们俩的照片，来得及的婚纱照</p>
      </div>
      <van-tag v-if="usingMock" type="warning" class="mock-tag">假数据</van-tag>
    </header>

    <UploadStep v-if="!task" :busy="busy" @start="onStart" />
    <ProgressStep v-else-if="status === 'running' || status === 'delivering'" :step="task.step" :text="task.step_text" />
    <QuestionStep
      v-else-if="status === 'waiting_user'"
      :key="task.step + task.questions.map((q) => q.question_id).join()"
      :questions="task.questions"
      :step="task.step"
      :text="task.step_text"
      :busy="busy"
      @submit="onAnswer"
    />
    <PreviewStep v-else-if="status === 'preview_ready'" :key="task.previews[0]?.image_id" :previews="task.previews" :stage="task.generation?.stage" :busy="busy" @review="onReview" />
    <PayStep v-else-if="status === 'awaiting_payment'" :busy="busy" @pay="onPay" />
    <RevealStep v-else-if="status === 'done'" :message="task.message" :deliverables="task.deliverables" @restart="restart" />
    <section v-else-if="status === 'failed'" class="card">
      <h2>这次没拍好</h2>
      <p class="hint">{{ task.error?.message || '出了点问题，请稍后重新开始' }}</p>
      <van-button type="primary" block round @click="restart">重新开始</van-button>
    </section>
  </main>
</template>
