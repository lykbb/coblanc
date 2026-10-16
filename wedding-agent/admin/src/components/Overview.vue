<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { bytes, ops } from '../api.js'
import StatusBar from './StatusBar.vue'
import StatusLegend from './StatusLegend.vue'
import { KINDS, money, num, priceSources, priceTitle, short, ticks, yuan } from '../usage.js'

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

// 每天一根柱：按模型堆叠 token（左轴）；费用折线（右轴）；柱下标生图张数。数据与 Token 用量页同源（/usage 的 daily_models、days）
const days = computed(() => {
  const count = period.value === '30d' ? 30 : 7
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(Date.now() - (count - 1 - i) * 86400000)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  })
})
const tokenModels = computed(() => [...new Set((usage.value?.daily_models || []).filter((r) => r.total).map((r) => r.model))])
const color = (model) => PALETTE[tokenModels.value.indexOf(model) % PALETTE.length]
const chart = computed(() => {
  const rows = usage.value?.daily_models || []
  const totals = Object.fromEntries((usage.value?.days || []).map((d) => [d.day, d]))
  const bars = days.value.map((day) => {
    const parts = rows.filter((r) => r.day === day && r.total).map((r) => ({ model: r.model, total: r.total }))
    const t = totals[day] || {}
    return { day, parts, total: parts.reduce((s, p) => s + p.total, 0), images: t.images || 0, cost: t.cost || 0 }
  })
  const [tokenMax, tokenTicks] = ticks(Math.max(...bars.map((b) => b.total)))
  const [costMax, costTicks] = ticks(Math.max(...bars.map((b) => b.cost)))
  return { bars, tokenMax, tokenTicks, costMax, costTicks }
})
const W = 760, H = 230, L = 56, R = 56, TOP = 26
const barW = computed(() => (W - L - R) / days.value.length)
const y = (v, max) => H - (v / max) * (H - TOP)
const cx = (i) => L + i * barW.value + barW.value / 2
// 堆叠段：每段至少 2px（很小的用量也看得见），从底往上依次排，不会错位
const segments = (b) => {
  let top = H
  return b.parts.map((p) => {
    const h = Math.max(2, (p.total / chart.value.tokenMax) * (H - TOP))
    top -= h
    return { ...p, y: top, h }
  })
}
const costLine = computed(() => chart.value.bars.map((b, i) => `${cx(i)},${y(b.cost, chart.value.costMax)}`).join(' '))
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
      <template v-if="usage.total">
        <div class="stat-row">
          <div class="stat-card"><span>输入 token</span><strong>{{ num(usage.total.input) }}</strong></div>
          <div class="stat-card"><span>缓存命中</span><strong>{{ num(usage.total.cached) }}</strong></div>
          <div class="stat-card"><span>输出 token</span><strong>{{ num(usage.total.output) }}</strong></div>
          <div class="stat-card"><span>生图</span><strong>{{ num(usage.total.images) }} 张</strong></div>
          <div class="stat-card"><span>费用</span><strong>{{ money(usage.total) }}</strong></div>
        </div>
        <div class="chart-card">
          <svg :viewBox="`0 0 ${W} ${H + 40}`" class="chart" role="img" aria-label="每日 token、费用与生图">
            <g v-for="t in chart.tokenTicks" :key="'l' + t">
              <line :x1="L" :x2="W - R" :y1="y(t, chart.tokenMax)" :y2="y(t, chart.tokenMax)" :class="t ? 'chart-grid' : 'chart-base'" />
              <text :x="L - 8" :y="y(t, chart.tokenMax)" text-anchor="end" dominant-baseline="middle" class="chart-axis">{{ short(t) }}</text>
            </g>
            <text v-for="t in chart.costTicks" :key="'r' + t" :x="W - R + 8" :y="y(t, chart.costMax)" dominant-baseline="middle" class="chart-axis cost">{{ yuan(t) }}</text>
            <text :x="L - 8" y="10" text-anchor="end" class="chart-axis-title">token</text>
            <text :x="W - R + 8" y="10" class="chart-axis-title cost">费用</text>
            <g v-for="(b, i) in chart.bars" :key="b.day">
              <rect v-for="p in segments(b)" :key="p.model" :x="L + i * barW + barW * 0.18" :width="barW * 0.64"
                    :y="p.y" :height="p.h" :fill="color(p.model)"><title>{{ b.day }} {{ p.model }}：{{ num(p.total) }} token</title></rect>
              <text v-if="b.images" :x="cx(i)" :y="H + 15" class="chart-img">{{ b.images }}张</text>
              <text v-if="period === '7d' || i % 5 === 4" :x="cx(i)" :y="H + 32" class="chart-day">{{ b.day.slice(5) }}</text>
            </g>
            <polyline :points="costLine" class="chart-cost" />
            <circle v-for="(b, i) in chart.bars" :key="'c' + b.day" :cx="cx(i)" :cy="y(b.cost, chart.costMax)" r="3" class="chart-cost-dot"><title>{{ b.day }} 费用 {{ yuan(b.cost) }}</title></circle>
          </svg>
          <div class="chart-legend">
            <span v-for="m in tokenModels" :key="m"><i :style="{ background: color(m) }" />{{ m }}</span>
            <span><i class="line" />费用（右轴）</span>
            <span><b class="chart-img">张</b>每日生图</span>
          </div>
        </div>
        <div class="legend-row"><StatusLegend :keys="usage.models.filter((m) => m.active !== false || m.calls).map((m) => (m.active ? 'in_use' : 'history'))" /></div>
        <div class="table-wrap"><table class="data-table">
          <thead><tr><th>模型</th><th>步骤</th><th class="right">调用</th><th class="right">输入</th><th class="right">缓存</th><th class="right">输出</th><th class="right">生图</th><th class="right">费用</th></tr></thead>
          <tbody>
            <tr v-for="m in usage.models.filter((m) => m.active !== false || m.calls)" :key="m.provider + m.model + m.kind">
              <td class="ell" :title="m.model"><StatusBar :s="m.active ? 'in_use' : 'history'" /><span class="mono">{{ m.model }}</span><span class="muted-s"> · {{ KINDS[m.kind] || m.kind }}</span></td><td class="ell" :title="m.step_labels.join('、')">{{ m.step_labels.join('、') || '—' }}</td>
              <td class="right">{{ num(m.calls) }}</td><td class="right">{{ num(m.input) }}</td><td class="right">{{ num(m.cached) }}</td><td class="right">{{ num(m.output) }}</td><td class="right">{{ num(m.images) }}<span v-if="m.backfilled" class="tag">含回填</span></td><td class="right" :title="priceTitle(m)">{{ money(m) }}</td>
            </tr>
          </tbody>
        </table></div>
        <p class="muted-s price-line">单价来源：<template v-for="(p, i) in priceSources(usage.models)" :key="p.provider"><span v-if="i"> · </span><a :href="p.source" target="_blank" rel="noopener noreferrer">{{ p.provider }} 官方</a></template> · 版本 {{ usage.prices.version }}</p>
      </template>
    </template>
  </section>
</template>
