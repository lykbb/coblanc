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
      <p>还没有项目，去创作画布上传照片开始吧。</p>
    </div>

    <ul v-else class="project-list">
      <li v-for="p in state.projects" :key="p.task_id" class="project-item" :class="{ current: p.task_id === state.taskId }">
        <div class="project-cover">
          <img loading="lazy" decoding="async" v-if="p.cover" :src="p.cover" alt="" />
          <span v-else>COBLANC</span>
        </div>
        <div class="project-info">
          <strong>婚纱照创作 · {{ p.task_id }}</strong>
          <span>{{ when(p.created_at) }} 创建 · {{ STATUS[p.status] || p.status }}</span>
        </div>
        <div class="project-actions">
          <button type="button" class="btn-ghost small" @click="openProject(p.task_id)">{{ p.task_id === state.taskId ? '回到画布' : '打开' }}</button>
          <button type="button" class="link-btn" @click="removeProject(p.task_id)">移除</button>
        </div>
      </li>
    </ul>
  </section>
</template>
