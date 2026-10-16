<script setup>
// 标签输入：回车 / 逗号成签，点 × 删除；联想已有标签
import { computed, ref } from 'vue'

const props = defineProps({ modelValue: { type: Array, default: () => [] }, suggestions: { type: Array, default: () => [] } })
const emit = defineEmits(['update:modelValue'])
const text = ref('')
const id = 'tags-' + Math.random().toString(36).slice(2, 8)
const options = computed(() => props.suggestions.filter((t) => !props.modelValue.includes(t)).slice(0, 50))
function commit() {
  const parts = text.value.split(/[,，、\s]+/).map((t) => t.trim().slice(0, 20)).filter(Boolean)
  if (parts.length) emit('update:modelValue', [...new Set([...props.modelValue, ...parts])].slice(0, 12))
  text.value = ''
}
function drop(tag) {
  emit('update:modelValue', props.modelValue.filter((t) => t !== tag))
}
function onKey(e) {
  if (e.key === 'Enter' || e.key === ',' || e.key === '，') { e.preventDefault(); commit() }
  else if (e.key === 'Backspace' && !text.value && props.modelValue.length) drop(props.modelValue.at(-1))
}
</script>

<template>
  <div class="tag-input field">
    <span v-for="t in modelValue" :key="t" class="tag-chip">{{ t }}<button type="button" aria-label="删除标签" @click="drop(t)">×</button></span>
    <input v-model="text" :list="id" placeholder="标签" maxlength="20" @keydown="onKey" @blur="commit" @change="commit" />
    <datalist :id="id"><option v-for="t in options" :key="t" :value="t" /></datalist>
  </div>
</template>
