<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import PortalShell from '@web/PortalShell.vue'
import Invites from './components/Invites.vue'
import Overview from './components/Overview.vue'
import Tasks from './components/Tasks.vue'
import Audit from './components/Audit.vue'
import Usage from './components/Usage.vue'
import Server from './components/Server.vue'
import Files from './components/Files.vue'
import Outputs from './components/Outputs.vue'
import { portal } from './api.js'

const SECTIONS = [
  { key: 'overview', label: '概览', icon: 'home', view: Overview },
  { key: 'tasks', label: '任务', icon: 'list', view: Tasks },
  { key: 'usage', label: 'Token 用量', icon: 'gauge', view: Usage },
  { key: 'server', label: '服务器', icon: 'server', view: Server },
  { key: 'files', label: '项目文件', icon: 'file', view: Files },
  { key: 'outputs', label: '生成记录', icon: 'wall', view: Outputs },
  { key: 'audit', label: '审计', icon: 'shield', view: Audit },
  { key: 'invites', label: '邀请码', icon: 'key', view: Invites },
]
// 地址 #栏目 或 #栏目/任务号（任务详情 ⇄ 生成记录互相跳转用）
const parse = () => location.hash.slice(1).split('/')
const current = ref(SECTIONS.find((s) => s.key === parse()[0]) || SECTIONS[0])
const target = ref(parse()[1] || '')
const holder = ref('')
function sync() {
  const [key, arg] = parse()
  current.value = SECTIONS.find((s) => s.key === key) || SECTIONS[0]
  target.value = arg || ''
}
onMounted(async () => {
  window.addEventListener('hashchange', sync)
  holder.value = (await portal.status()).holder
})
onUnmounted(() => window.removeEventListener('hashchange', sync))
function go(section) {
  current.value = section
  target.value = ''
  history.replaceState(null, '', '#' + section.key)
}
</script>

<template>
  <PortalShell brand="ADMIN" :holder="holder" :sections="SECTIONS" :current="current.key" @go="go" logout>
    <component :is="current.view" :key="current.key" :target="target" />
  </PortalShell>
</template>
