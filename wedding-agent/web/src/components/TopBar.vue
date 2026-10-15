<script setup>
import { computed } from 'vue'
import Icon from './Icon.vue'
import { AMIE } from '../agents.js'
import { activeStage, phase, restart, state } from '../store.js'

// 顶部只显示四位专家的接力：妆造 → 摄影 → 生成 → 审片
const steps = computed(() => {
  const p = phase.value
  const a = activeStage.value
  // 同一时间只亮一位：修图师在检查时，生成算做完；等用户确认样片时，亮生成
  const checking = state.task?.status === 'running' && ['checking', 'retouching'].includes(state.task?.step)
  const generated = checking || ['set_review', 'pay', 'delivering', 'done'].includes(p)
  const reviewed = ['pay', 'delivering', 'done'].includes(p)
  const reviewing = checking || p === 'set_review'
  return [
    { label: '妆造', status: a > 3 ? 'done' : a >= 1 ? 'active' : 'todo' },
    { label: '摄影', status: a > 4 ? 'done' : a === 4 ? 'active' : 'todo' },
    { label: '生成', status: generated ? 'done' : a >= 5 ? 'active' : 'todo' },
    { label: '审片', status: reviewed ? 'done' : reviewing ? 'active' : 'todo' },
  ]
})

function quit() {
  if (window.confirm('结束这次创作，回到新建页面吗？这次的进度会留在「我的项目」里。')) restart()
}
</script>

<template>
  <header class="topbar">
    <ol class="relay" aria-label="专家接力进度">
      <li class="relay-amie">
        <img loading="lazy" decoding="async" :src="AMIE.avatar" alt="Amie" />
      </li>
      <li v-for="step in steps" :key="step.label" class="relay-step" :class="step.status">
        <span class="relay-dot">
          <Icon v-if="step.status === 'done'" name="check" :size="16" />
          <span v-else-if="step.status === 'active'" class="relay-pulse" aria-hidden="true"></span>
        </span>
        <span class="relay-label">{{ step.label }}<span class="sr-only">{{ step.status === 'done' ? '，已完成' : step.status === 'active' ? '，进行中' : '' }}</span></span>
      </li>
    </ol>
    <div class="topbar-right">
      <button v-if="state.taskId" type="button" class="icon-btn" aria-label="结束这次创作" @click="quit"><Icon name="close" /></button>
    </div>
  </header>
</template>
