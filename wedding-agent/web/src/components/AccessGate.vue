<script setup>
import { ref } from 'vue'
import { redeemInvite } from '../api.js'

const emit = defineEmits(['granted'])
const code = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  if (!code.value.trim() || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await redeemInvite(code.value)
    emit('granted')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="gate">
    <form class="gate-card" @submit.prevent="submit">
      <div class="gate-brand">COBLANC</div>
      <label class="sr-only" for="invite">邀请码</label>
      <input id="invite" v-model="code" class="gate-input" placeholder="邀请码" autocomplete="off" autocapitalize="characters" spellcheck="false" maxlength="32" autofocus />
      <button class="gate-btn" :disabled="busy || !code.trim()">进入</button>
      <p class="gate-error" role="alert">{{ error }}</p>
    </form>
  </main>
</template>
