<script setup>
import { computed, onMounted, ref } from 'vue'
import { auditLog } from '../api.js'
import StatusLegend from './StatusLegend.vue'
import StatusBar from './StatusBar.vue'
import { SITES, TYPES, avatar, category, clock, dayKey, dayLabel, device, group, inferred, auditKind, relative, sentence, who } from '../audit.js'

const TABS = [['all', '全部'], ['front', '前台'], ['gallery', '图墙'], ['admin', '后台'], ['security', '安全异常']]
const items = ref([])
const system = ref(new Set())
const error = ref('')
const loading = ref(true)
const tab = ref('all')
const person = ref('')
const type = ref('')
const day = ref('')
const q = ref('')
const open = ref(new Set())

onMounted(async () => {
  try {
    const data = await auditLog()
    items.value = data.items
    system.value = new Set(data.system_holders || [])
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

const startOfToday = () => new Date(new Date().toDateString()).getTime() / 1000
const today = computed(() => items.value.filter((e) => e.at >= startOfToday()))
const summary = computed(() => {
  const t = today.value
  const people = [...new Set(t.filter((e) => category(e) !== 'security').map(who).filter((p) => p && !system.value.has(p)))]
  const visits = Object.fromEntries(Object.keys(SITES).map((s) => [s, t.filter((e) => e.action === 'visit' && e.site === s).length]))
  return {
    people,
    visits,
    uploads: t.filter((e) => e.action === 'refs_uploaded').reduce((s, e) => s + (e.detail?.ids || []).length, 0),
    tasks: t.filter((e) => e.action === 'task_created').length,
    anomalies: t.filter((e) => category(e) === 'security').length,
  }
})

const people = computed(() => [...new Set(items.value.map(who).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh')))
const types = computed(() => [...new Set(items.value.map((e) => e.action))].sort((a, b) => (TYPES[a] || a).localeCompare(TYPES[b] || b, 'zh')))
const counts = computed(() => {
  const c = { all: items.value.length, front: 0, gallery: 0, admin: 0, security: 0 }
  for (const e of items.value) c[category(e)] = (c[category(e)] || 0) + 1
  return c
})

const filtered = computed(() => {
  const needle = q.value.trim().toLowerCase()
  return items.value.filter((e) => (tab.value === 'all' || category(e) === tab.value)
    && (!person.value || who(e) === person.value)
    && (!type.value || e.action === type.value)
    && (!day.value || dayKey(e.at) === dayKey(new Date(day.value + 'T00:00').getTime() / 1000))
    && (!needle || [sentence({ ...e, parts: [e] }), e.ip, e.holder, e.user, e.ua, JSON.stringify(e.detail)].join(' ').toLowerCase().includes(needle)))
})

const days = computed(() => {
  const out = []
  for (const g of group(filtered.value)) {
    const key = dayKey(g.at)
    if (!out.length || out[out.length - 1].key !== key) out.push({ key, label: dayLabel(g.at), groups: [] })
    out[out.length - 1].groups.push(g)
  }
  return out
})

const gid = (g) => `${g.at}-${g.action}-${g.ip}`
function toggle(g) {
  const s = new Set(open.value)
  s.has(gid(g)) ? s.delete(gid(g)) : s.add(gid(g))
  open.value = s
}
const raw = (e) => Object.entries({ 时间: new Date(e.at * 1000).toLocaleString('zh-CN', { hour12: false }), 账号: e.holder, 成员: e.user, IP: e.ip, UA: e.ua, ...(e.detail || {}) })
  .filter(([, v]) => v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && !v.length))
  .map(([k, v]) => [k, Array.isArray(v) ? v.join(' ') : typeof v === 'object' ? JSON.stringify(v) : String(v)])
const clear = () => { person.value = ''; type.value = ''; day.value = ''; q.value = '' }
</script>

<template>
  <section class="portal-page audit-page">
    <header class="page-head"><h1>审计</h1></header>
    <p v-if="error" class="page-error" role="alert">{{ error }}</p>

    <div class="audit-summary">
      <div class="audit-sum-card wide">
        <span>今日活跃</span>
        <div class="audit-people">
          <i v-for="p in summary.people" :key="p" class="avatar" :style="{ background: avatar(p).color }" :title="p">{{ avatar(p).text }}</i>
          <em v-if="!summary.people.length" class="muted-s">—</em>
          <b v-else>{{ summary.people.length }} 人</b>
        </div>
      </div>
      <div class="audit-sum-card"><span>访问</span><div class="audit-visits"><span v-for="(label, s) in SITES" :key="s"><em>{{ label }}</em><b>{{ summary.visits[s] }}</b></span></div></div>
      <div class="audit-sum-card"><span>上传参考图</span><b>{{ summary.uploads }} 张</b></div>
      <div class="audit-sum-card"><span>新任务</span><b>{{ summary.tasks }}</b></div>
      <div class="audit-sum-card" :class="{ alert: summary.anomalies }"><span>安全异常</span><b>{{ summary.anomalies }}</b></div>
    </div>

    <div class="audit-bar">
      <div class="seg">
        <button v-for="[key, label] in TABS" :key="key" :class="{ on: tab === key }" @click="tab = key">{{ label }}<i class="seg-count">{{ counts[key] || 0 }}</i></button>
      </div>
    </div>
    <div class="filters audit-filters">
      <select v-model="person"><option value="">所有人</option><option v-for="p in people" :key="p" :value="p">{{ p }}</option></select>
      <select v-model="type"><option value="">所有动作</option><option v-for="t in types" :key="t" :value="t">{{ TYPES[t] || t }}</option></select>
      <input v-model="day" type="date" />
      <input v-model="q" type="search" placeholder="搜索 IP、任务、文件…" class="grow" />
      <button v-if="person || type || day || q" class="link-btn" @click="clear">清除</button>
      <StatusLegend :keys="filtered.map(auditKind)" />
    </div>

    <p v-if="loading" class="empty-s">加载中…</p>
    <p v-else-if="!days.length" class="empty-s">没有记录</p>
    <div v-for="d in days" :key="d.key" class="audit-day">
      <h3 class="audit-day-h">{{ d.label }}<span>{{ d.groups.length }}</span></h3>
      <ol class="audit-list">
        <li v-for="g in d.groups" :key="gid(g)" class="audit-item" :class="[{ sec: category(g) === 'security', open: open.has(gid(g)) }]" @click="toggle(g)">
          <StatusBar :s="auditKind(g)" />
          <i class="avatar" :class="{ anon: !who(g) }" :style="{ background: who(g) ? avatar(who(g)).color : null }">{{ who(g) ? avatar(who(g)).text : (category(g) === 'security' ? '!' : '?') }}</i>
          <div class="audit-body">
            <p class="audit-line">{{ sentence(g) }}</p>
            <p class="audit-meta">
              <span v-if="g.site" class="site-chip" :class="g.site">{{ SITES[g.site] }}</span>
              <span v-if="inferred(g)" class="tag soft" title="按 IP 对应的成员推断">推断</span>
              <span v-if="g.backfilled" class="tag soft" title="从 nginx / fail2ban 日志或任务轨迹回填">回填</span>
              <span v-if="device(g.ua)">{{ device(g.ua) }}</span>
              <span v-if="g.ip" class="mono">{{ g.ip }}</span>
            </p>
            <div v-if="open.has(gid(g))" class="audit-raw" @click.stop>
              <dl v-for="(e, i) in g.parts" :key="i"><template v-for="[k, v] in raw(e)" :key="k"><dt>{{ k }}</dt><dd class="mono">{{ v }}</dd></template></dl>
            </div>
          </div>
          <time class="audit-time" :title="new Date(g.at * 1000).toLocaleString('zh-CN', { hour12: false })">
            <b>{{ g.parts.length > 1 ? clock(g.first) + '–' + clock(g.at) : clock(g.at) }}</b><span>{{ relative(g.at) }}</span>
          </time>
        </li>
      </ol>
    </div>
  </section>
</template>
