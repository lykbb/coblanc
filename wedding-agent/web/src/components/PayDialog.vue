<script setup>
import { computed } from 'vue'
import Modal from './Modal.vue'
import Icon from './Icon.vue'
import { MATERIAL_LABELS } from '../agents.js'
import { pay, state } from '../store.js'

const isSet = computed(() => state.task?.generation?.stage === 'set')
const materials = computed(() => [...(state.task?.plan?.brief?.materials || ['invitation', 'welcome_poster', 'led_screen']), 'moments'])
</script>

<template>
  <Modal title="解锁高清图和婚礼物料" @close="state.dialog = null">
    <ul class="pay-list">
      <li><Icon name="check" :size="16" />{{ isSet ? '9 张高清婚纱照（去水印）' : '1 张高清婚纱照（去水印）' }}</li>
      <li v-for="key in materials" :key="key"><Icon name="check" :size="16" />{{ MATERIAL_LABELS[key] || key }}</li>
    </ul>
    <p class="pay-note">点击后即可解锁，当前不会扣款。</p>
    <template #foot>
      <button type="button" class="btn-ghost" @click="state.dialog = null">稍后再说</button>
      <button type="button" class="btn-primary" :disabled="state.busy" @click="pay">{{ state.busy ? '处理中…' : '确认并解锁' }}</button>
    </template>
  </Modal>
</template>
