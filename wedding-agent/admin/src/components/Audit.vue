<script setup>
import { onMounted, ref } from 'vue'
import { auditLog, when } from '../api.js'

const ACTIONS = {
  login: '登录', login_failed: '登录失败', login_locked: '登录锁定', logout: '退出', forbidden: '越权访问', csrf_rejected: '拦截跨站请求',
  codes_created: '生成邀请码', holder_revoked: '作废持有人', device_revoked: '踢掉设备',
  refs_uploaded: '上传参考图', ref_edited: '编辑参考图', ref_deleted: '删除参考图', refs_zipped: '打包下载', refs_exported: '导出元数据', file_viewed: '查看文件', file_downloaded: '下载文件',
  link_added: '添加链接', link_edited: '编辑链接', link_deleted: '删除链接', link_preview_uploaded: '上传链接预览图',
}
const SITES = { admin: '后台', gallery: '图墙' }
const WARN = new Set(['login_failed', 'login_locked', 'forbidden', 'csrf_rejected'])
const items = ref([])
const error = ref('')
onMounted(async () => {
  try {
    items.value = (await auditLog()).items
  } catch (e) {
    error.value = e.message
  }
})
const detail = (d) => Object.entries(d || {}).filter(([, v]) => v !== null && v !== '').map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' ') : v}`).join(' · ')
</script>

<template>
  <section class="portal-page">
    <header class="page-head"><h1>审计</h1><span class="page-count">{{ items.length }}</span></header>
    <p v-if="error" class="page-error" role="alert">{{ error }}</p>
    <table class="data-table">
      <thead><tr><th>时间</th><th>站点</th><th>谁</th><th>操作</th><th>详情</th><th>IP</th></tr></thead>
      <tbody>
        <tr v-for="(e, i) in items" :key="i" :class="{ warn: WARN.has(e.action) }">
          <td class="muted-s">{{ when(e.at) }}</td>
          <td class="muted-s">{{ SITES[e.site] || e.site || '—' }}</td>
          <td>{{ e.holder || '—' }}</td>
          <td>{{ ACTIONS[e.action] || e.action }}</td>
          <td class="muted-s wrap">{{ detail(e.detail) }}</td>
          <td class="mono muted-s">{{ e.ip }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>
