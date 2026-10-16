<script setup>
import { onMounted, ref, watch } from 'vue'
import { ops } from '../api.js'
import { KINDS, money, num, price } from '../usage.js'

const PERIODS = [{ key: 'today', label: '今天' }, { key: '7d', label: '7 天' }, { key: '30d', label: '30 天' }]
const period = ref('7d')
const data = ref(null)
const error = ref('')
async function load() {
  error.value = ''
  try { data.value = await ops.usage(period.value) } catch (e) { error.value = e.message }
}
onMounted(load)
watch(period, load)
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
    <template v-if="data?.total">
      <div class="stat-row">
        <div class="stat-card"><span>调用</span><strong>{{ num(data.total.calls) }}</strong></div>
        <div class="stat-card"><span>输入 token</span><strong>{{ num(data.total.input) }}</strong></div>
        <div class="stat-card"><span>缓存命中</span><strong>{{ num(data.total.cached) }}</strong></div>
        <div class="stat-card"><span>输出 token</span><strong>{{ num(data.total.output) }}</strong></div>
        <div class="stat-card"><span>生图</span><strong>{{ num(data.total.images) }}</strong></div>
        <div class="stat-card"><span>费用</span><strong>{{ money(data.total) }}</strong></div>
      </div>
      <p v-if="data.total.backfilled" class="muted-s">含 {{ data.total.backfilled }} 条回填（上线记录前的任务，仅生图张数下限）</p>

      <h2 class="sub-h">按模型</h2>
      <table class="data-table">
        <thead><tr><th>服务</th><th>模型</th><th>用途</th><th>步骤</th><th>状态</th><th>调用</th><th>输入</th><th>缓存</th><th>输出</th><th>生图</th><th>官方单价</th><th>费用</th></tr></thead>
        <tbody>
          <tr v-for="m in data.models" :key="m.provider + m.model + m.kind" :class="{ dim: m.active === false && !m.calls }">
            <td>{{ m.provider }}</td><td class="mono">{{ m.model }}</td><td>{{ KINDS[m.kind] || m.kind }}</td>
            <td>{{ m.step_labels.join('、') || '—' }}</td>
            <td><i class="mark" :class="m.active ? 'good' : 'idle'" />{{ m.active ? '在用' : m.active === false ? '未启用' : '历史' }}</td>
            <td class="right">{{ num(m.calls) }}</td><td class="right">{{ num(m.input) }}</td><td class="right">{{ num(m.cached) }}</td>
            <td class="right">{{ num(m.output) }}</td><td class="right">{{ num(m.images) }}</td>
            <td class="price"><a v-if="m.price" :href="m.price.source" target="_blank" rel="noopener noreferrer">{{ price(m.price) }}</a><span v-else>无</span></td>
            <td class="right">{{ money(m) }}</td>
          </tr>
        </tbody>
      </table>
      <p class="muted-s">单价版本 {{ data.prices.version }} · {{ data.prices.currency }} · {{ data.prices.file }}</p>

      <h2 class="sub-h">按步骤</h2>
      <table class="data-table">
        <thead><tr><th>步骤</th><th>模型</th><th>调用</th><th>输入</th><th>缓存</th><th>输出</th><th>生图</th><th>费用</th></tr></thead>
        <tbody>
          <template v-for="s in data.steps" :key="s.step">
            <tr class="group-row"><td>{{ s.label }}</td><td></td><td class="right">{{ num(s.calls) }}</td><td class="right">{{ num(s.input) }}</td><td class="right">{{ num(s.cached) }}</td><td class="right">{{ num(s.output) }}</td><td class="right">{{ num(s.images) }}</td><td class="right">{{ money(s) }}</td></tr>
            <tr v-for="r in data.step_models.filter((r) => r.step === s.step)" :key="s.step + r.provider + r.model + r.kind">
              <td></td><td class="mono">{{ r.model }} · {{ KINDS[r.kind] || r.kind }}</td><td class="right">{{ num(r.calls) }}</td><td class="right">{{ num(r.input) }}</td><td class="right">{{ num(r.cached) }}</td><td class="right">{{ num(r.output) }}</td><td class="right">{{ num(r.images) }}</td><td class="right">{{ money(r) }}</td>
            </tr>
          </template>
          <tr v-if="!data.steps.length"><td colspan="8" class="muted-s">暂无数据</td></tr>
        </tbody>
      </table>

      <h2 class="sub-h">按天</h2>
      <table class="data-table">
        <thead><tr><th>日期</th><th>调用</th><th>输入</th><th>缓存</th><th>输出</th><th>生图</th><th>费用</th></tr></thead>
        <tbody>
          <tr v-for="d in data.days" :key="d.day"><td>{{ d.day }}</td><td class="right">{{ num(d.calls) }}</td><td class="right">{{ num(d.input) }}</td><td class="right">{{ num(d.cached) }}</td><td class="right">{{ num(d.output) }}</td><td class="right">{{ num(d.images) }}</td><td class="right">{{ money(d) }}</td></tr>
          <tr v-if="!data.days.length"><td colspan="7" class="muted-s">暂无数据</td></tr>
        </tbody>
      </table>

      <h2 class="sub-h">按任务</h2>
      <table class="data-table">
        <thead><tr><th>任务</th><th>调用</th><th>输入</th><th>缓存</th><th>输出</th><th>生图</th><th>费用</th></tr></thead>
        <tbody>
          <tr v-for="t in data.tasks" :key="t.task_id"><td class="mono">{{ t.task_id }}</td><td class="right">{{ num(t.calls) }}</td><td class="right">{{ num(t.input) }}</td><td class="right">{{ num(t.cached) }}</td><td class="right">{{ num(t.output) }}</td><td class="right">{{ num(t.images) }}</td><td class="right">{{ money(t) }}</td></tr>
          <tr v-if="!data.tasks.length"><td colspan="7" class="muted-s">暂无数据</td></tr>
        </tbody>
      </table>
    </template>
  </section>
</template>
