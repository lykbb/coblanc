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
const open = ref(null) // 大图灯箱
const editing = ref(null) // 编辑弹窗
const menuFor = ref('') // 打开「⋯」菜单的卡片 id
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
const shown = computed(() => items.value.filter((i) => i.kind === (isLinks.value ? 'link' : 'image')))
// 左侧分类栏：点大类展开它的二级标签（按该类数据统计，取前 10），点标签筛选
const navCats = computed(() => [{ id: '', name: '全部' }, ...styles.value])
const subTags = ref([])
// 管理员新增/改名/删除风格（只能动新增的；删除要求分类里没有图）
const styleDraft = ref(null) // { id?, name }
async function saveStyle() {
  const d = styleDraft.value
  if (!d?.name.trim()) { styleDraft.value = null; return }
  try {
    styles.value = (d.id ? await refs.renameStyle(d.id, d.name.trim()) : await refs.addStyle(d.name.trim())).styles
    styleDraft.value = null
    error.value = ''
  } catch (e) { error.value = e.message }
}
async function dropStyle(c) {
  if (!confirm(`删除风格「${c.name}」？`)) return
  try {
    styles.value = (await refs.removeStyle(c.id)).styles
    if (filter.style === c.id) pickStyle('')
    error.value = ''
  } catch (e) { error.value = e.message }
}
async function loadSubTags(style) {
  subTags.value = []
  if (!style) return // 顶层「全部」不展开二级标签
  try {
    const tags = (await refs.tags(style)).tags.slice(0, 10)
    if (filter.style === style) subTags.value = tags
  } catch { /* 二级标签可缺 */ }
}
const imageStyles = computed(() => styles.value.filter((s) => s.kind === 'images'))
const styleName = (id) => styles.value.find((s) => s.id === id)?.name || id
const tagNames = computed(() => allTags.value.map((t) => t.tag))
const params = computed(() => Object.fromEntries(Object.entries({ style: filter.style, verdict: filter.verdict, q: filter.q, tag: filter.tag }).filter(([, v]) => v)))
const zipHref = computed(() => refs.zipUrl(params.value))
const canEdit = (item) => isAdmin.value || item.uploader === me.value

// 瀑布流：按估计高度放进最短的一列，翻页追加时已有卡片不挪位置
const columns = computed(() => {
  const cols = Array.from({ length: columnCount.value }, () => ({ height: 0, items: [] }))
  for (const item of shown.value) {
    const col = cols.reduce((a, b) => (b.height < a.height ? b : a))
    col.items.push(item)
    col.height += (isLinks.value ? (item.preview_url ? item.preview_height / item.preview_width : 0.5) + 0.16 : (item.height || 1) / (item.width || 1) + 0.18)
  }
  return cols.map((c) => c.items)
})

let loadSeq = 0
async function load(append = false) {
  if (loading.value && append) return
  const seq = ++loadSeq // 只认最后一次请求：切换标签页时慢的旧响应直接丢弃
  const forLinks = isLinks.value
  if (!append) { items.value = []; total.value = 0 }
  loading.value = true
  try {
    if (forLinks) {
      const data = await links.list({ q: filter.q, tag: filter.tag })
      if (seq !== loadSeq) return
      items.value = data.items.map((i) => ({ ...i, kind: 'link' }))
      total.value = data.items.length
    } else {
      const data = await refs.list({ ...params.value, offset: append ? items.value.length : 0, limit: PAGE })
      if (seq !== loadSeq) return
      const got = data.items.map((i) => ({ ...i, kind: 'image' }))
      items.value = append ? [...items.value, ...got] : got
      total.value = data.total
      counts.value = data.counts
    }
    error.value = ''
  } catch (e) {
    if (seq === loadSeq) error.value = e.message
  } finally {
    if (seq === loadSeq) loading.value = false
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
document.addEventListener('click', onDocClick)
document.addEventListener('keydown', onKey)
onUnmounted(() => { observer?.disconnect(); resizer?.disconnect(); document.removeEventListener('click', onDocClick); document.removeEventListener('keydown', onKey) })
watch(params, () => load())
watch(search, (v) => { clearTimeout(searchTimer); searchTimer = setTimeout(() => (filter.q = v.trim()), 250) })

function pickStyle(id) {
  if (filter.style === id) return
  filter.style = id
  filter.tag = ''
  loadSubTags(id)
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
  menuFor.value = ''
  open.value = item
}
function editRef(item) {
  menuFor.value = ''
  editing.value = item
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
  const item = editing.value
  if (!item) return
  const changes = {}
  for (const key of ['style', 'verdict', 'source_url', 'note', ...(canEdit(item) ? ['title'] : [])]) if (draft[key] !== (item[key] || '')) changes[key] = draft[key]
  if (canEdit(item) && draft.tags.join('\u0001') !== item.tags.join('\u0001')) changes.tags = draft.tags
  if (Object.keys(changes).length) patch(item, changes)
}
function toggleMenu(id) {
  menuFor.value = menuFor.value === id ? '' : id
}
function onDocClick() { menuFor.value = '' }
function onKey(e) {
  if (e.key !== 'Escape') return
  if (open.value) open.value = null
  else if (editing.value) closeEdit()
  menuFor.value = ''
}
function closeEdit() {
  save()
  editing.value = null
}
function flip(item) {
  menuFor.value = ''
  patch(item, { verdict: item.verdict === 'good' ? 'bad' : 'good' })
}
async function removeRef(item) {
  menuFor.value = ''
  if (!confirm('删除这张参考图？')) return
  try {
    await refs.remove(item.id)
    if (open.value?.id === item.id) open.value = null
    if (editing.value?.id === item.id) editing.value = null
    items.value = items.value.filter((i) => i.id !== item.id)
    total.value--
  } catch (e) {
    error.value = e.message
  }
}
function closeView() {
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
    <aside class="refwall-side" aria-label="分类">
      <p class="side-label"><span>Categories</span>分类</p>
      <div v-for="c in navCats" :key="c.id || 'all'" class="side-cat" :class="{ on: filter.style === c.id, open: c.id && filter.style === c.id && subTags.length }">
        <button type="button" class="side-cat-btn" :aria-expanded="c.id ? filter.style === c.id : undefined" @click="pickStyle(c.id)">
          <small class="side-num">{{ c.id || '—' }}</small><span class="side-name">{{ c.name }}</span>
        </button>
        <span v-if="isAdmin && c.custom" class="side-edit">
          <button type="button" title="重命名" aria-label="重命名" @click="styleDraft = { id: c.id, name: c.name }">✎</button>
          <button type="button" title="删除（分类为空时）" aria-label="删除" @click="dropStyle(c)">×</button>
        </span>
        <div v-if="c.id" class="side-tags-wrap">
          <div class="side-tags">
            <template v-if="filter.style === c.id">
              <button type="button" :class="{ on: !filter.tag }" @click="filter.tag = ''">全部</button>
              <button v-for="t in subTags" :key="t.tag" type="button" :class="{ on: filter.tag === t.tag }" @click="filter.tag = t.tag">{{ t.tag }}<i>{{ t.count }}</i></button>
            </template>
          </div>
        </div>
      </div>
      <template v-if="isAdmin">
        <form v-if="styleDraft" class="side-add-form" @submit.prevent="saveStyle">
          <input v-model="styleDraft.name" maxlength="12" :placeholder="styleDraft.id ? '新名字' : '风格名，如 森系'" autofocus @keydown.esc="styleDraft = null" />
          <button type="submit">{{ styleDraft.id ? '保存' : '添加' }}</button>
        </form>
        <button v-else type="button" class="side-add" @click="styleDraft = { name: '' }"><span>+</span>添加风格</button>
      </template>
    </aside>
    <div class="refwall-body">
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

    <div v-if="!isLinks" class="refwall-toolbar">
      <span v-if="!isLinks" class="refwall-seg" role="group" aria-label="好坏">
        <button type="button" :class="{ on: !filter.verdict }" @click="filter.verdict = ''">全部</button>
        <button type="button" :class="{ on: filter.verdict === 'good' }" @click="filter.verdict = 'good'"><i class="mark good"></i>好<template v-if="!filter.verdict"> {{ counts.good }}</template></button>
        <button type="button" :class="{ on: filter.verdict === 'bad' }" @click="filter.verdict = 'bad'"><i class="mark bad"></i>坏<template v-if="!filter.verdict"> {{ counts.bad }}</template></button>
      </span>
    </div>
    <div v-if="filter.tag" class="refwall-active-tag">
      <button type="button" class="tag-chip on" @click="filter.tag = ''">#{{ filter.tag }} ×</button>
    </div>

    <p v-if="error" class="page-error" role="alert">{{ error }}</p>

    <div ref="wall" class="masonry">
      <div v-for="(col, ci) in columns" :key="ci" class="masonry-col">
        <template v-if="isLinks">
          <article v-for="link in col" :key="link.id" class="pin link-pin" :class="{ 'text-pin': !link.preview_url }">
            <a v-if="link.preview_url" class="pin-media" :href="link.url" target="_blank" rel="noopener noreferrer">
              <img :src="refs.url(link.preview_url)" :alt="link.title" loading="lazy" decoding="async" :style="{ aspectRatio: link.preview_width + '/' + link.preview_height }" />
            </a>
            <a v-else class="link-text" :href="link.url" target="_blank" rel="noopener noreferrer">
              <span class="link-text-kind">{{ link.domain === 'instagram.com' ? 'Instagram' : link.domain }}</span>
              <span class="link-text-title">{{ link.title }}</span>
            </a>
            <a v-if="link.preview_url" class="link-title" :href="link.url" target="_blank" rel="noopener noreferrer">{{ link.title }}</a>
            <div v-if="isAdmin" class="pin-more" :class="{ open: menuFor === link.id }" @click.stop>
              <button type="button" class="pin-dots" aria-label="更多" :aria-expanded="menuFor === link.id" @click="toggleMenu(link.id)">⋯</button>
              <div v-if="menuFor === link.id" class="pin-menu" role="menu">
                <button role="menuitem" type="button" @click="menuFor = ''; editLink(link)">编辑</button>
                <button role="menuitem" type="button" class="danger" @click="menuFor = ''; removeLink(link)">删除</button>
              </div>
            </div>
          </article>
        </template>
        <template v-else>
          <article v-for="item in col" :key="item.id" class="pin" :class="item.verdict">
            <button type="button" class="pin-media" @click="view(item)">
              <img :src="refs.url(item.thumb_url)" :alt="item.title || styleName(item.style)" loading="lazy" decoding="async" :style="{ aspectRatio: item.width + '/' + item.height }" />
            </button>
            <div class="pin-more" :class="{ open: menuFor === item.id }" @click.stop>
              <button type="button" class="pin-dots" aria-label="更多" :aria-expanded="menuFor === item.id" @click="toggleMenu(item.id)">⋯</button>
              <div v-if="menuFor === item.id" class="pin-menu" role="menu">
                <a role="menuitem" :href="refs.url(item.original_url) + '&download=1'" @click="menuFor = ''">下载原图</a>
                <button role="menuitem" type="button" :class="{ checked: item.verdict === 'good' }" @click="item.verdict !== 'good' ? flip(item) : (menuFor = '')">标为好图<span v-if="item.verdict === 'good'">✓</span></button>
                <button role="menuitem" type="button" :class="{ checked: item.verdict === 'bad' }" @click="item.verdict !== 'bad' ? flip(item) : (menuFor = '')">标为坏图<span v-if="item.verdict === 'bad'">✓</span></button>
                <template v-if="canEdit(item)">
                  <hr />
                  <button role="menuitem" type="button" @click="editRef(item)">编辑</button>
                  <button role="menuitem" type="button" class="danger" @click="removeRef(item)">删除</button>
                </template>
              </div>
            </div>
            <span v-if="item.title" class="link-title">{{ item.title }}</span>
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

    <!-- 大图：只有图，点空白或 Esc 关闭 -->
    <div v-if="open" class="modal lightbox" @click.self="closeView">
      <img :src="refs.url(open.large_url)" :alt="open.title || styleName(open.style)" />
      <button type="button" class="icon-btn light ref-close" aria-label="关闭" @click="closeView"><Icon name="close" /></button>
    </div>

    <!-- 编辑图片 -->
    <div v-if="editing" class="modal" @click.self="closeEdit">
      <form class="ref-pop ref-edit" @submit.prevent="closeEdit">
        <div class="ref-edit-head">
          <img :src="refs.url(editing.thumb_url)" alt="" />
          <div><strong>编辑图片</strong><div class="ref-meta">{{ editing.uploader }} · {{ when(editing.created_at) }}</div></div>
        </div>
        <label class="ref-label">标题<input v-model="draft.title" class="field" maxlength="60" placeholder="标题" /></label>
        <div class="ref-label">标签<TagInput v-model="draft.tags" :suggestions="tagNames" /></div>
        <label class="ref-label">分类
          <select v-model="draft.style" class="field">
            <option v-for="s in imageStyles" :key="s.id" :value="s.id">{{ s.id }} {{ s.name }}</option>
          </select>
        </label>
        <div class="refwall-seg wide">
          <button type="button" :class="{ on: draft.verdict === 'good' }" @click="draft.verdict = 'good'"><i class="mark good"></i>好图</button>
          <button type="button" :class="{ on: draft.verdict === 'bad' }" @click="draft.verdict = 'bad'"><i class="mark bad"></i>坏图</button>
        </div>
        <label class="ref-label">来源链接<input v-model="draft.source_url" class="field" type="url" placeholder="https://" /></label>
        <label class="ref-label">备注<textarea v-model="draft.note" class="field" rows="3" maxlength="200" placeholder="备注"></textarea></label>
        <div class="ref-pop-foot">
          <button type="button" class="ghost-btn danger" @click="removeRef(editing)">删除</button>
          <span style="flex:1"></span>
          <button type="button" class="ghost-btn" @click="editing = null">取消</button>
          <button class="primary-btn">保存</button>
        </div>
      </form>
    </div>
    </div>
  </section>
</template>
