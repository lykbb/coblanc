<script setup>
import { onMounted, ref } from 'vue'
import PortalShell from '@web/PortalShell.vue'
import ReferenceWall from './components/ReferenceWall.vue'
import { portal } from './api.js'

const holder = ref('')
onMounted(async () => { holder.value = (await portal.status()).holder })
async function logout() {
  await portal.logout().catch(() => {})
  location.reload()
}
</script>

<template>
  <PortalShell brand="GALLERY" :holder="holder" @logout="logout">
    <ReferenceWall />
  </PortalShell>
</template>
