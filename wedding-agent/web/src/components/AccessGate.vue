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
    <div class="gate-media" aria-hidden="true"></div>
    <form class="gate-card" @submit.prevent="submit">
      <div class="gate-brand"><strong>COBLANC</strong><span>共白</span></div>
      <h1 class="gate-title">婚纱照创作工作室</h1>
      <p class="gate-lead">输入邀请码，和 Amie 一起开始你们的婚纱照。</p>
      <label class="sr-only" for="invite">邀请码</label>
      <input id="invite" v-model="code" class="gate-input" :class="{ invalid: error }" placeholder="邀请码" autocomplete="off" autocapitalize="characters" spellcheck="false" maxlength="32" autofocus :aria-invalid="Boolean(error)" aria-describedby="invite-error" @input="error = ''" />
      <button class="gate-btn" :disabled="busy || !code.trim()">{{ busy ? '正在验证…' : '进入' }}</button>
      <p id="invite-error" class="gate-error" role="alert">{{ error }}</p>
    </form>
  </main>
</template>

<style>
/* 邀请码页（用户站）：与落地页同一张主视觉 */
.gate { position: relative; min-height: 100%; height: 100%; display: grid; place-items: center; padding: 24px; background: #332f27; overflow: hidden; isolation: isolate; }
.gate-media { position: absolute; inset: 0; z-index: -1; background: url('/coblanc-film/assets/coblanc-film-hero.webp') 62% center / cover no-repeat; }
.gate-media::after { content: ''; position: absolute; inset: 0; background: linear-gradient(90deg, rgba(14, 24, 24, 0.55), rgba(14, 24, 24, 0.25)), linear-gradient(0deg, rgba(14, 24, 24, 0.4), transparent 50%); }
.gate-card { width: min(380px, 100%); display: flex; flex-direction: column; align-items: stretch; gap: 12px; padding: 34px 30px 22px; border-radius: 24px; background: rgba(251, 247, 238, 0.86); border: 1px solid rgba(255, 255, 255, 0.7); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6), 0 30px 80px rgba(0, 0, 0, 0.25); backdrop-filter: blur(24px) saturate(140%); color: var(--ink); }
.gate-brand { display: flex; align-items: baseline; justify-content: center; gap: 10px; }
.gate-brand strong { font-family: var(--logo, var(--brand)); font-weight: 400; font-size: 22px; letter-spacing: 0.24em; }
.gate-brand span { font-family: var(--serif); font-size: 12px; letter-spacing: 0.35em; color: var(--muted); }
.gate-title { margin: 14px 0 0; text-align: center; font-family: var(--serif); font-weight: 500; font-size: 24px; letter-spacing: 0.08em; }
.gate-lead { margin: 0 0 10px; text-align: center; font-size: 13px; line-height: 1.8; color: var(--muted); }
.gate-input { height: 48px; border: 1px solid var(--line); border-radius: 999px; background: #fff; text-align: center; letter-spacing: 0.24em; text-transform: uppercase; font-size: 15px; outline: none; transition: border-color .2s, box-shadow .2s; }
.gate-input:focus { border-color: var(--coral); box-shadow: 0 0 0 3px rgba(76, 125, 146, 0.15); }
.gate-input.invalid { border-color: #c9533d; }
.gate-input::placeholder { letter-spacing: 0.1em; color: #9b988c; text-transform: none; }
.gate-btn { height: 48px; border: 1px solid var(--ink); border-radius: 999px; background: var(--ink); color: #fbf7ee; font-size: 15px; cursor: pointer; letter-spacing: 0.3em; transition: background .2s, border-color .2s; }
.gate-btn:hover:not(:disabled) { background: var(--coral); border-color: var(--coral); }
.gate-btn:disabled { opacity: .45; cursor: default; }
@media (min-width: 900px) { .gate { place-items: center start; padding-left: clamp(48px, 9vw, 140px); } }
.gate-error { min-height: 20px; margin: 0; text-align: center; color: #a8402c; font-size: 13px; }
</style>
