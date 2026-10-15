<script setup>
import { computed, ref } from 'vue'
import Modal from './Modal.vue'
import { REDO_REASONS } from '../agents.js'
import { MAX_REDO, review, state } from '../store.js'

const reason = ref(state.redoPreset?.reason || 'face')
const note = ref(state.redoPreset?.note || '')
const left = computed(() => Math.max(0, MAX_REDO - state.redoUsed))
const stageName = computed(() => (state.task?.generation?.stage === 'set' ? '这组套图' : '这张样片'))

function submit() {
  review('redo', state.picked, { reason: reason.value, note: note.value.trim() || null })
}
</script>

<template>
  <Modal :title="`${stageName}哪里不满意？`" @close="state.dialog = null">
    <p class="muted">修图师会按你的意见重做{{ stageName }}，还能重做 {{ left }} 次。</p>
    <div class="redo-reasons" role="radiogroup" aria-label="不满意的原因">
      <label v-for="item in REDO_REASONS" :key="item.value" class="redo-reason" :class="{ selected: reason === item.value }">
        <input v-model="reason" type="radio" name="redo-reason" :value="item.value" />
        {{ item.label }}
      </label>
    </div>
    <label class="field">
      <span>具体说说（选填）</span>
      <textarea v-model="note" rows="3" maxlength="200" placeholder="比如：男生的脸不太像，下巴更圆一点"></textarea>
    </label>
    <template #foot>
      <button type="button" class="btn-ghost" @click="state.dialog = null">再想想</button>
      <button type="button" class="btn-primary" :disabled="state.busy || !left || !state.picked" @click="submit">请修图师重做</button>
    </template>
  </Modal>
</template>
