<script setup>
// 内部站点外框：品牌、栏目（可选）、登录人、退出。
import Icon from './components/Icon.vue'

defineProps({
  brand: { type: String, required: true },
  holder: { type: String, default: '' },
  sections: { type: Array, default: () => [] },
  current: { type: String, default: '' },
})
const emit = defineEmits(['go', 'logout'])
function signOut() {
  if (confirm('退出登录？')) emit('logout')
}
</script>

<template>
  <div class="portal">
    <header class="portal-bar">
      <strong class="portal-brand">COBLANC<span>{{ brand }}</span></strong>
      <nav v-if="sections.length > 1" class="portal-nav">
        <button v-for="s in sections" :key="s.key" type="button" :class="{ on: current === s.key }" @click="emit('go', s)">{{ s.label }}</button>
      </nav>
      <span class="portal-who">{{ holder }}</span>
      <button type="button" class="icon-btn" aria-label="退出" title="退出" @click="signOut"><Icon name="close" :size="16" /></button>
    </header>
    <main class="portal-main"><slot /></main>
  </div>
</template>
