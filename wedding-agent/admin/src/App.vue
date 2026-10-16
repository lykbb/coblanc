<script setup>
import { onMounted, ref } from 'vue'
import Icon from '@web/components/Icon.vue'
import ReferenceWall from './components/ReferenceWall.vue'
import Invites from './components/Invites.vue'
import Tasks from './components/Tasks.vue'
import Audit from './components/Audit.vue'
import { logout, status } from './api.js'

const SECTIONS = [
  { key: 'refs', label: '参考图墙', view: ReferenceWall },
  { key: 'invites', label: '邀请码', view: Invites },
  { key: 'tasks', label: '任务', view: Tasks },
  { key: 'audit', label: '审计', view: Audit },
]
const current = ref(SECTIONS.find((s) => '#' + s.key === location.hash) || SECTIONS[0])
const holder = ref('')
onMounted(async () => { holder.value = (await status()).holder })
function go(section) {
  current.value = section
  history.replaceState(null, '', '#' + section.key)
}
async function signOut() {
  if (!confirm('退出后台？')) return
  await logout().catch(() => {})
  location.reload()
}
</script>

<template>
  <div class="admin">
    <header class="admin-bar">
      <strong class="admin-brand">COBLANC<span>ADMIN</span></strong>
      <nav class="admin-nav">
        <button v-for="s in SECTIONS" :key="s.key" type="button" :class="{ on: current.key === s.key }" @click="go(s)">{{ s.label }}</button>
      </nav>
      <span class="admin-who">{{ holder }}</span>
      <button type="button" class="icon-btn" aria-label="退出" title="退出" @click="signOut"><Icon name="close" :size="16" /></button>
    </header>
    <main class="admin-main"><component :is="current.view" /></main>
  </div>
</template>
