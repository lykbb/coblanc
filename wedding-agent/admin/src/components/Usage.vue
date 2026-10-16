<script setup>
import { onMounted, ref, watch } from 'vue'
import { ops } from '../api.js'
import { computed } from 'vue'
import { KINDS, money, num, priceSources, priceTitle } from '../usage.js'
import StatusLegend from './StatusLegend.vue'
import StatusBar from './StatusBar.vue'

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
const showUnused = ref(false)
const used = computed(() => (data.value?.models || []).filter((m) => m.active !== false || m.calls))
const unused = computed(() => (data.value?.models || []).filter((m) => m.active === false && !m.calls))
const importing = ref(false)
const imported = ref('')
async function upload(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  importing.value = true
  error.value = ''
  try {
    const r = await ops.importUsage(file)
    imported.value = `已导入 ${r.rows} 行（${r.days[0]}${r.days.length > 1 ? ' ~ ' + r.days[r.days.length - 1] : ''}）`
    await load()
  } catch (err) { error.value = err.message } finally { importing.value = false }
}
</script>

<template>
  <section class="portal-page">
    <header class="page-head">
      <h1>Token 用量</h1>
      <label class="ghost-btn push file-btn" :class="{ busy: importing }">导入 DeepSeek 账单 CSV<input type="file" accept=".csv,text/csv" hidden @change="upload" /></label>
      <div class="seg">
        <button v-for="p in PERIODS" :key="p.key" type="button" :class="{ on: period === p.key }" @click="period = p.key">{{ p.label }}</button>
      </div>
    </header>
    <p v-if="error" class="page-error" role="alert">{{ error }}</p>
    <p v-if="imported" class="muted-s">{{ imported }}</p>
    <template v-if="data?.total">
      <div class="stat-row">
        <div class="stat-card"><span>调用</span><strong>{{ num(data.total.calls) }}</strong></div>
        <div class="stat-card"><span>输入 token</span><strong>{{ num(data.total.input) }}</strong></div>
        <div class="stat-card"><span>缓存命中</span><strong>{{ num(data.total.cached) }}</strong></div>
        <div class="stat-card"><span>输出 token</span><strong>{{ num(data.total.output) }}</strong></div>
        <div class="stat-card"><span>生图</span><strong>{{ num(data.total.images) }}</strong></div>
        <div class="stat-card"><span>费用</span><strong>{{ money(data.total) }}</strong></div>
      </div>
      <p v-if="data.total.backfilled" class="muted-s">含 {{ data.total.backfilled }} 条回填</p>
      <p v-if="data.imports?.length" class="muted-s">DeepSeek 账单已导入：{{ data.imports.join('、') }}<template v-if="data.total.superseded">；这些日子的合计以账单为准，自记的 {{ data.total.superseded }} 条只计入按步骤、按任务</template></p>

      <h2 class="sub-h">按模型<StatusLegend :keys="[...used.map((m) => (m.active ? 'in_use' : 'history')), ...(unused.length ? ['disabled'] : [])]" /></h2>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>模型</th><th>用途</th><th>步骤</th><th class="right">调用</th><th class="right">输入</th><th class="right">缓存</th><th class="right">输出</th><th class="right">生图</th><th class="right">费用</th></tr></thead>
        <tbody>
          <tr v-for="m in used" :key="m.provider + m.model + m.kind"'>
            <td class="ell" :title="m.provider + ' · ' + m.model"><StatusBar :s="m.active ? 'in_use' : 'history'" /><span class="muted-s">{{ m.provider }} · </span><span class="mono">{{ m.model }}</span></td><td>{{ KINDS[m.kind] || m.kind }}</td>
            <td class="ell" :title="m.step_labels.join('、')">{{ m.step_labels.join('、') || '—' }}</td>
            <td class="right">{{ num(m.calls) }}</td><td class="right">{{ num(m.input) }}</td><td class="right">{{ num(m.cached) }}</td>
            <td class="right">{{ num(m.output) }}</td><td class="right">{{ num(m.images) }}</td>
            <td class="right" :title="priceTitle(m)">{{ money(m) }}</td>
          </tr>
          <tr v-if="unused.length" class="dim clickable" @click="showUnused = !showUnused">
            <td colspan="9">{{ showUnused ? '▾' : '▸' }} 未启用的备用 · {{ unused.length }}</td>
          </tr>
          <template v-if="showUnused">
            <tr v-for="m in unused" :key="'u' + m.provider + m.model + m.kind" class="dim">
              <td class="ell" :title="m.provider + ' · ' + m.model"><StatusBar s="disabled" :detail="m.note || ''" /><span class="muted-s">{{ m.provider }} · </span><span class="mono">{{ m.model }}</span></td><td>{{ KINDS[m.kind] || m.kind }}</td>
              <td class="ell" :title="m.step_labels.join('、') + '\n' + (m.note || '')">{{ m.step_labels.join('、') }}</td>
              <td colspan="5"></td><td class="right muted-s" :title="priceTitle(m)">—</td>
            </tr>
          </template>
        </tbody>
      </table></div>
      <p class="muted-s price-line">单价来源：<template v-for="(p, i) in priceSources(data.models)" :key="p.provider"><span v-if="i"> · </span><a :href="p.source" target="_blank" rel="noopener noreferrer">{{ p.provider }} 官方</a></template> · 版本 {{ data.prices.version }}</p>

      <h2 class="sub-h">按步骤</h2>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>步骤</th><th>模型</th><th class="right">调用</th><th class="right">输入</th><th class="right">缓存</th><th class="right">输出</th><th class="right">生图</th><th class="right">费用</th></tr></thead>
        <tbody>
          <template v-for="s in data.steps" :key="s.step">
            <tr class="group-row"><td>{{ s.label }}</td><td></td><td class="right">{{ num(s.calls) }}</td><td class="right">{{ num(s.input) }}</td><td class="right">{{ num(s.cached) }}</td><td class="right">{{ num(s.output) }}</td><td class="right">{{ num(s.images) }}</td><td class="right">{{ money(s) }}</td></tr>
            <tr v-for="r in data.step_models.filter((r) => r.step === s.step)" :key="s.step + r.provider + r.model + r.kind">
              <td></td><td class="ell" :title="r.model"><span class="mono">{{ r.model }}</span><span class="muted-s"> · {{ KINDS[r.kind] || r.kind }}</span></td><td class="right">{{ num(r.calls) }}</td><td class="right">{{ num(r.input) }}</td><td class="right">{{ num(r.cached) }}</td><td class="right">{{ num(r.output) }}</td><td class="right">{{ num(r.images) }}</td><td class="right" :title="priceTitle(r)">{{ money(r) }}</td>
            </tr>
          </template>
          <tr v-if="!data.steps.length"><td colspan="8" class="muted-s">暂无数据</td></tr>
        </tbody>
      </table></div>

      <h2 class="sub-h">按天</h2>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>日期</th><th class="right">调用</th><th class="right">输入</th><th class="right">缓存</th><th class="right">输出</th><th class="right">生图</th><th class="right">费用</th></tr></thead>
        <tbody>
          <tr v-for="d in data.days" :key="d.day"><td>{{ d.day }}</td><td class="right">{{ num(d.calls) }}</td><td class="right">{{ num(d.input) }}</td><td class="right">{{ num(d.cached) }}</td><td class="right">{{ num(d.output) }}</td><td class="right">{{ num(d.images) }}</td><td class="right">{{ money(d) }}</td></tr>
          <tr v-if="!data.days.length"><td colspan="7" class="muted-s">暂无数据</td></tr>
        </tbody>
      </table></div>

      <h2 class="sub-h">按任务</h2>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>任务</th><th class="right">调用</th><th class="right">输入</th><th class="right">缓存</th><th class="right">输出</th><th class="right">生图</th><th class="right">费用</th></tr></thead>
        <tbody>
          <tr v-for="t in data.tasks" :key="t.task_id"><td class="mono">{{ t.task_id }}</td><td class="right">{{ num(t.calls) }}</td><td class="right">{{ num(t.input) }}</td><td class="right">{{ num(t.cached) }}</td><td class="right">{{ num(t.output) }}</td><td class="right">{{ num(t.images) }}</td><td class="right">{{ money(t) }}</td></tr>
          <tr v-if="!data.tasks.length"><td colspan="7" class="muted-s">暂无数据</td></tr>
        </tbody>
      </table></div>
    </template>
  </section>
</template>
