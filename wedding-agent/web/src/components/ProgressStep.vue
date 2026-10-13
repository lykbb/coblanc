<script setup>
import { computed } from 'vue'

const props = defineProps({ step: String, text: String })

// 专家接力：按后端返回的 step 点亮对应的人，不调用任何模型
const EXPERTS = [
  { mark: '囍', name: '小囍', steps: ['intake', 'packaging'] },
  { mark: '妆', name: '妆造师', steps: ['styling'] },
  { mark: '摄', name: '摄影师', steps: ['framing'] },
  { mark: '图', name: '生图', steps: ['generating'] },
  { mark: '修', name: '修图师', steps: ['checking', 'retouching'] },
]

const active = computed(() => EXPERTS.findIndex((expert) => expert.steps.includes(props.step)))
const isDone = (index) => (props.step === 'packaging' ? index > 0 : index < active.value)
</script>

<template>
  <section class="card progress">
    <div class="experts">
      <div
        v-for="(expert, index) in EXPERTS"
        :key="expert.name"
        class="expert"
        :class="{ active: index === active, done: isDone(index) }"
      >
        <div class="avatar">{{ expert.mark }}</div>
        <span>{{ expert.name }}</span>
      </div>
    </div>
    <van-loading size="22" vertical class="progress-text">{{ text || '小囍正在接单' }}</van-loading>
  </section>
</template>
