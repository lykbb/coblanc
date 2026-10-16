<script setup>
// 内部站点外框：有栏目时左侧导航（后台），否则顶栏（图墙）；访问人；账号菜单里退出（仅后台：确认后表单 POST 到 <前缀>logout）。
import AccountMenu from './components/AccountMenu.vue'
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
        <AccountMenu v-if="logout" :name="holder" :action="LOGOUT" up />
        <span v-else class="portal-who">{{ holder }}</span>
      </div>
    </aside>
    <main class="portal-main"><slot /></main>
  </div>
  <div v-else class="portal">
    <header class="portal-bar">
      <strong class="portal-brand">COBLANC<span>{{ brand }}</span></strong>
      <AccountMenu v-if="logout" class="portal-who" :name="holder" :action="LOGOUT" />
      <span v-else class="portal-who">{{ holder }}</span>
    </header>
    <main class="portal-main"><slot /></main>
  </div>
</template>
