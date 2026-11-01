<script setup>
import { openProject, removeProject, restart, state } from '../store.js'

const STATUS = {
  running: '进行中',
  waiting_user: '等你回答',
  preview_ready: '等你确认',
  awaiting_payment: '待支付',
  delivering: '制作物料中',
  done: '已完成',
  failed: '没拍成',
}

const when = (iso) => new Date(iso).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })

function newProject() {
  restart()
}

// 只是从这台电脑的列表里移除，先确认一下，避免误点
function remove(p) {
  if (window.confirm('从「我的项目」里移除这一组？移除后在这台电脑上就找不到它了。')) removeProject(p.task_id)
}
</script>

<template>
  <section class="page-view">
    <div class="canvas-head row">
      <div>
        <h1>我的项目</h1>
        <p>只记在这台电脑的浏览器里。服务重启后，旧任务可能会打不开。</p>
      </div>
      <button type="button" class="btn-primary" @click="newProject">新建创作</button>
    </div>

    <div v-if="!state.projects.length" class="empty-state">
      <span class="empty-mark" aria-hidden="true">C.</span>
      <p class="empty-title">还没有项目</p>
      <p>上传你们的照片，Amie 会带着妆造师、摄影师一起开始。</p>
      <button type="button" class="btn-primary" @click="newProject">开始创作</button>
    </div>

    <ul v-else class="project-list">
      <li v-for="p in state.projects" :key="p.task_id" class="project-item" :class="{ current: p.task_id === state.taskId }">
        <div class="project-cover">
          <img loading="lazy" decoding="async" v-if="p.cover" :src="p.cover" alt="" />
          <span v-else>COBLANC</span>
        </div>
        <div class="project-info">
          <strong>婚纱照 · {{ when(p.created_at) }}</strong>
          <span><i class="status-dot" :class="p.status" aria-hidden="true"></i>{{ STATUS[p.status] || p.status }}</span>
          <small class="project-id">{{ p.task_id }}</small>
        </div>
        <div class="project-actions">
          <button type="button" class="btn-ghost small" @click="openProject(p.task_id)">{{ p.task_id === state.taskId ? '回到画布' : '打开' }}</button>
          <button type="button" class="link-btn muted-link" @click="remove(p)">移除</button>
        </div>
      </li>
    </ul>
  </section>
</template>
