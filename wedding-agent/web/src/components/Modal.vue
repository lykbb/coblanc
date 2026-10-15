<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import Icon from './Icon.vue'

const props = defineProps({ title: { type: String, required: true }, wide: Boolean })
const emit = defineEmits(['close'])
const box = ref(null)

function onKey(event) {
  if (event.key === 'Escape') emit('close')
}

onMounted(async () => {
  document.addEventListener('keydown', onKey)
  await nextTick()
  box.value?.querySelector('button, input, textarea, [tabindex]')?.focus()
})
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div ref="box" class="modal" :class="{ wide: props.wide }" role="dialog" aria-modal="true" :aria-label="props.title">
      <header class="modal-head">
        <slot name="head"><h2>{{ props.title }}</h2></slot>
        <button type="button" class="icon-btn" aria-label="关闭" @click="emit('close')"><Icon name="close" /></button>
      </header>
      <div class="modal-body"><slot /></div>
      <footer v-if="$slots.foot" class="modal-foot"><slot name="foot" /></footer>
    </div>
  </div>
</template>
