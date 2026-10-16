<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { invites, when } from '../api.js'

const data = ref({ codes: [], devices: [], admins: [], members: [], system: [] })
const error = ref('')
const form = reactive({ names: '', count: '', prefix: '' })
const created = ref([])
const busy = ref(false)
const menu = ref('')
const expanded = ref({})
const KIND = { site: '用户站', front: '前台登录', admin: '后台登录' }

const holders = computed(() => {
  const map = new Map()
  const get = (holder) => map.get(holder) || map.set(holder, { holder, unused: 0, codes: 0, devices: [] }).get(holder)
  for (const c of data.value.codes) { const h = get(c.holder); h.codes++; if (!c.used_at) h.unused++ }
  for (const d of data.value.devices) get(d.holder).devices.push(d)
  return [...map.values()].map((h) => {
    const last = h.devices.reduce((a, d) => (!a || d.last_seen > a.last_seen ? d : a), null)
    return { ...h, last, system: data.value.system.includes(h.holder),
             status: h.devices.length ? '有效' : h.unused ? '待使用' : '已失效' }
  }).sort((a, b) => (b.last?.last_seen || 0) - (a.last?.last_seen || 0) || a.holder.localeCompare(b.holder))
})
const team = computed(() => holders.value.filter((h) => !h.system))
const system = computed(() => holders.value.filter((h) => h.system))
const kinds = (h) => [...new Set(h.devices.map((d) => KIND[d.kind] || d.kind))].join(' · ') || (h.unused ? '邀请码' : '—')

async function load() {
  try { data.value = await invites.list(); error.value = '' } catch (e) { error.value = e.message }
}
const closeMenu = () => (menu.value = '')
onMounted(() => { load(); document.addEventListener('click', closeMenu) })
onBeforeUnmount(() => document.removeEventListener('click', closeMenu))

async function generate(holdersList, count = 0, prefix = '') {
  busy.value = true
  try {
    created.value = (await invites.create({ holders: holdersList, count, prefix })).codes
    await load()
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
async function create() {
  const list = form.names.split(/[\s,，、]+/).filter(Boolean)
  const count = Number(form.count) || 0
  if (!list.length && !count) return
  await generate(list, count, form.prefix)
  if (!error.value) Object.assign(form, { names: '', count: '', prefix: '' })
}
async function revokeHolder(h) {
  if (!confirm(`作废 ${h.holder} 的全部设备和未用邀请码？`)) return
  await invites.revokeHolder(h.holder).catch((e) => (error.value = e.message))
  load()
}
async function kickAll(h) {
  if (!confirm(`踢掉 ${h.holder} 的 ${h.devices.length} 台设备？未用邀请码保留。`)) return
  for (const d of h.devices) await invites.revokeDevice(d.id).catch((e) => (error.value = e.message))
  load()
}
async function kick(d) {
  if (!confirm(`踢掉 ${d.holder} 的这台设备？`)) return
  await invites.revokeDevice(d.id).catch((e) => (error.value = e.message))
  load()
}
function copyAll() { navigator.clipboard?.writeText(created.value.map((c) => `${c.holder}\t${c.code}`).join('\n')) }
function downloadAll() {
  const blob = new Blob(['holder,code\n' + created.value.map((c) => `${c.holder},${c.code}`).join('\n')], { type: 'text/csv' })
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: 'invite-codes.csv' })
  a.click()
  URL.revokeObjectURL(a.href)
}
const browser = (ua) => {
  const m = (ua || '').match(/(Edg|Chrome|Firefox|Safari)\/[\d.]+/)
  const os = (ua || '').match(/Mac OS X|Windows|iPhone|iPad|Android|Linux/)
  return [m && m[0].replace(/\.[\d.]+$/, ''), os && os[0].replace('Mac OS X', 'macOS')].filter(Boolean).join(' · ') || (ua || '—').slice(0, 40)
}
</script>

<template>
  <section class="portal-page">
    <header class="page-head"><h1>邀请码</h1><span class="page-count">{{ team.length }}</span></header>

    <form class="inv-form-row" @submit.prevent="create">
      <input v-model="form.names" class="field grow" placeholder="持有人（空格或逗号分隔）" />
      <input v-model="form.count" class="field narrow" type="number" min="0" max="1000" placeholder="批量数量" />
      <input v-model="form.prefix" class="field narrow" maxlength="40" placeholder="批量前缀" />
      <button class="primary-btn" :disabled="busy">生成</button>
    </form>

    <div v-if="created.length" class="inv-created">
      <div class="inv-created-head">
        <strong>新邀请码 · 只显示这一次</strong>
        <button type="button" class="ghost-btn" @click="copyAll">复制</button>
        <button type="button" class="ghost-btn" @click="downloadAll">CSV</button>
        <button type="button" class="ghost-btn" @click="created = []">收起</button>
      </div>
      <table class="data-table"><tbody>
        <tr v-for="c in created" :key="c.code"><td>{{ c.holder }}</td><td class="mono">{{ c.code }}</td></tr>
      </tbody></table>
    </div>

    <p v-if="error" class="page-error" role="alert">{{ error }}</p>

    <template v-for="[title, list] in [['团队成员', team], ['系统账号', system]]" :key="title">
      <h2 v-if="list.length" class="sub-h inv-section">{{ title }} <span class="muted-s">{{ list.length }}</span></h2>
      <div v-if="list.length" class="table-wrap"><table class="data-table inv-table">
        <thead><tr><th>持有人</th><th>类型</th><th class="right">未用码</th><th class="right">设备数</th><th>最近使用</th><th>状态</th><th></th></tr></thead>
        <tbody>
          <template v-for="h in list" :key="h.holder">
            <tr :class="{ dim: h.status === '已失效' }">
              <td>{{ h.holder }}<span v-if="data.admins.includes(h.holder)" class="tag">管理员</span><span v-if="data.members.includes(h.holder)" class="tag">图墙</span></td>
              <td class="muted-s">{{ kinds(h) }}</td>
              <td class="right">{{ h.unused || '—' }}</td>
              <td class="right"><button v-if="h.devices.length" type="button" class="link-s" @click="expanded[h.holder] = !expanded[h.holder]">{{ h.devices.length }} {{ expanded[h.holder] ? '▾' : '▸' }}</button><span v-else>—</span></td>
              <td class="muted-s">{{ h.last ? when(h.last.last_seen) + ' · ' + (h.last.ip || '—') : '—' }}</td>
              <td><i class="mark" :class="h.status === '有效' ? 'good' : h.status === '待使用' ? 'idle' : 'bad'" />{{ h.status }}</td>
              <td class="menu-cell" @click.stop>
                <button type="button" class="dots-btn" :class="{ on: menu === h.holder }" aria-label="操作" @click="menu = menu === h.holder ? '' : h.holder">⋯</button>
                <div v-if="menu === h.holder" class="row-menu" role="menu">
                  <button type="button" :disabled="busy" @click="menu = ''; generate([h.holder])">生成新码</button>
                  <button v-if="h.devices.length" type="button" @click="menu = ''; expanded[h.holder] = true">查看设备</button>
                  <button v-if="h.devices.length" type="button" class="danger" @click="menu = ''; kickAll(h)">踢掉设备</button>
                  <button type="button" class="danger" @click="menu = ''; revokeHolder(h)">作废</button>
                </div>
              </td>
            </tr>
            <tr v-if="expanded[h.holder] && h.devices.length" class="detail">
              <td colspan="7">
                <table class="inv-devices"><tbody>
                  <tr v-for="d in h.devices" :key="d.id">
                    <td class="mono">{{ d.id }}</td><td>{{ KIND[d.kind] || d.kind }}</td>
                    <td class="muted-s">{{ when(d.last_seen) }} · {{ d.ip || '—' }}</td>
                    <td class="ua" :title="d.user_agent">{{ browser(d.user_agent) }}</td>
                    <td class="muted-s">到期 {{ when(d.expires) }}</td>
                    <td class="right"><button type="button" class="link-s danger" @click="kick(d)">踢掉</button></td>
                  </tr>
                </tbody></table>
              </td>
            </tr>
          </template>
        </tbody>
      </table></div>
    </template>
  </section>
</template>
