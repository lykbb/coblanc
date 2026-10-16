<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { bytes, ops } from '../api.js'

const PALETTE = ['#ef9c88', '#b6a5ea', '#e8b07c', '#7fbf9d', '#eda1b2', '#8fb3e0', '#c9b07a']
const server = ref(null)
const usage = ref(null)
const period = ref('7d')
const error = ref('')
let timer

async function loadServer() {
  try { server.value = await ops.server() } catch (e) { error.value = e.message }
}
async function loadUsage() {
  try { usage.value = await ops.usage(period.value) } catch (e) { error.value = e.message }
}
onMounted(() => { loadServer(); loadUsage(); timer = setInterval(loadServer, 10000) })
onUnmounted(() => clearInterval(timer))
watch(period, loadUsage)

const pct = (used, total) => (total ? Math.round((100 * used) / total) : 0)
const num = (n) => (n || 0).toLocaleString('zh-CN')
const short = (n) => (n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'K' : String(n))

// 每天一根柱：按模型堆叠 token；柱下方标生图张数
const days = computed(() => {
  const count = period.value === '30d' ? 30 : 7
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(Date.now() - (count - 1 - i) * 86400000)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  })
})
const tokenModels = computed(() => (usage.value?.models || []).filter((m) => m.total).map((m) => m.model).filter((m, i, a) => a.indexOf(m) === i))
const color = (model) => PALETTE[tokenModels.value.indexOf(model) % PALETTE.length]
const chart = computed(() => {
  const rows = usage.value?.daily_models || []
  const bars = days.value.map((day) => {
    const parts = rows.filter((r) => r.day === day && r.total).map((r) => ({ model: r.model, total: r.total }))
    return { day, parts, total: parts.reduce((s, p) => s + p.total, 0), images: rows.filter((r) => r.day === day).reduce((s, r) => s + r.images, 0) }
  })
  return { bars, max: Math.max(1, ...bars.map((b) => b.total)) }
})
const W = 720, H = 200, PAD = 28
const barW = computed(() => (W - PAD) / days.value.length)
</script>

<template>
  <section class="portal-page">
    <header class="page-head"><h1>概览</h1></header>
    <p v-if="error" class="page-error" role="alert">{{ error }}</p>

    <div v-if="server" class="stat-row">
      <div class="stat-card"><span>CPU</span><strong>{{ server.cpu.cores }} 核 · {{ server.cpu.percent ?? '—' }}%</strong><div class="bar"><i :style="{ width: (server.cpu.percent || 0) + '%' }" /></div></div>
      <div class="stat-card"><span>负载</span><strong>{{ server.cpu.load.map((v) => v.toFixed(2)).join(' / ') }}</strong></div>
      <div class="stat-card"><span>内存</span><strong>{{ bytes(server.memory.total - server.memory.available) }} / {{ bytes(server.memory.total) }}</strong><div class="bar"><i :style="{ width: pct(server.memory.total - server.memory.available, server.memory.total) + '%' }" /></div></div>
      <div class="stat-card"><span>磁盘</span><strong>{{ bytes(server.disk.used) }} / {{ bytes(server.disk.total) }}</strong><div class="bar"><i :style="{ width: pct(server.disk.used, server.disk.total) + '%' }" /></div></div>
      <div class="stat-card"><span>任务</span><strong>进行中 {{ server.tasks.running }} · 排队 {{ server.tasks.queued }}</strong></div>
      <div class="stat-card"><span>服务</span>
        <div class="svc-list"><span v-for="(state, name) in server.services" :key="name"><i class="mark" :class="state === 'active' ? 'good' : 'bad'" />{{ name }}</span></div>
      </div>
    </div>
    <p v-if="server" class="muted-s">{{ server.os }} · {{ server.cpu.cores }} 核 · {{ bytes(server.memory.total) }} 内存 · {{ server.hostname }}</p>

    <header class="page-head">
      <h2 class="sub-h">Token 消耗</h2>
      <div class="seg push">
        <button type="button" :class="{ on: period === '7d' }" @click="period = '7d'">7 天</button>
        <button type="button" :class="{ on: period === '30d' }" @click="period = '30d'">30 天</button>
      </div>
    </header>
    <template v-if="usage">
      <p v-if="!usage.total?.calls" class="empty-s">暂无数据</p>
      <template v-else>
        <div class="chart-card">
          <svg :viewBox="`0 0 ${W} ${H + 36}`" class="chart" role="img" aria-label="每日 token 消耗">
            <text x="0" y="12" class="chart-axis">{{ short(chart.max) }}</text>
            <line :x1="PAD" :x2="W" :y1="H" :y2="H" class="chart-base" />
            <g v-for="(b, i) in chart.bars" :key="b.day">
              <template v-for="(p, j) in b.parts" :key="p.model">
                <rect :x="PAD + i * barW + barW * 0.18" :width="barW * 0.64"
                      :y="H - (b.parts.slice(0, j + 1).reduce((s, q) => s + q.total, 0) / chart.max) * (H - 16)"
                      :height="(p.total / chart.max) * (H - 16)" :fill="color(p.model)" rx="2"><title>{{ b.day }} {{ p.model }}：{{ num(p.total) }}</title></rect>
              </template>
              <text v-if="b.images" :x="PAD + i * barW + barW / 2" :y="H + 14" class="chart-img">{{ b.images }}张</text>
              <text v-if="period === '7d' || i % 5 === 4" :x="PAD + i * barW + barW / 2" :y="H + 30" class="chart-day">{{ b.day.slice(5) }}</text>
            </g>
          </svg>
          <div class="chart-legend"><span v-for="m in tokenModels" :key="m"><i :style="{ background: color(m) }" />{{ m }}</span></div>
        </div>
        <table class="data-table">
          <thead><tr><th>模型</th><th>调用</th><th>token</th><th>生图</th></tr></thead>
          <tbody>
            <tr v-for="m in usage.models" :key="m.provider + m.model + m.kind">
              <td class="mono">{{ m.model }}</td><td class="right">{{ num(m.calls) }}</td><td class="right">{{ num(m.total) }}</td><td class="right">{{ num(m.images) }}<span v-if="m.backfilled" class="tag">含回填</span></td>
            </tr>
          </tbody>
        </table>
      </template>
    </template>
  </section>
</template>
