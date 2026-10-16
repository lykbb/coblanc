import { createApp, h, ref } from 'vue'
import '@web/tokens.css'
import './admin.css'
import AccessGate from '@web/components/AccessGate.vue'
import App from './App.vue'
import { redeem, status } from './api.js'

const authorized = ref(null)
status()
  .then((s) => (authorized.value = s.authorized))
  .catch(() => (authorized.value = false))

createApp({
  render: () => (authorized.value === null ? null : authorized.value
    ? h(App)
    : h(AccessGate, { redeem, brand: 'COBLANC · ADMIN', onGranted: () => (authorized.value = true) })),
}).mount('#app')
