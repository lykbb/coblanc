<script setup>
import { computed } from 'vue'
import StageCard from './StageCard.vue'
import JourneyBar from './JourneyBar.vue'
import { STYLE_ART } from '../agents.js'
import { framingCounts, heights, short, splitLook, styleLabel } from '../plan.js'
import { MAX_REDO, STAGES, openRedo, phase, review, stageStatus, state } from '../store.js'

const task = computed(() => state.task)
const plan = computed(() => task.value?.plan || {})
const photos = computed(() => plan.value.photos || { groom: [], bride: [], all: [] })
// 一个上传框：分组前先显示全部照片；小囍分好新郎新娘后再分两栏
const sorted = computed(() => photos.value.groom.length > 0 && photos.value.bride.length > 0)
const allPhotos = computed(() => (photos.value.all.length ? photos.value.all : state.draft.photos.map((p) => p.preview)))
const look = computed(() => plan.value.look)
const shot = computed(() => plan.value.shot)
const shots = computed(() => plan.value.shots || [])
const parts = computed(() => splitLook(look.value?.text))
const tall = computed(() => heights(plan.value.brief))
const counts = computed(() => framingCounts(shots.value))
const previews = computed(() => task.value?.previews || [])
const finalPhotos = computed(() => task.value?.deliverables?.photos || (task.value?.deliverables?.photo ? [task.value.deliverables.photo] : []))
const styleArt = computed(() => look.value?.references?.find((r) => r.role === 'style')?.url || STYLE_ART[look.value?.style] || null)
const lookRefs = (roles) => (look.value?.references || []).filter((r) => roles.includes(r.role)).slice(0, 2)
const redoLeft = computed(() => Math.max(0, MAX_REDO - state.redoUsed))

const subtitle = computed(() => {
  if (phase.value === 'start') return '在右边把照片发给 Amie，她会请妆造师、摄影师和修图师一起为你们出方案'
  if (phase.value === 'done') return '这组婚纱照已经完成，可以去「成片交付」下载高清图和婚礼物料'
  if (phase.value === 'failed') return state.task?.error?.category === 'user_input' ? '上传的照片不符合要求，看看右边 Amie 的说明' : '系统出了点问题，可以在右边点「重试」继续'
  return 'Amie 正在协调各领域的专业团队，为你们生成专属的婚纱照方案'
})

const subtitles = computed(() => [
  allPhotos.value.length ? `${allPhotos.value.length} 张照片${sorted.value ? ' · 已分组' : ''}` : '等你上传',
  look.value ? styleLabel(look.value.style) : '妆造师会和你们确认',
  parts.value.bride ? short(parts.value.bride, 14) : '等妆造方案',
  parts.value.groom ? short(parts.value.groom, 14) : '等妆造方案',
  shot.value ? short(shot.value.text, 14) : '摄影师会和你们确认',
  phase.value === 'sample_review' ? '等你确认' : state.sampleUrl ? '已出样片' : '先拍 1 张看方向',
  phase.value === 'set_review' ? '9 张已完成，等你确认' : phase.value === 'set_gen' ? '正在拍 9 张' : finalPhotos.value.length > 1 ? '9 张已交付' : '样片确认后拍 9 张',
])

const sample = computed(() => (phase.value === 'sample_review' ? previews.value[0] : null))
const zoom = (url) => { state.lightbox = url }
</script>

<template>
  <div class="canvas">
    <div class="canvas-scroll">
    <div class="canvas-head">
      <h1>创作画布</h1>
      <p>{{ subtitle }}</p>
    </div>

    <div class="stage-grid">
      <!-- 1 双方照片 -->
      <StageCard :index="0" :title="STAGES[0].title" :subtitle="subtitles[0]" :status="stageStatus(0)">
        <div v-if="!sorted" class="all-photos">
          <div class="mini-head"><span>你们的照片</span><span>{{ allPhotos.length }}/10</span></div>
          <div class="mini-thumbs four">
            <button v-for="(url, i) in allPhotos.slice(0, 4)" :key="url" type="button" class="thumb-btn" :aria-label="`放大照片 ${i + 1}`" @click="zoom(url)">
              <img loading="lazy" decoding="async" :src="url" :alt="`照片 ${i + 1}`" />
              <span v-if="i === 3 && allPhotos.length > 4" class="more">+{{ allPhotos.length - 4 }}</span>
            </button>
            <span v-if="!allPhotos.length" class="thumb-empty">等待上传</span>
          </div>
          <p v-if="allPhotos.length" class="muted">Amie 看过照片后，会在这里分出新娘和新郎</p>
        </div>
        <div v-else class="pair-photos">
          <div v-for="group in [{ key: 'bride', label: '女生参考照' }, { key: 'groom', label: '男生参考照' }]" :key="group.key" class="pair-col">
            <div class="mini-head"><span>{{ group.label }}</span><span>{{ photos[group.key].length }}/10</span></div>
            <div class="mini-thumbs">
              <button v-for="(url, i) in photos[group.key].slice(0, 2)" :key="url" type="button" class="thumb-btn" :aria-label="`放大${group.label} ${i + 1}`" @click="zoom(url)">
                <img loading="lazy" decoding="async" :src="url" :alt="`${group.label} ${i + 1}`" />
              </button>
              <span v-if="!photos[group.key].length" class="thumb-empty">等待上传</span>
            </div>
          </div>
        </div>
      </StageCard>

      <!-- 2 风格方案 -->
      <StageCard :index="1" :title="STAGES[1].title" :subtitle="subtitles[1]" :status="stageStatus(1)">
        <div class="style-body">
          <button v-if="styleArt" type="button" class="thumb-btn style-art" :aria-label="`放大${styleLabel(look?.style)}风格图`" @click="zoom(styleArt)">
            <img loading="lazy" decoding="async" :src="styleArt" :alt="styleLabel(look?.style)" />
            <span class="tag">{{ styleLabel(look?.style) }}</span>
          </button>
          <div v-else class="placeholder">{{ look ? styleLabel(look.style) : '风格由妆造师和你们一起选' }}</div>
          <div v-if="tall" class="height-chips">
            <span class="pill">女生 {{ tall.bride }} cm</span>
            <span class="pill">男生 {{ tall.groom }} cm</span>
          </div>
        </div>
      </StageCard>

      <!-- 3 女生造型 / 4 男生造型 -->
      <StageCard v-for="side in [{ i: 2, key: 'bride', who: '新娘' }, { i: 3, key: 'groom', who: '新郎' }]" :key="side.key" :index="side.i" :title="STAGES[side.i].title" :subtitle="subtitles[side.i]" :status="stageStatus(side.i)">
        <div class="look-body">
          <div class="look-thumbs">
            <button v-if="photos[side.key][0]" type="button" class="thumb-btn" :aria-label="`放大${side.who}照片`" @click="zoom(photos[side.key][0])">
              <img loading="lazy" decoding="async" :src="photos[side.key][0]" :alt="`${side.who}本人照片`" />
              <span class="tag">本人</span>
            </button>
            <button v-for="item in lookRefs(['makeup', 'outfit'])" :key="item.url" type="button" class="thumb-btn" aria-label="放大妆造参考图" @click="zoom(item.url)">
              <img loading="lazy" decoding="async" :src="item.url" alt="妆造参考图" />
              <span class="tag">{{ item.role === 'makeup' ? '妆容' : '服装' }}</span>
            </button>
          </div>
          <p v-if="parts[side.key]" class="look-text">{{ parts[side.key] }}</p>
          <p v-else class="muted">妆造师确认后，这里会写清{{ side.who }}的妆容、发型和服装</p>
        </div>
      </StageCard>

      <!-- 5 摄影场景 -->
      <StageCard :index="4" :title="STAGES[4].title" :subtitle="subtitles[4]" :status="stageStatus(4)">
        <div class="scene-body">
          <p v-if="shot" class="look-text">{{ short(shot.text, 90) }}</p>
          <p v-else class="muted">摄影师会和你们确认互动、场景、季节和灯光</p>
          <div v-if="counts.length" class="height-chips">
            <span v-for="c in counts" :key="c.name" class="pill">{{ c.name }} {{ c.count }}</span>
          </div>
        </div>
      </StageCard>

      <!-- 6 样片确认 -->
      <StageCard class="photo-stage" :index="5" :title="STAGES[5].title" :subtitle="subtitles[5]" :status="stageStatus(5)">
        <div class="sample-body">
          <button v-if="sample || state.sampleUrl" type="button" class="thumb-btn sample-img photo-preview" aria-label="放大样片" @click="zoom(sample?.url || state.sampleUrl)">
            <img loading="lazy" decoding="async" :src="sample?.url || state.sampleUrl" alt="样片（带水印）" />
            <span class="tag">{{ sample ? '样片 · 带水印' : '已确认的样片' }}</span>
            <span class="zoom-hint">点击看大图</span>
          </button>
          <div v-else class="placeholder" :class="{ shimmer: phase === 'composing' || phase === 'sample_gen' }">
            {{ phase === 'composing' ? 'Amie 正在写拍摄指令…' : phase === 'sample_gen' ? '正在拍 1 张样片…' : '先拍 1 张样片，看方向对不对' }}
          </div>
          <div v-if="sample" class="card-actions">
            <button type="button" class="btn-primary small" :disabled="state.busy" @click="review('confirm', sample.image_id)">方向对了，拍 9 张</button>
            <button type="button" class="btn-ghost small" :disabled="state.busy" @click="review('sample_only', sample.image_id)">只要这一张</button>
            <button type="button" class="btn-ghost small" :disabled="state.busy || !redoLeft" @click="openRedo()">重做（还剩 {{ redoLeft }} 次）</button>
          </div>
        </div>
      </StageCard>

      <!-- 7 九张成片 -->
      <StageCard class="photo-stage" :index="6" :title="STAGES[6].title" :subtitle="subtitles[6]" :status="stageStatus(6)">
        <div class="set-body">
          <div v-if="phase === 'set_review'" class="set-grid photo-set" role="radiogroup" aria-label="选一张做主视觉">
            <div
              v-for="(p, i) in previews"
              :key="p.image_id"
              class="set-cell"
              :class="{ picked: state.picked === p.image_id }"
              role="radio"
              :aria-checked="state.picked === p.image_id"
            >
              <button type="button" class="set-zoom" :aria-label="`放大第 ${i + 1} 张`" @click="zoom(p.url)">
                <img loading="lazy" decoding="async" :src="p.url" :alt="`第 ${i + 1} 张`" />
              </button>
              <span class="num">{{ String(i + 1).padStart(2, '0') }}</span>
              <button
                type="button"
                class="set-pick"
                :aria-pressed="state.picked === p.image_id"
                @click="state.picked = p.image_id"
              >{{ state.picked === p.image_id ? '主视觉' : '选为主视觉' }}</button>
            </div>
          </div>
          <div v-else-if="finalPhotos.length" class="set-grid photo-set">
            <button v-for="(url, i) in finalPhotos" :key="url" type="button" class="set-cell set-zoom-only" :aria-label="`放大第 ${i + 1} 张`" @click="zoom(url)">
              <img loading="lazy" decoding="async" :src="url" :alt="`成片 ${i + 1}`" />
              <span class="num">{{ String(i + 1).padStart(2, '0') }}</span>
              <span class="zoom-hint">点击看大图</span>
            </button>
          </div>
          <div v-else class="set-grid">
            <div v-for="n in 9" :key="n" class="set-cell empty" :class="{ shimmer: phase === 'set_gen' }">
              <span class="num">{{ String(n).padStart(2, '0') }}</span>
              <span class="slot-label">{{ shots[n - 1]?.framing || '' }}</span>
            </div>
          </div>
          <div v-if="phase === 'set_review'" class="card-actions">
            <button type="button" class="btn-primary small" :disabled="state.busy" @click="review('confirm', state.picked)">就选这组，去解锁高清</button>
            <button type="button" class="btn-ghost small" :disabled="state.busy || !redoLeft" @click="openRedo()">重做（还剩 {{ redoLeft }} 次）</button>
            <span class="hint">点图看大图；点「选为主视觉」定主图</span>
          </div>
        </div>
      </StageCard>
    </div>
    </div>
    <JourneyBar />
  </div>
</template>
