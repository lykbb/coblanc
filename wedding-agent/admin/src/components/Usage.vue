<script setup>
import { onMounted, ref, watch } from 'vue'
import { ops } from '../api.js'

const PERIODS = [{ key: 'today', label: '今天' }, { key: '7d', label: '7 天' }, { key: '30d', label: '30 天' }]
const KINDS = { agent: '对话', cheap: '轻量', vision: '看图', image: '生图' }
const period = ref('7d')
const data = ref(null)
const error = ref('')
async function load() {
  error.value = ''
  try { data.value = await ops.usage(period.value) } catch (e) { error.value = e.message }
}
onMounted(load)
watch(period, load)
const num = (n) => (n || 0).toLocaleString('zh-CN')
const money = (b) => (b.cost == null ? '—' : `${b.cost.toFixed(b.cost < 1 ? 4 : 2)} ${b.currency}`)
</script>

<template>
  <section class="portal-page">
    <header class="page-head">
      <h1>Token 用量</h1>
      <div class="seg push">
        <button v-for="p in PERIODS" :key="p.key" type="button" :class="{ on: period === p.key }" @click="period = p.key">{{ p.label }}</button>
      </div>
    </header>
    <p v-if="error" class="page-error" role="alert">{{ error }}</p>
    <template v-if="data">
      <p v-if="!data.total?.calls" class="empty-s">暂无数据</p>
      <template v-else>
        <div class="stat-row">
          <div class="stat-card"><span>调用</span><strong>{{ num(data.total.calls) }}</strong></div>
          <div class="stat-card"><span>输入 token</span><strong>{{ num(data.total.input) }}</strong></div>
          <div class="stat-card"><span>输出 token</span><strong>{{ num(data.total.output) }}</strong></div>
          <div class="stat-card"><span>生图</span><strong>{{ num(data.total.images) }}</strong></div>
          <div class="stat-card"><span>费用估算</span><strong>{{ money(data.total) }}</strong></div>
        </div>
        <p v-if="data.total.backfilled" class="muted-s">含 {{ data.total.backfilled }} 条回填（上线记录前的任务，仅生图张数下限）</p>
        <h2 class="sub-h">按模型</h2>
        <table class="data-table">
          <thead><tr><th>服务</th><th>模型</th><th>用途</th><th>调用</th><th>输入</th><th>输出</th><th>合计</th><th>生图</th><th>费用估算</th></tr></thead>
          <tbody>
            <tr v-for="m in data.models" :key="m.provider + m.model + m.kind">
              <td>{{ m.provider }}</td><td class="mono">{{ m.model }}</td><td>{{ KINDS[m.kind] || m.kind }}</td>
              <td class="right">{{ num(m.calls) }}</td><td class="right">{{ num(m.input) }}</td><td class="right">{{ num(m.output) }}</td>
              <td class="right">{{ num(m.total) }}</td><td class="right">{{ num(m.images) }}</td><td class="right">{{ money(m) }}</td>
            </tr>
          </tbody>
        </table>
        <h2 class="sub-h">按天</h2>
        <table class="data-table">
          <thead><tr><th>日期</th><th>调用</th><th>合计 token</th><th>生图</th><th>费用估算</th></tr></thead>
          <tbody>
            <tr v-for="d in data.days" :key="d.day"><td>{{ d.day }}</td><td class="right">{{ num(d.calls) }}</td><td class="right">{{ num(d.total) }}</td><td class="right">{{ num(d.images) }}</td><td class="right">{{ money(d) }}</td></tr>
          </tbody>
        </table>
        <h2 class="sub-h">按任务</h2>
        <table class="data-table">
          <thead><tr><th>任务</th><th>调用</th><th>输入</th><th>输出</th><th>生图</th><th>费用估算</th></tr></thead>
          <tbody>
            <tr v-for="t in data.tasks" :key="t.task_id"><td class="mono">{{ t.task_id }}</td><td class="right">{{ num(t.calls) }}</td><td class="right">{{ num(t.input) }}</td><td class="right">{{ num(t.output) }}</td><td class="right">{{ num(t.images) }}</td><td class="right">{{ money(t) }}</td></tr>
          </tbody>
        </table>
      </template>
    </template>
  </section>
</template>
