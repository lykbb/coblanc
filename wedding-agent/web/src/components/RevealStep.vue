<script setup>
defineProps({ message: String, deliverables: Object })
defineEmits(['restart'])

const LABELS = {
  photo: '高清婚纱照',
  invitation: '请柬主视觉 4:5',
  welcome_poster: '迎宾海报 2:3',
  led_screen: '婚礼大屏 16:9',
  moments: '朋友圈图',
}

const open = (url) => window.open(url, '_blank')
</script>

<template>
  <section class="card reveal">
    <h2>你们的作品完成啦</h2>
    <img :src="deliverables.photo" alt="高清婚纱照" class="reveal-photo" />
    <p class="message">{{ message }}</p>
    <van-cell-group inset class="files">
      <van-cell v-for="(url, key) in deliverables" :key="key" :title="LABELS[key] || key" is-link @click="open(url)" />
    </van-cell-group>
    <van-button block round plain class="secondary" @click="$emit('restart')">再做一组</van-button>
  </section>
</template>
