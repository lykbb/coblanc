<script setup>
import Icon from './Icon.vue'
import { state } from '../store.js'
import { usingMock } from '../api.js'
import { onBeforeUnmount, ref, watch } from 'vue'

const USER_AVATAR = `${import.meta.env.BASE_URL}user-avatar.jpg`
const menu = ref(false)
const confirming = ref(false)
function toggleMenu() { menu.value = !menu.value; confirming.value = false }
// 菜单打开时，点外面任意处或按 Esc 就收起
const wrap = ref(null)
function onDocDown(e) { if (wrap.value && !wrap.value.contains(e.target)) menu.value = false }
function onEsc(e) { if (e.key === 'Escape') menu.value = false }
watch(menu, (open) => {
  const fn = open ? 'addEventListener' : 'removeEventListener'
  document[fn]('pointerdown', onDocDown, true)
  document[fn]('keydown', onEsc)
})
onBeforeUnmount(() => { menu.value = false; document.removeEventListener('pointerdown', onDocDown, true); document.removeEventListener('keydown', onEsc) })

defineProps({
  collapsed: { type: Boolean, default: false },
})

const NAV = [
  { key: 'overview', label: '总览', icon: 'home' },
  { key: 'studio', label: '婚纱照创作', icon: 'spark' },
  { key: 'projects', label: '我的项目', icon: 'folder' },
  { key: 'library', label: '素材库', icon: 'library' },
  { key: 'delivery', label: '成片交付', icon: 'deliver' },
]
</script>

<template>
  <aside class="side" :class="{ 'is-collapsed': collapsed }" :aria-expanded="!collapsed">
    <div class="side-top">
      <div class="brand" title="COBLANC 共白">
        <strong class="brand-mark">C</strong><span class="brand-rest">OBLANC</span><span class="brand-cn">共白</span>
      </div>
    </div>

    <nav class="side-nav" aria-label="主导航">
      <button
        v-for="item in NAV"
        :key="item.key"
        type="button"
        class="nav-item"
        :class="{ active: state.view === item.key }"
        :aria-current="state.view === item.key ? 'page' : undefined"
        :title="collapsed ? item.label : undefined"
        @click="state.view = item.key"
      >
        <Icon class="nav-icon" :name="item.icon" />
        <span class="nav-label">{{ item.label }}</span>
      </button>
    </nav>

    <div ref="wrap" class="side-user-wrap">
      <button type="button" class="side-user" :title="collapsed ? '我的账号' : undefined" :aria-expanded="menu" aria-haspopup="menu" @click="toggleMenu">
        <span class="user-dot has-img" aria-hidden="true"><img :src="USER_AVATAR" alt="" /></span>
        <span class="side-user-text">
          <strong>我的账号</strong>
          <small>{{ usingMock ? '假数据模式' : '已连接后端' }}</small>
        </span>
      </button>
      <div v-if="menu" class="side-user-menu" role="menu">
        <button v-if="!confirming" type="button" role="menuitem" class="side-user-item" @click="confirming = true">退出登录</button>
        <form v-else method="post" action="/logout" class="side-user-confirm">
          <button type="button" class="side-user-btn" @click="menu = false">取消</button>
          <button type="submit" class="side-user-btn danger">退出</button>
        </form>
      </div>
    </div>
  </aside>
</template>
