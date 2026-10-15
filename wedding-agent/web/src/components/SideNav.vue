<script setup>
import Icon from './Icon.vue'
import { state } from '../store.js'
import { usingMock } from '../api.js'

const NAV = [
  { key: 'overview', label: '总览', icon: 'home', href: '/coblanc-film/' },
  { key: 'studio', label: '婚纱照创作', icon: 'spark' },
  { key: 'projects', label: '我的项目', icon: 'folder' },
  { key: 'library', label: '素材库', icon: 'library' },
  { key: 'delivery', label: '成片交付', icon: 'deliver' },
]
</script>

<template>
  <aside class="side">
    <div class="brand"><strong>COBLANC</strong><span>共白</span></div>
    <nav class="side-nav" aria-label="主导航">
      <template v-for="item in NAV" :key="item.key">
        <a v-if="item.href" class="nav-item" :href="item.href"><Icon :name="item.icon" />{{ item.label }}</a>
        <button
          v-else
          type="button"
          class="nav-item"
          :class="{ active: state.view === item.key }"
          :aria-current="state.view === item.key ? 'page' : undefined"
          @click="state.view = item.key"
        >
          <Icon :name="item.icon" />{{ item.label }}
        </button>
      </template>
    </nav>
    <div class="side-user">
      <span class="user-dot" aria-hidden="true"><Icon name="user" :size="18" /></span>
      <div class="side-user-text">
        <strong>演示账号</strong>
        <small>{{ usingMock ? '假数据模式' : '已连接后端' }}</small>
      </div>
    </div>
  </aside>
</template>
