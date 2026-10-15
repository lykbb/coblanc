<script setup>
import { computed } from 'vue'
import { AMIE, STYLE_ART } from '../agents.js'
import { openProject, phase, restart, state } from '../store.js'

const ASSET = '/coblanc-film/assets/'
const HERO = ASSET + 'coblanc-film-hero.png'
const COUPLE = ASSET + 'coblanc-film-couple.png'

const STATUS = {
  running: '进行中',
  waiting_user: '等你回答',
  preview_ready: '等你确认',
  awaiting_payment: '待支付',
  delivering: '制作物料中',
  done: '已完成',
  failed: '没拍成',
}

const moods = [
  { key: 'chinese_red_gold', label: '东方中式', url: STYLE_ART.chinese_red_gold },
  { key: 'korean_studio', label: '韩式影棚', url: STYLE_ART.korean_studio },
  { key: 'french_editorial', label: '法式杂志', url: STYLE_ART.french_editorial },
  { key: 'cinematic', label: '电影感', url: STYLE_ART.cinematic },
]

const current = computed(() => state.projects.find((p) => p.task_id === state.taskId) || state.projects[0] || null)
const recent = computed(() => state.projects.slice(0, 3))
const hasWork = computed(() => Boolean(state.taskId || current.value))

const phaseLabel = computed(() => {
  const p = phase.value
  if (p === 'start') return '待开始'
  if (p === 'done') return '已完成'
  if (p === 'failed') return '需重试'
  if (p === 'pay') return '待解锁'
  return '创作中'
})

const statusText = computed(() => {
  if (current.value) return STATUS[current.value.status] || current.value.status
  return phaseLabel.value
})

const when = (iso) => {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function goStudio() {
  state.view = 'studio'
}
function goProjects() {
  state.view = 'projects'
}
function startFresh() {
  restart()
  goStudio()
}
function continueCurrent() {
  if (state.taskId) {
    openProject(state.taskId)
    return
  }
  if (current.value) {
    openProject(current.value.task_id)
    return
  }
  startFresh()
}
</script>

<template>
  <section class="page-view overview-home" aria-label="总览首页">
    <div class="home-hero">
      <div class="home-hero-copy">
        <p class="home-eyebrow">COBLANC · 共白</p>
        <h1>为你们，留下<br />刚刚好的那一张。</h1>
        <p class="home-lead">
          Amie 艾蜜协调妆造、摄影与修图，从一张合照开始，完成九张成片与婚礼物料。
          安静、克制，也足够隆重。
        </p>
        <div class="home-cta">
          <button type="button" class="btn-primary home-cta-primary" @click="hasWork ? continueCurrent() : startFresh()">
            {{ hasWork ? '继续创作' : '开始我们的创作' }}
          </button>
          <button v-if="hasWork" type="button" class="btn-ghost" @click="startFresh">新建一组</button>
          <button v-else type="button" class="btn-ghost" @click="goProjects">查看我的项目</button>
        </div>
        <ul class="home-relay" aria-label="创作接力">
          <li>妆造</li>
          <li>摄影</li>
          <li>生成</li>
          <li>审片</li>
        </ul>
      </div>

      <div class="home-hero-visual" aria-hidden="true">
        <div class="home-glow"></div>
        <figure class="home-frame home-frame-main">
          <img :src="HERO" alt="" />
        </figure>
        <figure class="home-frame home-frame-side">
          <img :src="COUPLE" alt="" />
        </figure>
        <figure class="home-amie">
          <img :src="AMIE.avatar" alt="" />
          <figcaption>
            <strong>{{ AMIE.title }}</strong>
            <span>你的创意伙伴</span>
          </figcaption>
        </figure>
      </div>
    </div>

    <div class="home-panels">
      <article class="home-panel home-panel-status">
        <header class="home-panel-head">
          <div>
            <p class="home-kicker">当前状态</p>
            <h2>{{ hasWork ? '进行中的婚纱照' : '还没有开始' }}</h2>
          </div>
          <span class="home-badge" :class="{ idle: !hasWork }">{{ hasWork ? statusText : '欢迎到来' }}</span>
        </header>
        <p v-if="hasWork" class="home-panel-text">
          {{ current ? `项目 ${current.task_id}` : '当前任务' }}
          <template v-if="current?.created_at"> · {{ when(current.created_at) }}</template>
        </p>
        <p v-else class="home-panel-text">上传 2～10 张照片，至少 1 张你们俩的合照，其余单人照也可以。想让宠物一起入镜，记得告诉 Amie。</p>
        <div class="home-panel-actions">
          <button type="button" class="btn-primary small" @click="hasWork ? continueCurrent() : startFresh()">
            {{ hasWork ? '回到创作画布' : '立即开始' }}
          </button>
          <button type="button" class="link-btn" @click="goProjects">全部项目（{{ state.projects.length }}）</button>
        </div>
      </article>

      <article class="home-panel home-panel-entries">
        <p class="home-kicker">工作室入口</p>
        <h2>继续你们的故事</h2>
        <div class="home-entry-grid">
          <button type="button" class="home-entry" @click="goStudio">
            <span class="home-entry-label">婚纱照创作</span>
            <span class="home-entry-desc">画布与专家接力</span>
          </button>
          <button type="button" class="home-entry" @click="goProjects">
            <span class="home-entry-label">我的项目</span>
            <span class="home-entry-desc">{{ state.projects.length }} 组记录</span>
          </button>
          <button type="button" class="home-entry" @click="state.view = 'library'">
            <span class="home-entry-label">素材库</span>
            <span class="home-entry-desc">已上传的照片</span>
          </button>
          <button type="button" class="home-entry" @click="state.view = 'delivery'">
            <span class="home-entry-label">成片交付</span>
            <span class="home-entry-desc">高清图与物料</span>
          </button>
        </div>
      </article>
    </div>

    <section v-if="recent.length" class="home-recent" aria-label="最近项目">
      <header class="home-section-head">
        <div>
          <p class="home-kicker">最近</p>
          <h2>你们留下的片刻</h2>
        </div>
        <button type="button" class="link-btn" @click="goProjects">查看全部</button>
      </header>
      <ul class="home-recent-list">
        <li v-for="p in recent" :key="p.task_id">
          <button type="button" class="home-recent-card" @click="openProject(p.task_id)">
            <div class="home-recent-cover">
              <img v-if="p.cover" :src="p.cover" alt="" />
              <span v-else>COBLANC</span>
            </div>
            <div class="home-recent-meta">
              <strong>婚纱照 · {{ p.task_id }}</strong>
              <span>{{ when(p.created_at) }} · {{ STATUS[p.status] || p.status }}</span>
            </div>
          </button>
        </li>
      </ul>
    </section>

    <section class="home-moods" aria-label="风格印象">
      <header class="home-section-head">
        <div>
          <p class="home-kicker">风格印象</p>
          <h2>静一点，也亮一点</h2>
        </div>
      </header>
      <div class="home-mood-row">
        <figure v-for="mood in moods" :key="mood.key" class="home-mood">
          <img :src="mood.url" :alt="mood.label" />
          <figcaption>{{ mood.label }}</figcaption>
        </figure>
      </div>
    </section>
  </section>
</template>
