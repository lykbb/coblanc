<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Icon from '@web/components/Icon.vue'
import { refs, when } from '../api.js'

const styles = ref([])
const items = ref([])
const filter = reactive({ style: '', verdict: '' })
const error = ref('')
const dragging = ref(false)
const pending = ref([]) // 待上传文件
const batch = reactive({ style: '00', verdict: 'good', source_url: '', note: '' })
const progress = ref(null)
const open = ref(null) // 正在查看的图
const draft = reactive({ style: '', verdict: '', source_url: '', note: '' })
const picker = ref(null)
let dragDepth = 0

const styleName = (id) => styles.value.find((s) => s.id === id)?.name || id
const params = computed(() => Object.fromEntries(Object.entries(filter).filter(([, v]) => v)))
const zipHref = computed(() => refs.zipUrl(params.value))
const counts = computed(() => ({ good: items.value.filter((i) => i.verdict === 'good').length, bad: items.value.filter((i) => i.verdict === 'bad').length }))

async function load() {
  try {
    items.value = (await refs.list(params.value)).items
    error.value = ''
  } catch (e) {
    error.value = e.message
  }
}

onMounted(async () => {
  try {
    styles.value = (await refs.styles()).styles
  } catch (e) {
    error.value = e.message
  }
  load()
})
watch(params, load)

function take(fileList) {
  const files = [...fileList].filter((f) => f.type.startsWith('image/'))
  if (!files.length) return
  pending.value = files
  batch.style = filter.style || '00'
  batch.verdict = filter.verdict || 'good'
  batch.source_url = ''
  batch.note = ''
}

function onDragEnter(e) {
  if (![...e.dataTransfer.types].includes('Files')) return
  dragDepth++
  dragging.value = true
}
function onDragLeave() {
  dragDepth = Math.max(0, dragDepth - 1)
  if (!dragDepth) dragging.value = false
}
function onDrop(e) {
  dragDepth = 0
  dragging.value = false
  take(e.dataTransfer.files)
}

async function uploadAll() {
  const files = pending.value
  const failed = []
  progress.value = { done: 0, total: files.length }
  for (const file of files) {
    try {
      await refs.upload(file, { ...batch })
    } catch (e) {
      failed.push(`${file.name}：${e.message}`)
      if (e.code === 'REFERENCE_FULL') break
    }
    progress.value.done++
  }
  progress.value = null
  pending.value = []
  error.value = failed.join('；')
  load()
}

function view(item) {
  open.value = item
  Object.assign(draft, { style: item.style, verdict: item.verdict, source_url: item.source_url || '', note: item.note || '' })
}

async function save() {
  const item = open.value
  const changes = Object.fromEntries(Object.entries(draft).filter(([k, v]) => v !== (item[k] || '')))
  if (!Object.keys(changes).length) return
  try {
    Object.assign(item, await refs.update(item.id, changes))
    if ((filter.style && item.style !== filter.style) || (filter.verdict && item.verdict !== filter.verdict)) load()
  } catch (e) {
    error.value = e.message
  }
}

async function remove() {
  if (!confirm('删除这张参考图？')) return
  try {
    await refs.remove(open.value.id)
    open.value = null
    load()
  } catch (e) {
    error.value = e.message
  }
}

</script>

<template>
  <section class="refwall portal-page" @dragenter.prevent="onDragEnter" @dragover.prevent @dragleave="onDragLeave" @drop.prevent="onDrop">
    <header class="refwall-head">
      <h1>参考图墙</h1>
      <span class="page-count">{{ items.length }}</span>
      <div class="refwall-actions">
        <a class="ghost-btn" :class="{ disabled: !items.length }" :href="items.length ? zipHref : undefined" download>
          <Icon name="download" :size="16" />打包下载
        </a>
        <button type="button" class="ghost-btn" @click="picker.click()"><Icon name="plus" :size="16" />上传</button>
        <input ref="picker" type="file" accept="image/jpeg,image/png,image/webp" multiple hidden @change="take($event.target.files); $event.target.value = ''" />
      </div>
    </header>

    <nav class="refwall-tabs" aria-label="风格">
      <button type="button" :class="{ on: !filter.style }" @click="filter.style = ''">全部</button>
      <button v-for="s in styles" :key="s.id" type="button" :class="{ on: filter.style === s.id }" @click="filter.style = s.id">
        <small>{{ s.id }}</small>{{ s.name }}
      </button>
      <span class="refwall-seg" role="group" aria-label="好坏">
        <button type="button" :class="{ on: !filter.verdict }" @click="filter.verdict = ''">全部</button>
        <button type="button" :class="{ on: filter.verdict === 'good' }" @click="filter.verdict = 'good'"><i class="mark good"></i>好<template v-if="!filter.verdict"> {{ counts.good }}</template></button>
        <button type="button" :class="{ on: filter.verdict === 'bad' }" @click="filter.verdict = 'bad'"><i class="mark bad"></i>坏<template v-if="!filter.verdict"> {{ counts.bad }}</template></button>
      </span>
    </nav>

    <p v-if="error" class="page-error" role="alert">{{ error }}</p>

    <div v-if="items.length" class="refwall-grid">
      <button v-for="item in items" :key="item.id" type="button" class="ref-tile" :class="item.verdict" @click="view(item)">
        <img :src="refs.url(item.thumb_url)" :alt="item.note || styleName(item.style)" loading="lazy" decoding="async" :style="{ aspectRatio: item.width + '/' + item.height }" />
        <i class="mark" :class="item.verdict"></i>
      </button>
    </div>
    <div v-else class="refwall-empty" @click="picker.click()"><Icon name="wall" :size="28" /></div>

    <div v-if="dragging" class="refwall-drop"><Icon name="plus" :size="32" /></div>

    <!-- 上传弹层：本批全部套用 -->
    <div v-if="pending.length" class="modal" @click.self="!progress && (pending = [])">
      <form class="ref-pop" @submit.prevent="uploadAll">
        <div class="ref-pop-head"><strong>{{ pending.length }} 张</strong></div>
        <div class="ref-chips">
          <button v-for="s in styles" :key="s.id" type="button" :class="{ on: batch.style === s.id }" @click="batch.style = s.id">{{ s.name }}</button>
        </div>
        <div class="refwall-seg wide">
          <button type="button" :class="{ on: batch.verdict === 'good' }" @click="batch.verdict = 'good'"><i class="mark good"></i>好图</button>
          <button type="button" :class="{ on: batch.verdict === 'bad' }" @click="batch.verdict = 'bad'"><i class="mark bad"></i>坏图</button>
        </div>
        <input v-model="batch.source_url" class="field" type="url" placeholder="来源链接" />
        <input v-model="batch.note" class="field" maxlength="200" placeholder="备注" />
        <div class="ref-pop-foot">
          <button type="button" class="ghost-btn" :disabled="!!progress" @click="pending = []">取消</button>
          <button class="primary-btn" :disabled="!!progress">{{ progress ? `${progress.done} / ${progress.total}` : '上传' }}</button>
        </div>
      </form>
    </div>

    <!-- 大图 -->
    <div v-if="open" class="modal dark" @click.self="save(); open = null" @keydown.esc="open = null">
      <div class="ref-view">
        <img :src="refs.url(open.large_url)" :alt="open.note || styleName(open.style)" />
        <aside class="ref-side">
          <div class="ref-meta">{{ open.uploader }} · {{ when(open.created_at) }}</div>
          <select v-model="draft.style" class="field" @change="save">
            <option v-for="s in styles" :key="s.id" :value="s.id">{{ s.id }} {{ s.name }}</option>
          </select>
          <div class="refwall-seg wide">
            <button type="button" :class="{ on: draft.verdict === 'good' }" @click="draft.verdict = 'good'; save()"><i class="mark good"></i>好图</button>
            <button type="button" :class="{ on: draft.verdict === 'bad' }" @click="draft.verdict = 'bad'; save()"><i class="mark bad"></i>坏图</button>
          </div>
          <input v-model="draft.source_url" class="field" type="url" placeholder="来源链接" @change="save" />
          <a v-if="open.source_url" class="ref-link" :href="open.source_url" target="_blank" rel="noopener noreferrer">{{ open.source_url }}</a>
          <textarea v-model="draft.note" class="field" rows="3" maxlength="200" placeholder="备注" @change="save"></textarea>
          <div class="ref-side-foot">
            <a class="ghost-btn" :href="refs.url(open.original_url) + '&download=1'"><Icon name="download" :size="16" />原图</a>
            <button type="button" class="ghost-btn danger" @click="remove">删除</button>
          </div>
        </aside>
        <button type="button" class="icon-btn light ref-close" aria-label="关闭" @click="save(); open = null"><Icon name="close" /></button>
      </div>
    </div>
  </section>
</template>
