<script setup>
import { computed } from 'vue'

const props = defineProps({ task: Object })
defineEmits(['refresh'])

// 按后端返回的 step 判断各模块状态（普通轮询，不做动画）
const MODULES = [
  { name: '小囍接单', steps: ['intake'] },
  { name: '妆造师', steps: ['styling'] },
  { name: '摄影师', steps: ['framing'] },
  { name: '小囍写提示词', steps: ['composing'] },
  { name: '生图', steps: ['generating'] },
  { name: '修图师质检 / 修图', steps: ['checking', 'retouching'] },
  { name: '套版和交付', steps: ['packaging'] },
]
const ORDER = ['intake', 'styling', 'framing', 'composing', 'generating', 'checking', 'retouching', 'packaging']
const current = computed(() => ORDER.indexOf(props.task.step))

function state(module) {
  if (module.steps.includes(props.task.step)) return ['进行中', 'status-current']
  if (current.value >= 0 && module.steps.every((s) => ORDER.indexOf(s) < current.value)) return ['已完成', 'status-done']
  return ['未开始', 'status-todo']
}
const STAGE = { sample: '样片（1 张）', set: '套图（9 张）' }
</script>

<template>
  <section class="card">
    <h2>{{ task.status === 'delivering' ? '正在制作交付物' : '正在制作' }}</h2>
    <p class="hint">{{ task.step_text || '小囍正在接单' }}（每 1.5 秒自动刷新）</p>
    <table class="kv">
      <tr><td>状态 status</td><td>{{ task.status }}</td></tr>
      <tr><td>当前步骤 step</td><td>{{ task.step || '（还没开始）' }}</td></tr>
      <tr v-for="m in MODULES" :key="m.name">
        <td>{{ m.name }}</td>
        <td :class="state(m)[1]">{{ state(m)[0] }}</td>
      </tr>
      <template v-if="task.generation">
        <tr><td>生图阶段</td><td>{{ STAGE[task.generation.stage] || task.generation.stage || '—' }}</td></tr>
        <tr><td>累计生成</td><td>{{ task.generation.total_images }} 张，引擎 {{ task.generation.engine }}，上次耗时 {{ task.generation.seconds }} 秒</td></tr>
      </template>
      <tr v-if="task.photo_counts">
        <td>照片</td>
        <td>新郎 {{ task.photo_counts.groom }} 张，新娘 {{ task.photo_counts.bride }} 张<span v-if="task.photo_counts.legacy">，旧版合照 {{ task.photo_counts.legacy }} 张</span></td>
      </tr>
    </table>
    <div class="actions">
      <van-button size="small" plain @click="$emit('refresh')">刷新状态</van-button>
    </div>
  </section>
</template>
