<script setup>
import { computed } from 'vue'
import { STYLE_ART, STYLE_LABELS } from '../agents.js'
import { state } from '../store.js'

const ASSET = '/coblanc-film/assets/'
const LIB = ASSET + 'library/'

// 每张图整页只用一次
const BRAND = [
  { url: ASSET + 'coblanc-film-hero.webp', label: '主视觉' },
  { url: ASSET + 'coblanc-film-couple.webp', label: '合照印象' },
  { url: ASSET + 'film-style-board.webp', label: '胶片风格板' },
  { url: ASSET + 'studio-framework.webp', label: '工作台示意' },
  { url: ASSET + 'amie-portrait.webp', label: 'Amie 形象' },
]

const STYLE_TILES = [
  { url: STYLE_ART.chinese_red_gold, label: STYLE_LABELS.chinese_red_gold },
  { url: STYLE_ART.korean_studio, label: STYLE_LABELS.korean_studio },
  { url: STYLE_ART.french_editorial, label: STYLE_LABELS.french_editorial },
  { url: STYLE_ART.cinematic, label: STYLE_LABELS.cinematic },
  { url: STYLE_ART.retro, label: STYLE_LABELS.retro },
  { url: ASSET + 'style-minimal.webp', label: '极简清透' },
]

const MOODS = [
  { label: '晨光', colors: ['#F3E3CF', '#E6C29E', '#FBF6EE'] },
  { label: '薄雾', colors: ['#E6E8EB', '#C3CBD4', '#F6F6F4'] },
  { label: '暖桃', colors: ['#F3D6C7', '#DFA287', '#FBF0E9'] },
  { label: '丁香', colors: ['#E5DCEB', '#BBA8CE', '#F6F2F7'] },
  { label: '奶油', colors: ['#F6EEDC', '#E4D2AC', '#FCFAF3'] },
  { label: '松青', colors: ['#D2DDD5', '#8CA595', '#EFF3EE'] },
  { label: '腮红', colors: ['#F1D7D6', '#D99FA2', '#FAEFEE'] },
  { label: '雾蓝', colors: ['#D8E0E8', '#9AAEC1', '#F0F3F6'] },
  { label: '香槟', colors: ['#EEE4CF', '#CFB88C', '#F9F5EB'] },
  { label: '灰紫', colors: ['#DED8E0', '#A79CAE', '#F3F0F3'] },
  { label: '鼠尾草', colors: ['#DCE2D3', '#A2B193', '#F3F5EE'] },
  { label: '绯红', colors: ['#EDCDC7', '#C47B72', '#F8ECE9'] },
  { label: '浅芋', colors: ['#E8DFEA', '#C2AFC9', '#F6F2F6'] },
  { label: '亚麻', colors: ['#ECE5D8', '#C9BA9E', '#F7F3EC'] },
  { label: '湖光', colors: ['#D5E5E5', '#8DB6B7', '#EEF5F4'] },
  { label: '蜜杏', colors: ['#F4E0CB', '#DDAA77', '#FBF3EA'] },
  { label: '鸢尾', colors: ['#DEDAEC', '#A19AC8', '#F3F2F8'] },
  { label: '青瓷', colors: ['#D6E4DD', '#97BCAD', '#EEF4F1'] },
].map((m) => ({ ...m, url: `mood:${m.label}` }))
const moodBg = (c) => `radial-gradient(120% 75% at 28% 18%, ${c[2]} 0%, transparent 62%), radial-gradient(90% 70% at 85% 95%, ${c[1]} 0%, transparent 70%), linear-gradient(165deg, ${c[0]} 0%, ${c[1]} 120%)`

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
    { key: 'mood', title: '色与光', hint: '柔和氛围参考', items: take(MOODS) },
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
        <template v-for="(item, i) in sec.items" :key="item.url">
          <div v-if="item.colors" class="library-tile mood-tile" :style="{ background: moodBg(item.colors) }" :title="item.colors.join('  ')">
            <span class="mood-name">{{ item.label }}</span>
          </div>
          <button
            v-else
            type="button"
            class="library-tile"
            :aria-label="`放大 ${item.label || sec.title} ${i + 1}`"
            @click="state.lightbox = item.url"
          >
            <img :src="item.url" :alt="item.label || `${sec.title} ${i + 1}`" loading="lazy" decoding="async" />
            <span v-if="item.label" class="library-tag">{{ item.label }}</span>
          </button>
        </template>
      </div>
    </section>
  </section>
</template>
