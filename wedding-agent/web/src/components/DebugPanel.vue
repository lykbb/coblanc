<script setup>
import { ref } from 'vue'
import { ENDPOINTS, apiLog } from '../api.js'

defineProps({ taskId: String, task: Object })
defineEmits(['refresh'])

const open = ref(false)
const pretty = (value) => JSON.stringify(value, null, 2)
</script>

<template>
  <section class="debug">
    <button type="button" @click="open = !open">{{ open ? '▼' : '▶' }} 接口调试（任务 id：{{ taskId || '还没创建' }}）</button>
    <div v-if="open" class="debug-body">
      <button type="button" class="btn-ghost small" :disabled="!taskId" @click="$emit('refresh')">刷新状态（GET 任务）</button>
      <div v-for="(label, name) in ENDPOINTS" :key="name" class="debug-item">
        <h4>{{ label }}</h4>
        <template v-if="apiLog[name]">
          <div class="muted">最近一次：{{ apiLog[name].at }}</div>
          <div>请求</div>
          <pre>{{ pretty(apiLog[name].request) }}</pre>
          <div>{{ apiLog[name].error ? '错误' : '返回' }}</div>
          <pre>{{ pretty(apiLog[name].error || apiLog[name].response) }}</pre>
        </template>
        <div v-else class="muted">还没调用过</div>
      </div>
    </div>
  </section>
</template>
