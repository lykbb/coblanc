<script setup>
import { ref } from 'vue'

const props = defineProps({ previews: Array, busy: Boolean })
const emit = defineEmits(['review'])

const REASONS = [
  { value: 'face', label: '脸不像' },
  { value: 'body', label: '身材比例不对' },
  { value: 'hands', label: '手部有问题' },
  { value: 'style', label: '不喜欢这个风格' },
  { value: 'other', label: '其他' },
]

const selected = ref(props.previews.find((p) => p.is_best)?.image_id ?? props.previews[0]?.image_id)
const showRedo = ref(false)
const reason = ref('face')
const note = ref('')

function confirm() {
  emit('review', { action: 'confirm', image_id: selected.value })
}

function redo() {
  showRedo.value = false
  emit('review', { action: 'redo', image_id: selected.value, reason: reason.value, note: note.value.trim() || null })
}
</script>

<template>
  <section class="card">
    <h2>挑一张最像你们的</h2>
    <p class="hint">预览带水印，确认后解锁高清图和婚礼物料。</p>
    <div class="previews">
      <button
        v-for="preview in previews"
        :key="preview.image_id"
        type="button"
        class="preview"
        :class="{ selected: preview.image_id === selected }"
        @click="selected = preview.image_id"
      >
        <img :src="preview.url" alt="候选婚纱照" />
        <span class="watermark">小囍预览</span>
        <van-tag v-if="preview.is_best" type="primary" class="best-tag">修图师推荐</van-tag>
      </button>
    </div>
    <van-button type="primary" block round :loading="busy" @click="confirm">就要这张</van-button>
    <van-button block round plain class="secondary" :disabled="busy" @click="showRedo = true">不满意，重做</van-button>

    <van-popup v-model:show="showRedo" position="bottom" round class="redo-popup">
      <h3>哪里不满意？</h3>
      <van-radio-group v-model="reason" class="options">
        <van-radio v-for="item in REASONS" :key="item.value" :name="item.value" class="option">{{ item.label }}</van-radio>
      </van-radio-group>
      <van-field v-model="note" placeholder="具体说说（选填），比如：男生不太像" class="field" />
      <van-button type="primary" block round @click="redo">请修图师重做</van-button>
    </van-popup>
  </section>
</template>
