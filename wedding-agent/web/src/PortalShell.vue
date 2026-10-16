<script setup>
// 内部站点外框：有栏目时左侧导航（后台），否则顶栏（图墙）；访问人；退出（仅后台：表单 POST 到 <前缀>logout）。
import Icon from './components/Icon.vue'

defineProps({
  brand: { type: String, required: true },
  holder: { type: String, default: '' },
  sections: { type: Array, default: () => [] },
  current: { type: String, default: '' },
  logout: { type: Boolean, default: false },
})
const LOGOUT = import.meta.env.BASE_URL + 'logout'
const emit = defineEmits(['go'])
function confirmOut(e) {
  if (!confirm('退出登录？')) e.preventDefault()
}
</script>

<template>
  <div v-if="sections.length" class="portal portal-side-layout">
    <aside class="portal-side">
      <strong class="portal-brand side-brand">COBLANC<span>{{ brand }}</span></strong>
      <nav class="portal-side-nav">
        <button v-for="s in sections" :key="s.key" type="button" class="portal-nav-item" :class="{ active: current === s.key }" @click="emit('go', s)">
          <Icon :name="s.icon || 'folder'" :size="18" /><span>{{ s.label }}</span>
        </button>
      </nav>
      <div class="portal-side-user">
        <span class="portal-who">{{ holder }}</span>
        <form v-if="logout" method="post" :action="LOGOUT" @submit="confirmOut">
          <button type="submit" class="icon-btn" aria-label="退出" title="退出"><Icon name="close" :size="16" /></button>
        </form>
      </div>
    </aside>
    <main class="portal-main"><slot /></main>
  </div>
  <div v-else class="portal">
    <header class="portal-bar">
      <strong class="portal-brand">COBLANC<span>{{ brand }}</span></strong>
      <span class="portal-who">{{ holder }}</span>
      <form v-if="logout" method="post" :action="LOGOUT" @submit="confirmOut">
        <button type="submit" class="icon-btn" aria-label="退出" title="退出"><Icon name="close" :size="16" /></button>
      </form>
    </header>
    <main class="portal-main"><slot /></main>
  </div>
</template>
