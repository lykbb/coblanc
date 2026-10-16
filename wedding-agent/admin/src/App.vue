<script setup>
import { onMounted, ref } from 'vue'
import PortalShell from '@web/PortalShell.vue'
import Invites from './components/Invites.vue'
import Overview from './components/Overview.vue'
import Tasks from './components/Tasks.vue'
import Audit from './components/Audit.vue'
import Usage from './components/Usage.vue'
import Server from './components/Server.vue'
import Files from './components/Files.vue'
import { portal } from './api.js'

const SECTIONS = [
  { key: 'overview', label: '概览', icon: 'home', view: Overview },
  { key: 'tasks', label: '任务', icon: 'list', view: Tasks },
  { key: 'usage', label: 'Token 用量', icon: 'gauge', view: Usage },
  { key: 'server', label: '服务器', icon: 'server', view: Server },
  { key: 'files', label: '项目文件', icon: 'file', view: Files },
  { key: 'audit', label: '审计', icon: 'shield', view: Audit },
  { key: 'invites', label: '邀请码', icon: 'key', view: Invites },
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
