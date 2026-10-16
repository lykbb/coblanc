<script setup>
import { onMounted, ref } from 'vue'
import { tasks, when } from '../api.js'

const STATUS = { running: '进行中', waiting_user: '等用户回答', preview_ready: '待确认', awaiting_payment: '待支付', delivering: '交付中', done: '完成', failed: '失败' }
const items = ref([])
const error = ref('')
const open = ref(null)
const big = ref(null)

async function load() {
  try {
    items.value = (await tasks.list()).items
    error.value = ''
  } catch (e) {
    error.value = e.message
  }
}
onMounted(load)

async function view(item) {
  if (open.value?.task_id === item.task_id) return (open.value = null)
  try {
    open.value = await tasks.get(item.task_id)
  } catch (e) {
    error.value = e.message
  }
}
const GROUPS = [['photos', '用户照片'], ['previews', '样片 / 预览'], ['deliverables', '交付']]
</script>

<template>
  <section class="admin-page">
    <header class="page-head"><h1>任务</h1><span class="refwall-count">{{ items.length }}</span>
      <button type="button" class="ghost-btn push" @click="load">刷新</button></header>
    <p v-if="error" class="refwall-error" role="alert">{{ error }}</p>
    <table class="admin-table">
      <thead><tr><th>任务</th><th>状态</th><th>步骤</th><th>错误</th><th>更新</th></tr></thead>
      <tbody>
        <template v-for="t in items" :key="t.task_id">
          <tr class="clickable" :class="{ on: open?.task_id === t.task_id }" @click="view(t)">
            <td class="mono">{{ t.task_id }}</td>
            <td><i class="mark" :class="t.status === 'failed' ? 'bad' : t.status === 'done' ? 'good' : 'idle'"></i>{{ STATUS[t.status] || t.status }}</td>
            <td>{{ t.step_text || t.step || '—' }}</td>
            <td class="err">{{ t.error ? (t.error.title || t.error.code) + (t.error.message ? '：' + t.error.message : '') : '—' }}</td>
            <td class="muted-s">{{ when(t.updated_at) }}</td>
          </tr>
          <tr v-if="open?.task_id === t.task_id" class="detail">
            <td colspan="5">
              <div v-for="[key, label] in GROUPS" :key="key" class="task-group">
                <template v-if="open.images[key].length">
                  <span class="muted-s">{{ label }} · {{ open.images[key].length }}</span>
                  <div class="task-thumbs">
                    <img v-for="url in open.images[key]" :key="url" :src="url" alt="" loading="lazy" @click="big = url" />
                  </div>
                </template>
              </div>
              <span v-if="!GROUPS.some(([k]) => open.images[k].length)" class="muted-s">没有图片</span>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
    <div v-if="big" class="ref-modal dark" @click="big = null"><img class="task-big" :src="big" alt="" /></div>
  </section>
</template>
