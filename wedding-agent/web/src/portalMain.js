// 内部站点入口：先查登录，未登录显示邀请码页，登录后挂载站点 App。
import { createApp, h, ref } from 'vue'
import './tokens.css'
import './portal.css'
import AccessGate from './components/AccessGate.vue'

export function mountPortal(App, portal, brand) {
  const authorized = ref(null)
  portal.status()
    .then((s) => (authorized.value = s.authorized))
    .catch(() => (authorized.value = false))
  createApp({
    render: () => (authorized.value === null ? null : authorized.value
      ? h(App)
      : h(AccessGate, { redeem: portal.redeem, brand, onGranted: () => (authorized.value = true) })),
  }).mount('#app')
}
