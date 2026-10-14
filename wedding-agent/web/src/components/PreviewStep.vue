<script setup>
import { computed, ref } from 'vue'

const props = defineProps({ previews: Array, generation: Object, busy: Boolean })
const emit = defineEmits(['review'])

const REASONS = [
  { value: 'face', label: '脸不像' },
  { value: 'body', label: '身材比例不对' },
  { value: 'hands', label: '手部有问题' },
  { value: 'style', label: '不喜欢这个风格' },
  { value: 'other', label: '其他' },
]

const isSet = computed(() => props.generation?.stage === 'set')
const selected = ref(props.previews.find((p) => p.is_best)?.image_id ?? props.previews[0]?.image_id)
const showRedo = ref(false)
const reason = ref('face')
const note = ref('')

const send = (action) => emit('review', { action, image_id: selected.value })

function redo() {
  showRedo.value = false
  emit('review', { action: 'redo', image_id: selected.value, reason: reason.value, note: note.value.trim() || null })
}
</script>

<template>
  <section class="card">
    <h2>{{ isSet ? '9 张套图出来了' : '样片出来了' }}</h2>
    <p class="hint">
      预览带“小囍预览”水印，支付后解锁高清图和婚礼物料。
      <template v-if="generation">已累计生成 {{ generation.total_images }} 张，本轮耗时 {{ generation.seconds }} 秒。</template>
    </p>

    <div class="grid" :class="{ single: previews.length === 1 }">
      <button
        v-for="(preview, index) in previews"
        :key="preview.image_id"
        type="button"
        class="tile"
        :class="{ selected: preview.image_id === selected }"
        @click="selected = preview.image_id"
      >
        <img :src="preview.url" alt="预览图" />
        <span class="watermark">小囍预览</span>
        <span v-if="preview.is_best" class="badge">修图师推荐</span>
        <div class="meta">
          第 {{ index + 1 }} 张 · {{ preview.image_id }}
        </div>
      </button>
    </div>
    <p class="fine">已选：{{ selected }}</p>

    <div class="actions">
      <template v-if="isSet">
        <van-button type="primary" block :loading="busy" @click="send('confirm')">就要这组，去支付</van-button>
      </template>
      <template v-else>
        <van-button type="primary" block :loading="busy" @click="send('confirm')">就要这张，继续出 9 张套图</van-button>
        <van-button block plain type="primary" :disabled="busy" @click="send('sample_only')">只要这一张，直接去支付</van-button>
      </template>
      <van-button block plain :disabled="busy" @click="showRedo = !showRedo">不满意，重做</van-button>
    </div>

    <div v-if="showRedo" class="redo-form">
      <p class="question-title">哪里不满意？（针对已选的 {{ selected }}）</p>
      <van-radio-group v-model="reason" class="options">
        <van-radio v-for="item in REASONS" :key="item.value" :name="item.value">{{ item.label }}</van-radio>
      </van-radio-group>
      <van-field v-model="note" placeholder="具体说说（选填），比如：男生不太像" class="field" />
      <van-button type="primary" block :disabled="busy" @click="redo">请修图师重做</van-button>
      <p class="fine">每个任务最多重做 2 次。</p>
    </div>
  </section>
</template>
