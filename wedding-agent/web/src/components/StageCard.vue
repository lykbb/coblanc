<script setup>
import Icon from './Icon.vue'

defineProps({
  index: { type: Number, required: true },
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  status: { type: String, default: 'todo' }, // done | active | todo | failed
})

const STATUS_TEXT = { done: '已完成', active: '进行中', todo: '未开始', failed: '出了问题' }
</script>

<template>
  <section class="stage-card" :class="status" :aria-label="`${title}，${STATUS_TEXT[status]}`">
    <header class="stage-head">
      <span class="stage-badge" aria-hidden="true">
        <Icon v-if="status === 'done'" name="check" :size="16" />
        <Icon v-else-if="status === 'failed'" name="alert" :size="16" />
        <template v-else>{{ String(index + 1).padStart(2, '0') }}</template>
      </span>
      <div class="stage-titles">
        <h2>{{ title }}</h2>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>
      <span class="stage-status">{{ STATUS_TEXT[status] }}</span>
    </header>
    <div class="stage-body">
      <slot />
    </div>
  </section>
</template>
