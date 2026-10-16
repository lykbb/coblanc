<script setup>
// 行左侧的细状态条：可悬停 / 聚焦（热区比条宽），提示状态名、解释和补充（如失败原因）。
import { computed, ref } from 'vue'
import { status } from '../status.js'

const props = defineProps({ s: { type: String, required: true }, detail: { type: String, default: '' } })
const info = computed(() => status(props.s))
const label = computed(() => [info.value.label, info.value.tip, props.detail].filter(Boolean).join('：'))
const tip = ref(null)
function show(e) {
  const r = e.currentTarget.getBoundingClientRect()
  tip.value = { left: r.right + 6, top: r.top + r.height / 2 }
}
</script>

<template>
  <span class="st-mark" :style="{ '--st': info.color }" role="img" tabindex="0" :aria-label="label"
        @mouseenter="show" @focus="show" @mouseleave="tip = null" @blur="tip = null" @click.stop />
  <Teleport v-if="tip" to="body">
    <div class="st-tip" :style="{ left: tip.left + 'px', top: tip.top + 'px', '--st': info.color }" role="tooltip">
      <b>{{ info.label }}</b><span v-if="info.tip">{{ info.tip }}</span><em v-if="detail">{{ detail }}</em>
    </div>
  </Teleport>
</template>
