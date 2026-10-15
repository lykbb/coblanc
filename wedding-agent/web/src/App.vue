<script setup>
import { computed, onMounted } from 'vue'
import SideNav from './components/SideNav.vue'
import TopBar from './components/TopBar.vue'
import StudioCanvas from './components/StudioCanvas.vue'
import AmiePanel from './components/AmiePanel.vue'
import QuestionDialog from './components/QuestionDialog.vue'
import RedoDialog from './components/RedoDialog.vue'
import PayDialog from './components/PayDialog.vue'
import Lightbox from './components/Lightbox.vue'
import DeliveryView from './components/DeliveryView.vue'
import ProjectsView from './components/ProjectsView.vue'
import LibraryView from './components/LibraryView.vue'
import DebugPanel from './components/DebugPanel.vue'
import Icon from './components/Icon.vue'
import { usingMock } from './api.js'
import { clearError, refresh, resumeLastTask, state } from './store.js'

// 地址里带 ?debug 时显示接口调试面板
const debug = new URLSearchParams(location.search).has('debug')
const questionsKey = computed(() => (state.task ? state.task.step + (state.task.questions || []).map((q) => q.question_id).join() : ''))

onMounted(resumeLastTask)
</script>

<template>
  <div class="app">
    <SideNav />
    <div class="main-area">
      <TopBar />
      <div v-if="state.error" class="banner error" role="alert">
        <Icon name="alert" />
        <span><b v-if="state.error.code">{{ state.error.code }}</b>{{ state.error.message }}</span>
        <button v-if="state.taskId" type="button" class="link-btn" @click="clearError(); refresh()">刷新状态</button>
        <button type="button" class="icon-btn" aria-label="关闭提示" @click="clearError"><Icon name="close" :size="16" /></button>
      </div>
      <div v-if="state.notice" class="banner notice" role="status">
        <span>{{ state.notice }}</span>
        <button type="button" class="icon-btn" aria-label="关闭提示" @click="state.notice = null"><Icon name="close" :size="16" /></button>
      </div>
      <div class="workspace">
        <main class="workspace-main">
          <StudioCanvas v-if="state.view === 'studio'" />
          <ProjectsView v-else-if="state.view === 'projects'" />
          <LibraryView v-else-if="state.view === 'library'" />
          <DeliveryView v-else-if="state.view === 'delivery'" />
        </main>
        <AmiePanel />
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
