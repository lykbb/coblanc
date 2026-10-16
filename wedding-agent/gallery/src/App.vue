<script setup>
import { onMounted, ref } from 'vue'
import PortalShell from '@web/PortalShell.vue'
import ReferenceWall from './components/ReferenceWall.vue'
import { portal } from './api.js'

const holder = ref('')
onMounted(async () => { holder.value = (await portal.status()).holder })
</script>

<template>
  <PortalShell brand="GALLERY" :holder="holder">
    <ReferenceWall />
  </PortalShell>
</template>
