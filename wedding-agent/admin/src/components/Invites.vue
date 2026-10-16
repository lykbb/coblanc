<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { invites, when } from '../api.js'

const data = ref({ codes: [], devices: [], admins: [] })
const error = ref('')
const form = reactive({ names: '', count: '', prefix: '' })
const created = ref([])
const busy = ref(false)

const holders = computed(() => {
  const map = new Map()
  for (const c of data.value.codes) {
    const h = map.get(c.holder) || { holder: c.holder, unused: 0, devices: [] }
    if (!c.used_at) h.unused++
    map.set(c.holder, h)
  }
  for (const d of data.value.devices) {
    const h = map.get(d.holder) || { holder: d.holder, unused: 0, devices: [] }
    h.devices.push(d)
    map.set(d.holder, h)
  }
  return [...map.values()]
})

async function load() {
  try {
    data.value = await invites.list()
    error.value = ''
  } catch (e) {
    error.value = e.message
  }
}
onMounted(load)

async function create() {
  const holdersList = form.names.split(/[\s,，、]+/).filter(Boolean)
  const count = Number(form.count) || 0
  if (!holdersList.length && !count) return
  if (!confirm(`生成 ${holdersList.length + count} 个邀请码？`)) return
  busy.value = true
  try {
    created.value = (await invites.create({ holders: holdersList, count, prefix: form.prefix })).codes
    Object.assign(form, { names: '', count: '', prefix: '' })
    load()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function revokeHolder(holder) {
  if (!confirm(`作废 ${holder} 的所有设备和未用邀请码？`)) return
  await invites.revokeHolder(holder).catch((e) => (error.value = e.message))
  load()
}
async function revokeDevice(d) {
  if (!confirm(`踢掉 ${d.holder} 的这台设备？`)) return
  await invites.revokeDevice(d.id).catch((e) => (error.value = e.message))
  load()
}

function copyAll() {
  navigator.clipboard?.writeText(created.value.map((c) => `${c.holder}\t${c.code}`).join('\n'))
}
function downloadAll() {
  const blob = new Blob(['holder,code\n' + created.value.map((c) => `${c.holder},${c.code}`).join('\n')], { type: 'text/csv' })
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: 'invite-codes.csv' })
  a.click()
  URL.revokeObjectURL(a.href)
}
const short = (ua) => (ua || '').replace(/\(.*?\)/g, '').trim().slice(0, 48) || '—'
</script>

<template>
  <section class="admin-page">
    <header class="page-head"><h1>邀请码</h1><span class="refwall-count">{{ holders.length }}</span></header>

    <form class="inv-form" @submit.prevent="create">
      <input v-model="form.names" class="ref-input" placeholder="持有人（空格或逗号分隔）" />
      <input v-model="form.count" class="ref-input narrow" type="number" min="0" max="1000" placeholder="批量数量" />
      <input v-model="form.prefix" class="ref-input narrow" maxlength="40" placeholder="批量前缀" />
      <button class="primary-btn" :disabled="busy">生成</button>
    </form>

    <div v-if="created.length" class="inv-created">
      <div class="inv-created-head">
        <strong>新邀请码 · 只显示这一次</strong>
        <button type="button" class="ghost-btn" @click="copyAll">复制</button>
        <button type="button" class="ghost-btn" @click="downloadAll">CSV</button>
        <button type="button" class="ghost-btn" @click="created = []">收起</button>
      </div>
      <table class="admin-table"><tbody>
        <tr v-for="c in created" :key="c.code"><td>{{ c.holder }}</td><td class="mono">{{ c.code }}</td></tr>
      </tbody></table>
    </div>

    <p v-if="error" class="refwall-error" role="alert">{{ error }}</p>

    <table class="admin-table">
      <thead><tr><th>持有人</th><th>未用码</th><th>设备</th><th></th></tr></thead>
      <tbody>
        <tr v-for="h in holders" :key="h.holder">
          <td>{{ h.holder }}<span v-if="data.admins.includes(h.holder)" class="tag">管理员</span></td>
          <td>{{ h.unused || '—' }}</td>
          <td>
            <div v-for="d in h.devices" :key="d.id" class="inv-device">
              <span class="tag" v-if="d.kind === 'admin'">后台</span>
              <span class="mono">{{ d.id }}</span>
              <span class="muted-s">{{ when(d.last_seen) }} · {{ d.ip }} · {{ short(d.user_agent) }}</span>
              <button type="button" class="link-s danger" @click="revokeDevice(d)">踢掉</button>
            </div>
            <span v-if="!h.devices.length" class="muted-s">—</span>
          </td>
          <td class="right"><button type="button" class="link-s danger" @click="revokeHolder(h.holder)">作废</button></td>
        </tr>
      </tbody>
    </table>
  </section>
</template>
