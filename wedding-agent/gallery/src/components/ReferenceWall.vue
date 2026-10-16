<script setup>
// 参考图墙：分类标签页（00 来源链接是链接卡片，其余是图片）、搜索、标签筛选、瀑布流（按列最短优先）、无限滚动、大图、上传
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import Icon from '@web/components/Icon.vue'
import TagInput from './TagInput.vue'
import { links, refs, when } from '../api.js'

const LINKS = '00'
const PAGE = 60
const styles = ref([])
const me = ref('')
const isAdmin = ref(false)
const allTags = ref([])
const filter = reactive({ style: '', verdict: '', q: '', tag: '' })
const search = ref('')
const items = ref([])
const total = ref(0)
const counts = ref({ good: 0, bad: 0 })
const loading = ref(false)
const error = ref('')
const dragging = ref(false)
const pending = ref([])
const batch = reactive({ style: '09', verdict: 'good', title: '', tags: [], source_url: '', note: '' })
const progress = ref(null)
const open = ref(null)
const draft = reactive({ style: '', verdict: '', title: '', tags: [], source_url: '', note: '' })
const linkForm = ref(null) // { id?, title, url, tags }
const picker = ref(null)
const previewPicker = ref(null)
const wall = ref(null)
const sentinel = ref(null)
const columnCount = ref(4)
let dragDepth = 0
let observer, resizer, searchTimer

const isLinks = computed(() => filter.style === LINKS)
const imageStyles = computed(() => styles.value.filter((s) => s.kind === 'images'))
const styleName = (id) => styles.value.find((s) => s.id === id)?.name || id
const tagNames = computed(() => allTags.value.map((t) => t.tag))
const params = computed(() => Object.fromEntries(Object.entries({ style: filter.style, verdict: filter.verdict, q: filter.q, tag: filter.tag }).filter(([, v]) => v)))
const zipHref = computed(() => refs.zipUrl(params.value))
const canEdit = (item) => isAdmin.value || item.uploader === me.value

// 瀑布流：按估计高度放进最短的一列，翻页追加时已有卡片不挪位置
const columns = computed(() => {
  const cols = Array.from({ length: columnCount.value }, () => ({ height: 0, items: [] }))
  for (const item of items.value) {
    const col = cols.reduce((a, b) => (b.height < a.height ? b : a))
    col.items.push(item)
    col.height += (isLinks.value ? (item.preview_height || 900) / (item.preview_width || 1280) + 0.3 : (item.height || 1) / (item.width || 1) + 0.18)
  }
  return cols.map((c) => c.items)
})

async function load(append = false) {
  if (loading.value && append) return
  loading.value = true
  try {
    if (isLinks.value) {
      const data = await links.list({ q: filter.q, tag: filter.tag })
      items.value = data.items
      total.value = data.items.length
    } else {
      const data = await refs.list({ ...params.value, offset: append ? items.value.length : 0, limit: PAGE })
      items.value = append ? [...items.value, ...data.items] : data.items
      total.value = data.total
      counts.value = data.counts
    }
    error.value = ''
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
async function loadTags() {
  try { allTags.value = (await refs.tags()).tags } catch { /* 联想可缺 */ }
}

onMounted(async () => {
  try {
    const info = await refs.styles()
    styles.value = info.styles
    me.value = info.me
    isAdmin.value = info.admin
  } catch (e) {
    error.value = e.message
  }
  load()
  loadTags()
  observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && !isLinks.value && items.value.length < total.value) load(true)
  }, { rootMargin: '800px' })
  if (sentinel.value) observer.observe(sentinel.value)
  resizer = new ResizeObserver(([entry]) => { columnCount.value = Math.max(2, Math.floor(entry.contentRect.width / 240)) })
  if (wall.value) resizer.observe(wall.value)
})
onUnmounted(() => { observer?.disconnect(); resizer?.disconnect() })
watch(params, () => load())
watch(search, (v) => { clearTimeout(searchTimer); searchTimer = setTimeout(() => (filter.q = v.trim()), 250) })

function pickStyle(id) {
  filter.style = id
  if (id === LINKS) filter.verdict = ''
}
function pickTag(tag) {
  filter.tag = filter.tag === tag ? '' : tag
}

// ---- 上传 ----
function take(fileList) {
  const files = [...fileList].filter((f) => f.type.startsWith('image/'))
  if (!files.length || isLinks.value) return
  pending.value = files
  Object.assign(batch, { style: filter.style || '09', verdict: filter.verdict || 'good', title: '', tags: filter.tag ? [filter.tag] : [], source_url: '', note: '' })
}
function onDragEnter(e) {
  if (isLinks.value || ![...e.dataTransfer.types].includes('Files')) return
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
      await refs.upload(file, { ...batch, tags: batch.tags.join(',') })
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
  loadTags()
}

// ---- 图片卡片操作 ----
function view(item) {
  open.value = item
  Object.assign(draft, { style: item.style, verdict: item.verdict, title: item.title || '', tags: [...item.tags], source_url: item.source_url || '', note: item.note || '' })
}
async function patch(item, changes) {
  try {
    Object.assign(item, await refs.update(item.id, changes))
    if ('tags' in changes) loadTags()
  } catch (e) {
    error.value = e.message
  }
}
function save() {
  const item = open.value
  if (!item) return
  const changes = {}
  for (const key of ['style', 'verdict', 'source_url', 'note', ...(canEdit(item) ? ['title'] : [])]) if (draft[key] !== (item[key] || '')) changes[key] = draft[key]
  if (canEdit(item) && draft.tags.join('\u0001') !== item.tags.join('\u0001')) changes.tags = draft.tags
  if (Object.keys(changes).length) patch(item, changes)
}
function flip(item) {
  patch(item, { verdict: item.verdict === 'good' ? 'bad' : 'good' })
}
async function removeRef(item) {
  if (!confirm('删除这张参考图？')) return
  try {
    await refs.remove(item.id)
    if (open.value?.id === item.id) open.value = null
    items.value = items.value.filter((i) => i.id !== item.id)
    total.value--
  } catch (e) {
    error.value = e.message
  }
}
function closeView() {
  save()
  open.value = null
}

// ---- 来源链接 ----
function editLink(link) {
  linkForm.value = link ? { id: link.id, title: link.title, url: link.url, tags: [...link.tags], preview_url: link.preview_url } : { title: '', url: '', tags: [] }
}
async function saveLink() {
  const form = linkForm.value
  progress.value = { done: 0, total: 1 }
  try {
    const body = { title: form.title, url: form.url, tags: form.tags }
    const saved = form.id ? await links.update(form.id, body) : await links.add(body)
    linkForm.value = { ...form, id: saved.id, preview_url: saved.preview_url }
    if (!saved.preview_url) error.value = '没抓到预览图，可以手动上传'
    else linkForm.value = null
    load()
    loadTags()
  } catch (e) {
    error.value = e.message
  } finally {
    progress.value = null
  }
}
async function uploadPreview(file) {
  if (!file || !linkForm.value?.id) return
  try {
    const saved = await links.preview(linkForm.value.id, file)
    linkForm.value.preview_url = saved.preview_url
    error.value = ''
    load()
  } catch (e) {
    error.value = e.message
  }
}
async function refetch() {
  try {
    linkForm.value.preview_url = (await links.refetch(linkForm.value.id)).preview_url
    error.value = ''
    load()
  } catch (e) {
    error.value = e.message
  }
}
async function removeLink(link) {
  if (!confirm('删除这个链接？')) return
  try {
    await links.remove(link.id)
    linkForm.value = null
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
      <span class="page-count">{{ total }}</span>
      <label class="refwall-search">
        <Icon name="search" :size="16" />
        <input v-model="search" type="search" placeholder="搜索标题、标签、上传人、分类" maxlength="100" />
      </label>
      <div class="refwall-actions">
        <template v-if="isLinks">
          <button v-if="isAdmin" type="button" class="ghost-btn" @click="editLink(null)"><Icon name="plus" :size="16" />添加链接</button>
        </template>
        <template v-else>
          <a class="ghost-btn" :class="{ disabled: !total }" :href="total ? zipHref : undefined" download><Icon name="download" :size="16" />打包下载</a>
          <button type="button" class="ghost-btn" @click="picker.click()"><Icon name="plus" :size="16" />上传</button>
        </template>
        <input ref="picker" type="file" accept="image/jpeg,image/png,image/webp" multiple hidden @change="take($event.target.files); $event.target.value = ''" />
      </div>
    </header>

    <nav class="refwall-tabs" aria-label="分类">
      <button type="button" :class="{ on: !filter.style }" @click="pickStyle('')">全部</button>
      <button v-for="s in styles" :key="s.id" type="button" :class="{ on: filter.style === s.id }" @click="pickStyle(s.id)">
        <small>{{ s.id }}</small>{{ s.name }}
      </button>
      <span v-if="!isLinks" class="refwall-seg" role="group" aria-label="好坏">
        <button type="button" :class="{ on: !filter.verdict }" @click="filter.verdict = ''">全部</button>
        <button type="button" :class="{ on: filter.verdict === 'good' }" @click="filter.verdict = 'good'"><i class="mark good"></i>好<template v-if="!filter.verdict"> {{ counts.good }}</template></button>
        <button type="button" :class="{ on: filter.verdict === 'bad' }" @click="filter.verdict = 'bad'"><i class="mark bad"></i>坏<template v-if="!filter.verdict"> {{ counts.bad }}</template></button>
      </span>
    </nav>
    <div v-if="filter.tag" class="refwall-active-tag">
      <button type="button" class="tag-chip on" @click="filter.tag = ''">#{{ filter.tag }} ×</button>
    </div>

    <p v-if="error" class="page-error" role="alert">{{ error }}</p>

    <div ref="wall" class="masonry">
      <div v-for="(col, ci) in columns" :key="ci" class="masonry-col">
        <template v-if="isLinks">
          <article v-for="link in col" :key="link.id" class="pin link-pin">
            <a class="pin-media" :href="link.url" target="_blank" rel="noopener noreferrer">
              <img v-if="link.preview_url" :src="refs.url(link.preview_url)" :alt="link.title" loading="lazy" decoding="async" :style="{ aspectRatio: (link.preview_width || 1280) + '/' + (link.preview_height || 900) }" />
              <span v-else class="pin-placeholder"><Icon name="link" :size="26" /></span>
            </a>
            <div class="pin-cap">
              <a class="pin-title" :href="link.url" target="_blank" rel="noopener noreferrer">{{ link.title }}</a>
              <span class="pin-domain">{{ link.domain }}</span>
              <div v-if="link.tags.length" class="pin-tags"><button v-for="t in link.tags" :key="t" type="button" @click="pickTag(t)">#{{ t }}</button></div>
            </div>
            <div v-if="isAdmin" class="pin-actions"><button type="button" class="pin-act" aria-label="编辑" @click="editLink(link)">编辑</button></div>
          </article>
        </template>
        <template v-else>
          <article v-for="item in col" :key="item.id" class="pin" :class="item.verdict">
            <button type="button" class="pin-media" @click="view(item)">
              <img :src="refs.url(item.thumb_url)" :alt="item.title || styleName(item.style)" loading="lazy" decoding="async" :style="{ aspectRatio: item.width + '/' + item.height }" />
            </button>
            <div class="pin-actions">
              <a class="pin-act" :href="refs.url(item.original_url) + '&download=1'" aria-label="下载" title="下载"><Icon name="download" :size="15" /></a>
              <button type="button" class="pin-act" :title="item.verdict === 'good' ? '标为坏图' : '标为好图'" @click="flip(item)"><i class="mark" :class="item.verdict"></i></button>
              <button v-if="canEdit(item)" type="button" class="pin-act" aria-label="删除" title="删除" @click="removeRef(item)"><Icon name="trash" :size="15" /></button>
            </div>
            <div v-if="item.title || item.tags.length" class="pin-cap">
              <span v-if="item.title" class="pin-title">{{ item.title }}</span>
              <div v-if="item.tags.length" class="pin-tags"><button v-for="t in item.tags" :key="t" type="button" @click="pickTag(t)">#{{ t }}</button></div>
            </div>
          </article>
        </template>
      </div>
    </div>
    <div v-if="!items.length && !loading" class="refwall-empty" @click="!isLinks && picker.click()"><Icon :name="isLinks ? 'link' : 'wall'" :size="28" /></div>
    <div ref="sentinel" class="refwall-sentinel"></div>

    <div v-if="dragging" class="refwall-drop"><Icon name="plus" :size="32" /></div>

    <!-- 上传弹层：本批全部套用 -->
    <div v-if="pending.length" class="modal" @click.self="!progress && (pending = [])">
      <form class="ref-pop" @submit.prevent="uploadAll">
        <div class="ref-pop-head"><strong>{{ pending.length }} 张</strong></div>
        <div class="ref-chips">
          <button v-for="s in imageStyles" :key="s.id" type="button" :class="{ on: batch.style === s.id }" @click="batch.style = s.id">{{ s.name }}</button>
        </div>
        <div class="refwall-seg wide">
          <button type="button" :class="{ on: batch.verdict === 'good' }" @click="batch.verdict = 'good'"><i class="mark good"></i>好图</button>
          <button type="button" :class="{ on: batch.verdict === 'bad' }" @click="batch.verdict = 'bad'"><i class="mark bad"></i>坏图</button>
        </div>
        <input v-model="batch.title" class="field" maxlength="60" placeholder="标题" />
        <TagInput v-model="batch.tags" :suggestions="tagNames" />
        <input v-model="batch.source_url" class="field" type="url" placeholder="来源链接" />
        <input v-model="batch.note" class="field" maxlength="200" placeholder="备注" />
        <div class="ref-pop-foot">
          <button type="button" class="ghost-btn" :disabled="!!progress" @click="pending = []">取消</button>
          <button class="primary-btn" :disabled="!!progress">{{ progress ? `${progress.done} / ${progress.total}` : '上传' }}</button>
        </div>
      </form>
    </div>

    <!-- 来源链接：添加 / 编辑（仅管理员） -->
    <div v-if="linkForm" class="modal" @click.self="!progress && (linkForm = null)">
      <form class="ref-pop" @submit.prevent="saveLink">
        <div class="ref-pop-head"><strong>{{ linkForm.id ? '编辑链接' : '添加链接' }}</strong></div>
        <img v-if="linkForm.preview_url" class="link-preview" :src="refs.url(linkForm.preview_url)" alt="" />
        <input v-model="linkForm.title" class="field" maxlength="60" placeholder="标题" required />
        <input v-model="linkForm.url" class="field" type="url" maxlength="1000" placeholder="https://" required />
        <TagInput v-model="linkForm.tags" :suggestions="tagNames" />
        <div v-if="linkForm.id" class="ref-pop-row">
          <button type="button" class="ghost-btn" @click="previewPicker.click()">上传预览图</button>
          <button type="button" class="ghost-btn" @click="refetch">重新抓取</button>
          <button type="button" class="ghost-btn danger push" @click="removeLink(linkForm)">删除</button>
          <input ref="previewPicker" type="file" accept="image/jpeg,image/png,image/webp" hidden @change="uploadPreview($event.target.files[0]); $event.target.value = ''" />
        </div>
        <div class="ref-pop-foot">
          <button type="button" class="ghost-btn" :disabled="!!progress" @click="linkForm = null">关闭</button>
          <button class="primary-btn" :disabled="!!progress || !linkForm.title.trim() || !linkForm.url.trim()">{{ progress ? '保存中' : '保存' }}</button>
        </div>
      </form>
    </div>

    <!-- 大图 -->
    <div v-if="open" class="modal dark" @click.self="closeView" @keydown.esc="closeView">
      <div class="ref-view">
        <img :src="refs.url(open.large_url)" :alt="open.title || styleName(open.style)" />
        <aside class="ref-side">
          <div class="ref-meta">{{ open.uploader }} · {{ when(open.created_at) }}</div>
          <template v-if="canEdit(open)">
            <input v-model="draft.title" class="field" maxlength="60" placeholder="标题" @change="save" />
            <TagInput v-model="draft.tags" :suggestions="tagNames" @update:model-value="save" />
          </template>
          <template v-else>
            <strong v-if="open.title" class="ref-title">{{ open.title }}</strong>
            <div v-if="open.tags.length" class="pin-tags"><button v-for="t in open.tags" :key="t" type="button" @click="pickTag(t); closeView()">#{{ t }}</button></div>
          </template>
          <select v-model="draft.style" class="field" @change="save">
            <option v-for="s in imageStyles" :key="s.id" :value="s.id">{{ s.id }} {{ s.name }}</option>
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
            <button v-if="canEdit(open)" type="button" class="ghost-btn danger" @click="removeRef(open)">删除</button>
          </div>
        </aside>
        <button type="button" class="icon-btn light ref-close" aria-label="关闭" @click="closeView"><Icon name="close" /></button>
      </div>
    </div>
  </section>
</template>
