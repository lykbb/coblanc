<script setup>
defineProps({ task: Object, busy: Boolean })
defineEmits(['pay'])
</script>

<template>
  <section class="card">
    <h2>就差最后一步</h2>
    <p class="hint">
      {{ task.generation?.stage === 'set' ? '解锁 9 张高清婚纱照' : '解锁这张高清婚纱照' }}，以及婚礼物料：请柬主视觉、迎宾海报、婚礼大屏、朋友圈图。
    </p>
    <p class="fine">点击后即可解锁，当前不会扣款。</p>
    <div class="actions">
      <van-button type="primary" block :loading="busy" @click="$emit('pay')">确认并解锁</van-button>
    </div>
  </section>
</template>
