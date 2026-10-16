<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import SideNav from './components/SideNav.vue'
import TopBar from './components/TopBar.vue'
import StudioCanvas from './components/StudioCanvas.vue'
import OverviewView from './components/OverviewView.vue'
import AmiePanel from './components/AmiePanel.vue'
import QuestionDialog from './components/QuestionDialog.vue'
import RedoDialog from './components/RedoDialog.vue'
import PayDialog from './components/PayDialog.vue'
import Lightbox from './components/Lightbox.vue'
import DeliveryView from './components/DeliveryView.vue'
import ProjectsView from './components/ProjectsView.vue'
import LibraryView from './components/LibraryView.vue'
import ReferenceWall from './components/ReferenceWall.vue'
import DebugPanel from './components/DebugPanel.vue'
import Icon from './components/Icon.vue'
import { usingMock } from './api.js'
import { clearError, refresh, restart, resumeLastTask, state } from './store.js'

const SIDE_COLLAPSED_W = 76
const SIDE_MIN = 188
const SIDE_MAX = 320
const SIDE_COLLAPSE_AT = 148
const SIDE_EXPAND_AT = 120
const AMIE_MIN = 260
const AMIE_MAX = 440
const CENTER_MIN = 360
const KEY_SIDE = 'coblanc.layout.sideW'
const KEY_AMIE = 'coblanc.layout.amieW'
const KEY_COLLAPSED = 'coblanc.layout.sideCollapsed'

const debug = new URLSearchParams(location.search).has('debug')
const questionsKey = computed(() => (state.task ? state.task.step + (state.task.questions || []).map((q) => q.question_id).join() : ''))
const inStudio = computed(() => state.view === 'studio')

const sideW = ref(228)
const amieW = ref(300)
const sideCollapsed = ref(false)
const resizing = ref(false)
const resizingKind = ref(null)

function readNum(key, fallback) {
  try {
    const n = Number(localStorage.getItem(key))
    return Number.isFinite(n) ? n : fallback
  } catch {
    return fallback
  }
}

function persist() {
  try {
    localStorage.setItem(KEY_SIDE, String(sideCollapsed.value ? SIDE_COLLAPSED_W : sideW.value))
    localStorage.setItem(KEY_AMIE, String(amieW.value))
    localStorage.setItem(KEY_COLLAPSED, sideCollapsed.value ? '1' : '0')
    localStorage.removeItem('coblanc.sideCollapsed')
  } catch {
    /* ignore */
  }
}

function clamp(n, min, max) {
  return Math.min(max, Math.max(min, n))
}

const layoutStyle = computed(() => ({
  '--side-w': `${sideW.value}px`,
  '--amie-w': `${amieW.value}px`,
}))

let drag = null

function onPointerMove(event) {
  if (!drag) return
  const dx = event.clientX - drag.startX
  if (drag.kind === 'side') {
    const maxByCenter = window.innerWidth - 32 - 16 - (inStudio.value ? amieW.value + 20 : 0) - CENTER_MIN
    const next = clamp(drag.startW + dx, SIDE_COLLAPSED_W, Math.min(SIDE_MAX, Math.max(SIDE_COLLAPSED_W, maxByCenter)))
    sideW.value = next
    sideCollapsed.value = next <= SIDE_COLLAPSE_AT
  } else if (drag.kind === 'amie') {
    // splitter 在 Amie 左侧：右拖变窄
    const sideNow = sideW.value
    const maxByCenter = window.innerWidth - 32 - 16 - sideNow - 20 - CENTER_MIN
    const next = clamp(drag.startW - dx, AMIE_MIN, Math.min(AMIE_MAX, Math.max(AMIE_MIN, maxByCenter)))
    amieW.value = next
  }
}

function onPointerUp() {
  if (!drag) return
  const kind = drag.kind
  drag = null
  resizing.value = false
  resizingKind.value = null
  document.body.classList.remove('is-col-resizing')
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
  // 松手后吸附，靠 CSS 过渡避免闪一下
  if (kind === 'side') {
    if (sideCollapsed.value || sideW.value <= SIDE_COLLAPSE_AT) {
      sideCollapsed.value = true
      sideW.value = SIDE_COLLAPSED_W
    } else {
      sideCollapsed.value = false
      sideW.value = clamp(sideW.value, SIDE_MIN, SIDE_MAX)
    }
  } else if (kind === 'amie') {
    amieW.value = clamp(amieW.value, AMIE_MIN, AMIE_MAX)
  }
  persist()
}

function startDrag(kind, event) {
  event.preventDefault()
  resizing.value = true
  resizingKind.value = kind
  document.body.classList.add('is-col-resizing')
  drag = {
    kind,
    startX: event.clientX,
    startW: kind === 'side' ? sideW.value : amieW.value,
  }
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerUp)
}

onMounted(() => {
  const collapsed = (() => {
    try {
      const v = localStorage.getItem(KEY_COLLAPSED)
      if (v === '1' || v === '0') return v === '1'
      return localStorage.getItem('coblanc.sideCollapsed') === '1'
    } catch {
      return false
    }
  })()
  sideCollapsed.value = collapsed
  const savedSide = readNum(KEY_SIDE, 228)
  sideW.value = collapsed ? SIDE_COLLAPSED_W : clamp(Math.max(savedSide, SIDE_MIN), SIDE_MIN, SIDE_MAX)
  // 旧默认 360 偏宽，演示期软迁到 300
  const savedAmie = readNum(KEY_AMIE, 300)
  amieW.value = clamp(savedAmie >= 350 ? 300 : savedAmie, AMIE_MIN, AMIE_MAX)
  resumeLastTask()
})

onBeforeUnmount(() => {
  onPointerUp()
})
</script>

<template>
  <div class="app" :class="{ 'is-resizing': resizing, [`resizing-${resizingKind}`]: !!resizingKind }" :style="layoutStyle">
    <SideNav :collapsed="sideCollapsed" />
    <div
      class="split-v split-side"
      role="separator"
      aria-orientation="vertical"
      aria-label="调整左侧导航宽度"
      tabindex="0"
      @pointerdown="startDrag('side', $event)"
    ></div>
    <div class="main-area">
      <TopBar v-if="inStudio" />
      <div v-if="state.error" class="banner error" role="alert">
        <Icon name="alert" />
        <span><b v-if="state.error.code && !state.error.lost">{{ state.error.code }}</b>{{ state.error.message }}</span>
        <button v-if="state.error.lost" type="button" class="link-btn" @click="clearError(); restart()">重新开始</button>
        <button v-else-if="state.taskId" type="button" class="link-btn" @click="clearError(); refresh()">刷新状态</button>
        <button type="button" class="icon-btn" aria-label="关闭提示" @click="clearError"><Icon name="close" :size="16" /></button>
      </div>
      <div v-if="state.notice" class="banner notice" role="status">
        <span>{{ state.notice }}</span>
        <button type="button" class="icon-btn" aria-label="关闭提示" @click="state.notice = null"><Icon name="close" :size="16" /></button>
      </div>
      <div class="workspace" :class="{ 'with-amie': inStudio }">
        <main class="workspace-main">
          <OverviewView v-if="state.view === 'overview'" />
          <StudioCanvas v-else-if="state.view === 'studio'" />
          <ProjectsView v-else-if="state.view === 'projects'" />
          <LibraryView v-else-if="state.view === 'library'" />
          <ReferenceWall v-else-if="state.view === 'refs'" />
          <DeliveryView v-else-if="state.view === 'delivery'" />
        </main>
        <div
          v-if="inStudio"
          class="split-v split-amie"
          role="separator"
          aria-orientation="vertical"
          aria-label="调整 Amie 面板宽度"
          tabindex="0"
          @pointerdown="startDrag('amie', $event)"
        ></div>
        <AmiePanel v-if="inStudio" />
      </div>
    </div>

    <QuestionDialog v-if="state.dialog === 'questions' && state.task?.status === 'waiting_user'" :key="questionsKey" />
    <RedoDialog v-if="state.dialog === 'redo' && state.task?.status === 'preview_ready'" />
    <PayDialog v-if="state.dialog === 'pay' && state.task?.status === 'awaiting_payment'" />
    <Lightbox v-if="state.lightbox" />
    <span v-if="usingMock" class="mock-badge">假数据模式</span>
    <DebugPanel v-if="debug" class="debug-float" :task-id="state.taskId" :task="state.task" @refresh="refresh" />
  </div>
</template>
