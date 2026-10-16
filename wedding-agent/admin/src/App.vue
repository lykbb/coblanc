<script setup>
import { onMounted, ref } from 'vue'
import PortalShell from '@web/PortalShell.vue'
import Invites from './components/Invites.vue'
import Tasks from './components/Tasks.vue'
import Audit from './components/Audit.vue'
import { portal } from './api.js'

const SECTIONS = [
  { key: 'invites', label: '邀请码', view: Invites },
  { key: 'tasks', label: '任务', view: Tasks },
  { key: 'audit', label: '审计', view: Audit },
]
const current = ref(SECTIONS.find((s) => '#' + s.key === location.hash) || SECTIONS[0])
const holder = ref('')
onMounted(async () => { holder.value = (await portal.status()).holder })
function go(section) {
  current.value = section
  history.replaceState(null, '', '#' + section.key)
}
</script>

<template>
  <PortalShell brand="ADMIN" :holder="holder" :sections="SECTIONS" :current="current.key" @go="go" logout>
    <component :is="current.view" />
  </PortalShell>
</template>
