<script setup>
import { computed } from 'vue'
import { STYLE_ART, STYLE_LABELS } from '../agents.js'
import { state } from '../store.js'

const plan = computed(() => state.task?.plan || {})
const groups = computed(() => {
  const photos = plan.value.photos
  const all = photos?.all?.length ? photos.all : state.draft.photos.map((p) => p.preview)
  const refs = [...(plan.value.look?.references || []), ...(plan.value.shot?.references || [])].map((r) => ({ url: r.url, label: r.role }))
  const people = photos?.groom?.length && photos?.bride?.length
    ? [
        { title: '新娘照片', items: photos.bride.map((url) => ({ url })) },
        { title: '新郎照片', items: photos.groom.map((url) => ({ url })) },
      ]
    : [{ title: '你们的照片', items: all.map((url) => ({ url })) }]
  return [...people, { title: '专家选用的参考图', items: refs }]
})
const styles = Object.entries(STYLE_ART).map(([id, url]) => ({ url, label: STYLE_LABELS[id] }))
</script>

<template>
  <section class="page-view">
    <div class="canvas-head">
      <h1>素材库</h1>
      <p>这次创作用到的照片和参考图。</p>
    </div>
    <template v-for="group in groups" :key="group.title">
      <h2 class="section-title">{{ group.title }}</h2>
      <p v-if="!group.items.length" class="muted">暂时还没有</p>
      <div v-else class="library-grid">
        <button v-for="(item, i) in group.items" :key="item.url" type="button" class="thumb-btn" :aria-label="`放大${group.title} ${i + 1}`" @click="state.lightbox = item.url">
          <img :src="item.url" :alt="`${group.title} ${i + 1}`" />
          <span v-if="item.label" class="tag">{{ item.label }}</span>
        </button>
      </div>
    </template>
    <h2 class="section-title">品牌风格板（示意）</h2>
    <div class="library-grid">
      <button v-for="item in styles" :key="item.url" type="button" class="thumb-btn" :aria-label="`放大${item.label}风格板`" @click="state.lightbox = item.url">
        <img :src="item.url" :alt="item.label" />
        <span class="tag">{{ item.label }}</span>
      </button>
    </div>
  </section>
</template>
