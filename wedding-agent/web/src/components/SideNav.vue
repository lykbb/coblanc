<script setup>
import Icon from './Icon.vue'
import { state } from '../store.js'
import { usingMock } from '../api.js'

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

    <div class="side-user" :title="collapsed ? '演示账号' : undefined">
      <span class="user-dot" aria-hidden="true"><Icon name="user" :size="18" /></span>
      <div class="side-user-text">
        <strong>演示账号</strong>
        <small>{{ usingMock ? '假数据模式' : '已连接后端' }}</small>
      </div>
    </div>
  </aside>
</template>
