<script setup>
import { computed } from 'vue'

const props = defineProps({ message: String, deliverables: Object })
defineEmits(['restart'])

const LABELS = {
  photo: '高清婚纱照（主图）',
  invitation: '请柬主视觉 4:5',
  welcome_poster: '迎宾海报 2:3',
  led_screen: '婚礼大屏 16:9',
  moments: '朋友圈图',
}
const photos = computed(() => props.deliverables.photos || [])
const materials = computed(() => Object.entries(props.deliverables).filter(([key]) => key !== 'photos' && key !== 'photo'))
</script>

<template>
  <section class="card">
    <h2>你们的作品完成啦</h2>
    <p class="message">{{ message }}</p>

    <h3>高清婚纱照（{{ photos.length || 1 }} 张）</h3>
    <div class="grid" :class="{ single: photos.length <= 1 }">
      <a v-for="(url, i) in photos.length ? photos : [deliverables.photo]" :key="url" :href="url" target="_blank" download class="tile">
        <img :src="url" alt="高清婚纱照" />
        <div class="meta">第 {{ i + 1 }} 张 · 点开 / 下载</div>
      </a>
    </div>

    <h3>婚礼物料</h3>
    <div class="grid">
      <a v-for="[key, url] in materials" :key="key" :href="url" target="_blank" download class="tile">
        <img :src="url" :alt="LABELS[key] || key" />
        <div class="meta">{{ LABELS[key] || key }}</div>
      </a>
    </div>
    <p v-if="!materials.length" class="muted">这次没有选婚礼物料。</p>

    <div class="actions">
      <van-button block plain @click="$emit('restart')">再做一组</van-button>
    </div>
  </section>
</template>
