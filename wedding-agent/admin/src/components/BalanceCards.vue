<script setup>
// DeepSeek 实时余额（概览、Token 用量共用）：每 10 秒取一次 /balance；后端按页面是否开着决定查官方接口的频率。
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ops } from '../api.js'

const data = ref(null)
let timer
async function load() { try { data.value = await ops.balance() } catch { /* 安静处理 */ } }
onMounted(() => { load(); timer = setInterval(load, 10000) })
onUnmounted(() => clearInterval(timer))

const yuan = (v) => (v == null ? '—' : '¥' + (Math.abs(v) < 1 ? v.toFixed(3) : v.toFixed(2)))
const W = 120, H = 28
const spark = computed(() => {
  const pts = data.value?.spark || []
  if (pts.length < 2) return ''
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1])
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys)
  return pts.map(([x, y]) => `${(((x - x0) / (x1 - x0 || 1)) * W).toFixed(1)},${(H - 2 - ((y - y0) / (y1 - y0 || 1)) * (H - 4)).toFixed(1)}`).join(' ')
})
const ago = computed(() => {
  const at = data.value?.current?.at
  if (!at) return ''
  const s = Math.max(0, Date.now() / 1000 - at)
  return s < 90 ? '刚刚更新' : `${Math.round(s / 60)} 分钟前更新`
})
</script>

<template>
  <div v-if="data && data.enabled" class="stat-row balance-row">
    <div class="stat-card">
      <span>DeepSeek 余额<em class="muted-s balance-ago">{{ data.error ? '查询失败 · ' + data.error : ago }}</em></span>
      <div class="balance-main">
        <strong>{{ data.current ? (data.current.currency === 'USD' ? '$' : '¥') + data.current.total.toFixed(2) : '—' }}</strong>
        <svg v-if="spark" :viewBox="`0 0 ${W} ${H}`" :width="W" :height="H" class="balance-spark" aria-label="近 24 小时余额走势"><polyline :points="spark" /></svg>
      </div>
    </div>
    <div class="stat-card"><span>今日实际花费</span><strong>{{ yuan(data.spent_today) }}</strong></div>
    <div class="stat-card"><span>我们算的 DeepSeek 费用</span><strong>{{ yuan(data.our_cost_today) }}</strong></div>
    <div class="stat-card" :class="{ 'balance-warn': data.warn }" :title="data.warn ? '偏差超过 20% 且超过 ¥0.5' : ''">
      <span>差额</span><strong>{{ (data.diff > 0 ? '+' : '') + yuan(data.diff) }}</strong>
    </div>
  </div>
</template>
