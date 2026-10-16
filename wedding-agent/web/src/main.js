import { createApp, h, ref } from 'vue'
import './style.css'
import App from './App.vue'
import AccessGate from './components/AccessGate.vue'
import { accessStatus } from './api.js'

// 先查邀请码状态：未授权只显示邀请码页；后端关掉 ACCESS_INVITE_REQUIRED 时直接进工作台。
const authorized = ref(null)
accessStatus()
  .then((s) => (authorized.value = s.authorized))
  .catch(() => (authorized.value = true)) // 查不到时进工作台，具体错误由工作台的接口提示

createApp({
  render: () => (authorized.value === null ? null : authorized.value ? h(App) : h(AccessGate, { onGranted: () => (authorized.value = true) })),
}).mount('#app')
