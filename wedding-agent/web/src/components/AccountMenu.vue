<script setup>
// 账号菜单：点用户名展开，退出登录需再确认一次；表单 POST 到 action（服务端清会话后回登录页）
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({ name: { type: String, default: '' }, action: { type: String, required: true }, up: { type: Boolean, default: false } })
const open = ref(false)
const confirming = ref(false)
const root = ref(null)
function toggle() { open.value = !open.value; confirming.value = false }
function outside(e) { if (root.value && !root.value.contains(e.target)) { open.value = false; confirming.value = false } }
function esc(e) { if (e.key === 'Escape') { open.value = false; confirming.value = false } }
onMounted(() => { document.addEventListener('click', outside); document.addEventListener('keydown', esc) })
onBeforeUnmount(() => { document.removeEventListener('click', outside); document.removeEventListener('keydown', esc) })
</script>

<template>
  <div ref="root" class="acct" :class="{ up }">
    <button type="button" class="acct-name" :aria-expanded="open" aria-haspopup="menu" @click="toggle">
      <span class="acct-avatar">{{ (props.name || '我').slice(0, 1).toUpperCase() }}</span><span class="acct-label">{{ props.name || '账号' }}</span>
    </button>
    <div v-if="open" class="acct-menu" role="menu">
      <button v-if="!confirming" type="button" role="menuitem" class="acct-item" @click="confirming = true">退出登录</button>
      <form v-else method="post" :action="action" class="acct-confirm">
        <span>确定退出登录？</span>
        <div><button type="button" class="acct-btn" @click="confirming = false">取消</button><button type="submit" class="acct-btn danger">退出</button></div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.acct { position: relative; }
.acct-name { display: flex; align-items: center; gap: 8px; border: 0; background: transparent; padding: 4px 8px 4px 4px; border-radius: 999px; cursor: pointer; color: inherit; font: inherit; font-size: 13px; }
.acct-name:hover, .acct-name[aria-expanded='true'] { background: #f1f0f5; }
.acct-avatar { width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; background: #f3e2dc; color: #a2533f; font-size: 12px; font-weight: 600; }
.acct-menu { position: absolute; right: 0; top: calc(100% + 6px); min-width: 168px; padding: 6px; background: #fff; border-radius: 12px; box-shadow: 0 8px 28px rgba(30, 20, 40, .14), 0 0 0 1px rgba(0, 0, 0, .05); z-index: 50; }
.acct.up .acct-menu { top: auto; bottom: calc(100% + 6px); left: 0; right: auto; }
.acct-item { width: 100%; text-align: left; border: 0; background: transparent; padding: 8px 10px; border-radius: 8px; cursor: pointer; font: inherit; font-size: 13px; color: inherit; }
.acct-item:hover { background: #f6f4f8; }
.acct-confirm { margin: 0; padding: 6px 4px 2px; display: grid; gap: 8px; font-size: 13px; }
.acct-confirm div { display: flex; gap: 6px; justify-content: flex-end; }
.acct-btn { border: 0; border-radius: 8px; padding: 6px 12px; font: inherit; font-size: 12px; cursor: pointer; background: #f1f0f5; color: inherit; }
.acct-btn.danger { background: #c9533d; color: #fff; }
</style>
