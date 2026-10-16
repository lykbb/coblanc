<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { bytes, ops, when } from '../api.js'
import { serviceKey } from '../status.js'
import StatusLegend from './StatusLegend.vue'
import StatusBar from './StatusBar.vue'

const data = ref(null)
const error = ref('')
let timer
async function load() {
  try { data.value = await ops.server(); error.value = '' } catch (e) { error.value = e.message }
}
onMounted(() => { load(); timer = setInterval(load, 5000) })
onUnmounted(() => clearInterval(timer))
const pct = (used, total) => (total ? Math.round((100 * used) / total) : 0)
function uptime(s) {
  if (s == null) return '—'
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
  return `${d ? d + ' 天 ' : ''}${h} 小时 ${m} 分`
}
</script>

<template>
  <section class="portal-page">
    <header class="page-head"><h1>服务器</h1><span v-if="data" class="page-count">{{ when(data.at) }}</span></header>
    <p v-if="error" class="page-error" role="alert">{{ error }}</p>
    <template v-if="data">
      <div class="stat-row">
        <div class="stat-card"><span>CPU</span><strong>{{ data.cpu.percent ?? '—' }}%</strong><div class="bar"><i :style="{ width: (data.cpu.percent || 0) + '%' }" /></div></div>
        <div class="stat-card"><span>负载 1 / 5 / 15 分</span><strong>{{ data.cpu.load.map((v) => v.toFixed(2)).join(' / ') }}</strong></div>
        <div class="stat-card">
          <span>内存</span><strong>{{ bytes(data.memory.total - data.memory.available) }} / {{ bytes(data.memory.total) }}</strong>
          <div class="bar"><i :style="{ width: pct(data.memory.total - data.memory.available, data.memory.total) + '%' }" /></div>
        </div>
        <div class="stat-card">
          <span>交换</span><strong>{{ bytes(data.memory.swap_total - data.memory.swap_free) }} / {{ bytes(data.memory.swap_total) }}</strong>
          <div class="bar"><i :style="{ width: pct(data.memory.swap_total - data.memory.swap_free, data.memory.swap_total) + '%' }" /></div>
        </div>
        <div class="stat-card">
          <span>磁盘</span><strong>{{ bytes(data.disk.used) }} / {{ bytes(data.disk.total) }}</strong>
          <div class="bar"><i :style="{ width: pct(data.disk.used, data.disk.total) + '%' }" /></div>
        </div>
        <div class="stat-card">
          <span>参考图库</span><strong>{{ bytes(data.references.used) }} / {{ bytes(data.references.cap) }}</strong>
          <div class="bar"><i :style="{ width: pct(data.references.used, data.references.cap) + '%' }" /></div>
        </div>
        <div class="stat-card"><span>运行时间</span><strong>{{ uptime(data.uptime_seconds) }}</strong></div>
        <div class="stat-card"><span>任务</span><strong>进行中 {{ data.tasks.running }} · 排队 {{ data.tasks.queued }}</strong></div>
      </div>
      <h2 class="sub-h">服务<StatusLegend v-if="data" :keys="Object.values(data.services).map(serviceKey)" /></h2>
      <table class="data-table">
        <tbody>
          <tr v-for="(state, name) in data.services" :key="name">
            <td class="mono"><StatusBar :s="serviceKey(state)" />{{ name }}</td>
          </tr>
        </tbody>
      </table>
      <h2 class="sub-h">配置</h2>
      <table class="data-table">
        <tbody>
          <tr><td>CPU 核数</td><td>{{ data.cpu.cores }}</td></tr>
          <tr><td>内存</td><td>{{ bytes(data.memory.total) }}</td></tr>
          <tr><td>系统</td><td>{{ data.os }}</td></tr>
          <tr><td>内核</td><td class="mono">{{ data.kernel }}</td></tr>
          <tr><td>主机名</td><td class="mono">{{ data.hostname }}</td></tr>
        </tbody>
      </table>
    </template>
  </section>
</template>
