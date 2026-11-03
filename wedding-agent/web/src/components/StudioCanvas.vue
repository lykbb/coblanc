<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Icon from './Icon.vue'
import StageCard from './StageCard.vue'
import JourneyBar from './JourneyBar.vue'
import { STYLE_ART } from '../agents.js'
import { framingCounts, heights, short, styleLabel } from '../plan.js'
import { MAX_REDO, STAGES, activeStage, addPhotos, isImageFile, openRedo, phase, review, stageStatus, state } from '../store.js'

const task = computed(() => state.task)
const plan = computed(() => task.value?.plan || {})
const photos = computed(() => plan.value.photos || { groom: [], bride: [], all: [] })
// 一个上传框：分组前先显示全部照片；小囍分好新郎新娘后再分两栏
const sorted = computed(() => photos.value.groom.length > 0 && photos.value.bride.length > 0)
const allPhotos = computed(() => (photos.value.all.length ? photos.value.all : state.draft.photos.map((p) => p.preview)))
const look = computed(() => plan.value.look)
const shot = computed(() => plan.value.shot)
const shots = computed(() => plan.value.shots || [])
const choices = computed(() => plan.value.choices || null)
// 女生/男生造型卡：妆容和衣服各一行，直接用方案里已选的选项
const sideLines = (key) => {
  const c = choices.value
  if (!c) return []
  return [
    c.makeup?.[key] && `妆容：${c.makeup[key]}`,
    `衣服：${c.outfit?.[key] || c.outfit?.label || ''}`,
  ].filter((line) => line && !line.endsWith('：'))
}
const tall = computed(() => heights(plan.value.brief))
const counts = computed(() => framingCounts(shots.value))
const previews = computed(() => task.value?.previews || [])
const finalPhotos = computed(() => task.value?.deliverables?.photos || (task.value?.deliverables?.photo ? [task.value.deliverables.photo] : []))
const styleArt = computed(() => look.value?.references?.find((r) => r.role === 'style')?.url || STYLE_ART[look.value?.style] || null)
const lookRefs = (roles) => (look.value?.references || []).filter((r) => roles.includes(r.role)).slice(0, 2)
const redoLeft = computed(() => Math.max(0, MAX_REDO - state.redoUsed))

// 开始前：第一张卡就是上传入口，点选或把照片拖进来（和 Amie 对话框里的回形针是同一个上传）
const canPick = computed(() => phase.value === 'start' && state.draft.photos.length < 10)
const over = ref(false)
const shown = computed(() => (canPick.value ? 3 : 4)) // 留一格给「添加」
function pick(event) {
  addPhotos([...event.target.files])
  event.target.value = ''
}
function drop(event) {
  over.value = false
  const files = [...(event.dataTransfer?.files || [])].filter(isImageFile)
  if (files.length) addPhotos(files)
}

const subtitle = computed(() => {
  if (phase.value === 'start') return '把你们的照片交给 Amie，她会请妆造师、摄影师和修图师一起为你们出方案'
  if (phase.value === 'done') return '这组婚纱照已经完成，可以去「成片交付」下载高清图和婚礼物料'
  if (phase.value === 'loading') return '正在打开你们的项目…'
  if (phase.value === 'failed') return state.task?.error?.category === 'user_input' ? '上传的照片不符合要求，看看 Amie 的说明' : '系统出了点问题，可以在 Amie 对话框里点「重试」继续'
  return 'Amie 正在协调各领域的专业团队，为你们生成专属的婚纱照方案'
})

const subtitles = computed(() => [
  allPhotos.value.length ? `${allPhotos.value.length} 张照片${sorted.value ? ' · 已分组' : ''}` : '',
  look.value ? styleLabel(look.value.style) : '',
  choices.value?.makeup?.label || '',
  choices.value?.outfit?.label || '',
  choices.value?.scene?.label || '',
  phase.value === 'sample_review' ? '等你确认' : state.sampleUrl ? '已出样片' : '',
  phase.value === 'set_review' ? '9 张已完成，等你确认' : phase.value === 'set_gen' ? '正在拍 9 张' : finalPhotos.value.length > 1 ? '9 张已交付' : '',
])

const sample = computed(() => (phase.value === 'sample_review' ? previews.value[0] : null))
const zoom = (url) => { state.lightbox = url }

// 单节点聚焦：画布中间只放一个节点，完成后自动换到下一个；可以回看之前的
const current = computed(() => Math.min(Math.max(activeStage.value, 0), STAGES.length - 1))
const view = ref(current.value)
const dir = ref('next')
const nextReady = ref(false)
const viewable = (i) => i <= current.value || stageStatus(i) !== 'todo'
function goTo(i) {
  if (i < 0 || i >= STAGES.length || i === view.value || !viewable(i)) return
  dir.value = i > view.value ? 'next' : 'prev'
  view.value = i
  if (i >= current.value) nextReady.value = false
}
watch(current, (now, before) => {
  if (view.value === before || view.value > now) {
    dir.value = now >= view.value ? 'next' : 'prev'
    view.value = now
    nextReady.value = false
  } else if (now !== before) {
    nextReady.value = true
  }
})
const browsing = computed(() => view.value < current.value)

// 键盘左右键切换阶段（输入框里打字时不抢按键，弹窗开着时也不动）
function onKey(e) {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
  if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return
  const t = e.target
  if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return
  if (state.dialog || state.lightbox) return
  e.preventDefault()
  goTo(view.value + (e.key === 'ArrowRight' ? 1 : -1))
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

// 样片、九张出来时把那张卡片滚到眼前，确认按钮不用自己找
const root = ref(null)
watch(phase, async (now, before) => {
  if (now === before || !['sample_review', 'set_review'].includes(now)) return
  await nextTick()
  root.value?.querySelector('.photo-stage.active')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
})
</script>

<template>
  <div ref="root" class="canvas">
    <div class="canvas-scroll">
    <div class="canvas-head">
      <h1>创作画布</h1>
      <p>{{ subtitle }}</p>
    </div>


    <div class="focus-stage">
    <Transition :name="`focus-${dir}`" mode="out-in">
    <div :key="view" class="stage-grid focus-mode">
      <!-- 1 双方照片 -->
      <StageCard v-if="view === 0" :index="0" :title="STAGES[0].title" :subtitle="subtitles[0]" :status="stageStatus(0)">
        <div v-if="!sorted" class="all-photos">
          <div class="mini-head"><span>你们的照片</span><span>{{ allPhotos.length }}/10</span></div>
          <div class="mini-thumbs four">
            <button v-for="(url, i) in allPhotos.slice(0, shown)" :key="url" type="button" class="thumb-btn" :aria-label="`放大照片 ${i + 1}`" @click="zoom(url)">
              <img loading="lazy" decoding="async" :src="url" :alt="`照片 ${i + 1}`" />
              <span v-if="i === shown - 1 && allPhotos.length > shown" class="more">+{{ allPhotos.length - shown }}</span>
            </button>
            <label v-if="canPick && allPhotos.length" class="upload-add" title="继续添加照片">
              <input type="file" accept="image/*,.heic,.heif" multiple class="sr-only" @change="pick" />
              <Icon name="plus" :size="20" />
              <span>添加</span>
            </label>
            <label
              v-if="canPick && !allPhotos.length"
              class="drop-zone"
              :class="{ over }"
              @dragover.prevent="over = true"
              @dragleave="over = false"
              @drop.prevent="drop"
            >
              <input type="file" accept="image/*,.heic,.heif" multiple class="sr-only" @change="pick" />
              <span class="drop-icon"><Icon name="plus" :size="20" /></span>
              <strong>添加你们的照片</strong>
              <small>点击选择，或把照片拖进来<br />2～10 张<br />单张不超过 10 MB</small>
            </label>
            <span v-else-if="!allPhotos.length" class="thumb-empty">{{ phase === 'loading' ? '正在加载…' : '等待上传' }}</span>
          </div>
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
      <StageCard v-if="view === 1" :index="1" :title="STAGES[1].title" :subtitle="subtitles[1]" :status="stageStatus(1)">
        <div class="style-body">
          <button v-if="styleArt" type="button" class="thumb-btn style-art" :aria-label="`放大${styleLabel(look?.style)}风格图`" @click="zoom(styleArt)">
            <img loading="lazy" decoding="async" :src="styleArt" :alt="styleLabel(look?.style)" />
            <span class="tag">{{ styleLabel(look?.style) }}</span>
          </button>
          <div v-else-if="look" class="placeholder">{{ styleLabel(look.style) }}</div>
          <p v-if="choices?.style?.description" class="look-text clamp1">{{ choices.style.description }}</p>
          <div v-if="tall" class="height-chips">
            <span class="pill">女生 {{ tall.bride }} cm</span>
            <span class="pill">男生 {{ tall.groom }} cm</span>
          </div>
        </div>
      </StageCard>

      <!-- 3 女生造型 / 4 男生造型 -->
      <template v-for="side in [{ i: 2, key: 'bride', who: '新娘' }, { i: 3, key: 'groom', who: '新郎' }]" :key="side.key">
      <StageCard v-if="view === side.i" :index="side.i" :title="STAGES[side.i].title" :subtitle="subtitles[side.i]" :status="stageStatus(side.i)">
        <div class="look-body">
          <button v-if="styleArt" type="button" class="thumb-btn look-art" :aria-label="`放大${styleLabel(look?.style)}风格图`" @click="zoom(styleArt)">
            <img loading="lazy" decoding="async" :src="styleArt" :alt="styleLabel(look?.style)" />
            <span class="tag">{{ styleLabel(look?.style) }}</span>
          </button>
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
          <p v-for="line in sideLines(side.key)" :key="line" class="look-text clamp1" :title="line">{{ line }}</p>
        </div>
      </StageCard>
      </template>

      <!-- 5 摄影场景 -->
      <StageCard v-if="view === 4" :index="4" :title="STAGES[4].title" :subtitle="subtitles[4]" :status="stageStatus(4)">
        <div class="scene-body">
          <template v-if="choices?.scene">
            <p class="look-text"><b>{{ choices.scene.label }}</b></p>
            <p class="look-text clamp1">{{ choices.scene.description }}</p>
          </template>
          <div v-if="counts.length" class="height-chips">
            <span v-for="c in counts" :key="c.name" class="pill">{{ c.name }} {{ c.count }}</span>
          </div>
        </div>
      </StageCard>

      <!-- 6 样片确认 -->
      <StageCard v-if="view === 5" class="photo-stage" :index="5" :title="STAGES[5].title" :subtitle="subtitles[5]" :status="stageStatus(5)">
        <div class="sample-body">
          <button v-if="sample || state.sampleUrl" type="button" class="thumb-btn sample-img photo-preview" aria-label="放大样片" @click="zoom(sample?.url || state.sampleUrl)">
            <img loading="lazy" decoding="async" :src="sample?.url || state.sampleUrl" alt="样片（带水印）" />
          </button>
          <div v-else class="placeholder" :class="{ shimmer: phase === 'composing' || phase === 'sample_gen' }">
            {{ phase === 'composing' ? 'Amie 正在写拍摄指令…' : phase === 'sample_gen' ? '正在拍 1 张样片…' : '' }}
          </div>
          <div v-if="sample" class="card-actions icon-actions">
            <button type="button" class="icon-act primary" data-tip="方向对了，拍 9 张" aria-label="方向对了，拍 9 张" :disabled="state.busy" @click="review('confirm', sample.image_id)"><Icon name="grid9" :size="20" /></button>
            <button type="button" class="icon-act" data-tip="只要这一张" aria-label="只要这一张" :disabled="state.busy" @click="review('sample_only', sample.image_id)"><Icon name="image" :size="20" /></button>
            <button type="button" class="icon-act" :data-tip="`重做（还剩 ${redoLeft} 次）`" :aria-label="`重做，还剩 ${redoLeft} 次`" :disabled="state.busy || !redoLeft" @click="openRedo()"><Icon name="refresh" :size="20" /><span class="icon-count">{{ redoLeft }}</span></button>
          </div>
        </div>
      </StageCard>

      <!-- 7 九张成片 -->
      <StageCard v-if="view === 6" class="photo-stage" :index="6" :title="STAGES[6].title" :subtitle="subtitles[6]" :status="stageStatus(6)">
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
            </button>
          </div>
          <div v-else class="set-grid">
            <div v-for="n in 9" :key="n" class="set-cell empty" :class="{ shimmer: phase === 'set_gen' }">
              <span class="num">{{ String(n).padStart(2, '0') }}</span>
              <span class="slot-label">{{ shots[n - 1]?.framing || '' }}</span>
            </div>
          </div>
          <div v-if="phase === 'set_review'" class="card-actions icon-actions">
            <button type="button" class="icon-act primary" data-tip="就选这组，去解锁高清" aria-label="就选这组，去解锁高清" :disabled="state.busy" @click="review('confirm', state.picked)"><Icon name="unlock" :size="20" /></button>
            <button type="button" class="icon-act" :data-tip="`重做（还剩 ${redoLeft} 次）`" :aria-label="`重做，还剩 ${redoLeft} 次`" :disabled="state.busy || !redoLeft" @click="openRedo()"><Icon name="refresh" :size="20" /><span class="icon-count">{{ redoLeft }}</span></button>
          </div>
        </div>
      </StageCard>
    </div>
    </Transition>
    </div>
    </div>
    <JourneyBar :view="view" :can-view="viewable" @go="goTo" />
  </div>
</template>

<style scoped>
.look-art { display: block; width: 100%; aspect-ratio: 16 / 9; margin-bottom: 8px; }
.look-art img { width: 100%; height: 100%; object-fit: cover; border-radius: 8px; }
.clamp2 { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.clamp1 { display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; }
</style>
