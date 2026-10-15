<script setup>
import { computed } from 'vue'
import Icon from './Icon.vue'
import { AMIE, MATERIAL_LABELS } from '../agents.js'
import { state } from '../store.js'

const d = computed(() => (state.task?.status === 'done' ? state.task.deliverables : null))
const photos = computed(() => d.value?.photos?.length ? d.value.photos : d.value?.photo ? [d.value.photo] : [])
const materials = computed(() => Object.entries(d.value || {}).filter(([key, value]) => key !== 'photos' && key !== 'photo' && typeof value === 'string'))
</script>

<template>
  <section class="page-view">
    <div class="canvas-head">
      <h1>成片交付</h1>
      <p>高清婚纱照和婚礼物料都在这里，点图片可以放大，点下载在新窗口打开原图。</p>
    </div>

    <div v-if="!d" class="empty-state">
      <p>作品完成后会出现在这里。</p>
      <button type="button" class="btn-primary" @click="state.view = 'studio'">回到创作画布</button>
    </div>

    <template v-else>
      <div class="delivery-message">
        <img loading="lazy" decoding="async" :src="AMIE.avatar" alt="" />
        <p><b>Amie 的寄语</b>{{ state.task.message }}</p>
      </div>

      <div class="delivery-grid">
        <button type="button" class="delivery-hero" aria-label="放大主视觉" @click="state.lightbox = d.photo">
          <img loading="lazy" decoding="async" :src="d.photo" alt="主视觉" />
          <span class="tag">主视觉</span>
        </button>
        <div class="delivery-photos">
          <div v-for="(url, i) in photos" :key="url" class="delivery-photo">
            <button type="button" class="thumb-btn" :aria-label="`放大第 ${i + 1} 张`" @click="state.lightbox = url">
              <img loading="lazy" decoding="async" :src="url" :alt="`高清图 ${i + 1}`" />
            </button>
            <a :href="url" target="_blank" rel="noopener" class="link-btn"><Icon name="download" :size="14" />第 {{ i + 1 }} 张</a>
          </div>
        </div>
      </div>

      <h2 class="section-title">婚礼物料</h2>
      <div class="material-list">
        <div v-for="[key, url] in materials" :key="key" class="material-item">
          <button type="button" class="thumb-btn" :aria-label="`放大${MATERIAL_LABELS[key] || key}`" @click="state.lightbox = url">
            <img loading="lazy" decoding="async" :src="url" :alt="MATERIAL_LABELS[key] || key" />
          </button>
          <span>{{ MATERIAL_LABELS[key] || key }}</span>
          <a :href="url" target="_blank" rel="noopener" class="link-btn"><Icon name="download" :size="14" />下载</a>
        </div>
      </div>
    </template>
  </section>
</template>
