<script setup>
defineProps({ items: { type: Array, required: true } }) // [[tone, 文字], …]
</script>

<template>
  <span class="st-legend"><span v-for="[tone, label] in items" :key="tone"><i :class="'st-' + tone" />{{ label }}</span></span>
</template>
