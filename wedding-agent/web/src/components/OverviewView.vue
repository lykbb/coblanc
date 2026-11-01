<script setup>
import { computed } from 'vue'
import { AMIE, STYLE_ART } from '../agents.js'
import { openProject, phase, restart, state } from '../store.js'

const ASSET = '/coblanc-film/assets/'
const HERO = ASSET + 'coblanc-film-hero.webp'

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
      <div class="home-hero-media" aria-hidden="true" :style="{ backgroundImage: `url(${HERO})` }"></div>
      <div class="home-hero-copy">
        <p class="home-eyebrow">COBLANC · 共白</p>
        <h1>为你们，留下<br />刚刚好的那一张。</h1>
        <p class="home-lead">
          Amie 艾蜜协调妆造、摄影与修图，从你们的照片开始，完成九张成片与婚礼物料。安静、克制，也足够隆重。
        </p>
        <div class="home-cta">
          <button type="button" class="btn-primary home-cta-primary" @click="hasWork ? continueCurrent() : startFresh()">
            {{ hasWork ? '继续创作' : '开始我们的创作' }}<span class="arrow" aria-hidden="true">→</span>
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
      <figure class="home-amie" aria-hidden="true">
        <img loading="lazy" decoding="async" :src="AMIE.avatar" alt="" />
        <figcaption>
          <strong>{{ AMIE.title }}</strong>
          <span><i class="online-dot"></i>你的创意伙伴 · 在线</span>
        </figcaption>
      </figure>
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
        <div v-if="hasWork" class="home-current">
          <div class="home-recent-cover">
            <img v-if="current?.cover" loading="lazy" decoding="async" :src="current.cover" alt="" />
            <span v-else>COBLANC</span>
          </div>
          <p class="home-panel-text">
            {{ current?.created_at ? `${when(current.created_at)} 开始` : '当前这一组' }}<br />
            <small>回到画布就能接着上次的进度。</small>
          </p>
        </div>
        <p v-else class="home-panel-text">上传 2～10 张照片，新郎新娘都要有，合照单人照都行。想让宠物一起入镜，也记得说一声。</p>
        <div class="home-panel-actions">
          <button type="button" class="btn-primary small" @click="hasWork ? continueCurrent() : startFresh()">
            {{ hasWork ? '回到创作画布' : '立即开始' }}
          </button>
          <button type="button" class="link-btn" @click="goProjects">全部项目（{{ state.projects.length }}）</button>
        </div>
      </article>

      <article class="home-panel home-panel-steps">
        <p class="home-kicker">怎么拍</p>
        <h2>三步，交给 Amie</h2>
        <ol class="home-steps">
          <li>
            <span class="home-step-num">01</span>
            <div><strong>发几张照片</strong><p>合照、单人照都可以，越清晰越像你们。</p></div>
          </li>
          <li>
            <span class="home-step-num">02</span>
            <div><strong>选风格，看样片</strong><p>妆造师、摄影师各问几个问题，先出 1 张样片给你们确认。</p></div>
          </li>
          <li>
            <span class="home-step-num">03</span>
            <div><strong>九张成片与物料</strong><p>方向对了再拍全套，附请柬、迎宾海报和婚礼大屏。</p></div>
          </li>
        </ol>
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
              <img loading="lazy" decoding="async" v-if="p.cover" :src="p.cover" alt="" />
              <span v-else>COBLANC</span>
            </div>
            <div class="home-recent-meta">
              <strong>{{ when(p.created_at) || '婚纱照' }}</strong>
              <span>{{ STATUS[p.status] || p.status }}</span>
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
          <img loading="lazy" decoding="async" :src="mood.url" :alt="mood.label" />
          <figcaption>{{ mood.label }}</figcaption>
        </figure>
      </div>
    </section>
  </section>
</template>
