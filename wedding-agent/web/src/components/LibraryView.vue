<script setup>
import { computed } from 'vue'
import { STYLE_ART, STYLE_LABELS } from '../agents.js'
import { state } from '../store.js'

const ASSET = '/coblanc-film/assets/'
const LIB = ASSET + 'library/'

// 每张图整页只用一次
const BRAND = [
  { url: ASSET + 'coblanc-film-hero.png', label: '主视觉' },
  { url: ASSET + 'coblanc-film-couple.png', label: '合照印象' },
  { url: ASSET + 'film-style-board.png', label: '胶片风格板' },
  { url: ASSET + 'studio-framework.png', label: '工作台示意' },
  { url: ASSET + 'amie-portrait.png', label: 'Amie 形象' },
]

const STYLE_TILES = [
  { url: STYLE_ART.chinese_red_gold, label: STYLE_LABELS.chinese_red_gold },
  { url: STYLE_ART.korean_studio, label: STYLE_LABELS.korean_studio },
  { url: STYLE_ART.french_editorial, label: STYLE_LABELS.french_editorial },
  { url: STYLE_ART.cinematic, label: STYLE_LABELS.cinematic },
  { url: STYLE_ART.retro, label: STYLE_LABELS.retro },
  { url: ASSET + 'style-minimal.png', label: '极简清透' },
]

const MOOD_LABELS = [
  '晨光', '薄雾', '暖桃', '丁香', '奶油', '松青',
  '腮红', '雾蓝', '香槟', '灰紫', '鼠尾草', '绯红',
  '浅芋', '亚麻', '湖光', '蜜杏', '鸢尾', '青瓷',
]
const MOODS = MOOD_LABELS.map((label, i) => ({
  url: `${LIB}mood-${String(i + 1).padStart(2, '0')}.png`,
  label,
}))

const userItems = computed(() => {
  const photos = state.task?.plan?.photos
  if (photos?.groom?.length && photos?.bride?.length) {
    return [
      ...photos.bride.map((url, i) => ({ url, label: `新娘 ${i + 1}` })),
      ...photos.groom.map((url, i) => ({ url, label: `新郎 ${i + 1}` })),
    ]
  }
  const all = photos?.all?.length ? photos.all : state.draft.photos.map((p) => p.preview)
  return all.map((url, i) => ({ url, label: `上传 ${i + 1}` }))
})

const refItems = computed(() => {
  const plan = state.task?.plan || {}
  const refs = [...(plan.look?.references || []), ...(plan.shot?.references || [])]
  const used = new Set(userItems.value.map((i) => i.url))
  const out = []
  for (const r of refs) {
    if (!r?.url || used.has(r.url)) continue
    used.add(r.url)
    out.push({ url: r.url, label: r.role || '参考' })
  }
  return out
})

const sections = computed(() => {
  const used = new Set()
  const take = (list) => {
    const items = []
    for (const item of list) {
      if (!item?.url || used.has(item.url)) continue
      used.add(item.url)
      items.push(item)
    }
    return items
  }
  return [
    { key: 'user', title: '你们的照片', hint: '本次上传或已分组的参考照', items: take(userItems.value), empty: '还没有上传。去创作页发给 Amie 即可。' },
    { key: 'refs', title: '专家参考', hint: '妆造与摄影选用的参考图', items: take(refItems.value), empty: '方案确认后，参考图会出现在这里。' },
    { key: 'brand', title: '品牌视觉', hint: 'COBLANC 示意资产，每张各用一次', items: take(BRAND) },
    { key: 'style', title: '风格板', hint: '东方、韩式、法式与电影感等方向', items: take(STYLE_TILES) },
    { key: 'mood', title: '色与光', hint: '柔和氛围板，演示填充用', items: take(MOODS) },
  ]
})

const total = computed(() => sections.value.reduce((n, s) => n + s.items.length, 0))
</script>

<template>
  <section class="page-view library-page" aria-label="素材库">
    <header class="library-hero">
      <p class="library-eyebrow">COBLANC · LIBRARY</p>
      <h1>素材库</h1>
      <p class="library-lead">收纳你们的照片、专家参考，以及品牌风格与光色板。<br />共 {{ total }} 件，互不重复。</p>
    </header>

    <section v-for="sec in sections" :key="sec.key" class="library-section">
      <header class="library-section-head">
        <div>
          <h2>{{ sec.title }}</h2>
          <p>{{ sec.hint }}</p>
        </div>
        <span class="library-count">{{ sec.items.length }}</span>
      </header>

      <p v-if="!sec.items.length" class="library-empty">{{ sec.empty || '暂时还没有' }}</p>
      <div v-else class="library-grid">
        <button
          v-for="(item, i) in sec.items"
          :key="item.url"
          type="button"
          class="library-tile"
          :aria-label="`放大 ${item.label || sec.title} ${i + 1}`"
          @click="state.lightbox = item.url"
        >
          <img :src="item.url" :alt="item.label || `${sec.title} ${i + 1}`" loading="lazy" />
          <span v-if="item.label" class="library-tag">{{ item.label }}</span>
        </button>
      </div>
    </section>
  </section>
</template>
