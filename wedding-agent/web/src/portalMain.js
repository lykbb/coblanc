// 内部站点入口：进入前已由 nginx 把关（图墙只认 IP 白名单；后台另要账号密码登录页），这里直接挂载站点 App。
import { createApp } from 'vue'
import './tokens.css'
import './portal.css'

export function mountPortal(App) {
  createApp(App).mount('#app')
}
