<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import Icon from './Icon.vue'
import { state } from '../store.js'

const close = () => { state.lightbox = null }
const onKey = (event) => { if (event.key === 'Escape') close() }
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="lightbox" role="dialog" aria-modal="true" aria-label="查看大图" @click.self="close">
    <img :src="state.lightbox" alt="大图" />
    <button type="button" class="icon-btn light" aria-label="关闭大图" @click="close"><Icon name="close" /></button>
  </div>
</template>
