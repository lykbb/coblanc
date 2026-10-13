<script setup>
defineProps({ busy: Boolean })
defineEmits(['pay'])
</script>

<template>
  <section class="card">
    <h2>就差最后一步</h2>
    <p class="hint">解锁高清婚纱照和婚礼物料：请柬主视觉、迎宾海报、婚礼大屏，再送一张朋友圈图。</p>
    <p class="fine">演示版：模拟支付，不会真的扣款。</p>
    <van-button type="primary" block round :loading="busy" @click="$emit('pay')">模拟支付并解锁</van-button>
  </section>
</template>
