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

<style>
/* 邀请码页（用户站） */
.gate { height: 100%; display: grid; place-items: center; background: var(--bg); }
.gate-card { width: min(320px, 86vw); display: flex; flex-direction: column; align-items: stretch; gap: 14px; }
.gate-brand { font-family: var(--brand); font-size: 26px; letter-spacing: 0.32em; text-align: center; margin-bottom: 18px; }
.gate-input { height: 46px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel); text-align: center; letter-spacing: 0.24em; text-transform: uppercase; font-size: 15px; outline: none; transition: border-color .2s; }
.gate-input:focus { border-color: var(--peach-line); }
.gate-input::placeholder { letter-spacing: 0.1em; color: var(--muted); text-transform: none; }
.gate-btn { height: 44px; border: 0; border-radius: 12px; background: var(--grad-btn); color: var(--btn-ink); cursor: pointer; letter-spacing: 0.2em; }
.gate-btn:disabled { opacity: .5; cursor: default; }
.gate-error { min-height: 18px; margin: 0; text-align: center; color: var(--peach-ink); font-size: 12px; }

</style>
