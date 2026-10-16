<script setup>
import { legendKeys, status } from '../status.js'

defineProps({ keys: { type: Array, required: true } }) // 本页出现过的状态 key
</script>

<template>
  <span class="st-legend"><span v-for="k in legendKeys(keys)" :key="k" :title="status(k).tip"><i :style="{ background: status(k).color }" />{{ status(k).label }}</span></span>
</template>
