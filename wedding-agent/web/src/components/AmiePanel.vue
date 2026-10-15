<script setup>
import { computed, ref } from 'vue'
import Icon from './Icon.vue'
import { AMIE, speakerOf } from '../agents.js'
import { framingCounts } from '../plan.js'
import { MAX_REDO, addPhotos, failureText, openRedo, phase, removePhoto, restart, retryTask, startTask, state, submitPhotoFix } from '../store.js'

const task = computed(() => state.task)
const speaker = computed(() => speakerOf(task.value?.step))
// 中文里夹英文名时两边加空格："回答 Amie 的"、"回答妆造师的"
const named = (name) => (/^[A-Za-z]/.test(name) ? ` ${name} ` : name)
const photoFix = computed(() => phase.value.endsWith('_ask') && (state.task?.questions || []).some((q) => q.type === 'upload'))
const asking = computed(() => phase.value.endsWith('_ask') && !photoFix.value)
// 能往对话框里加照片：开始前，或者等用户补传照片时
const canAttach = computed(() => phase.value === 'start' || photoFix.value)
const failure = computed(() => task.value?.error || state.error || null)
const reviewing = computed(() => phase.value === 'sample_review' || phase.value === 'set_review')
const redoLeft = computed(() => Math.max(0, MAX_REDO - state.redoUsed))
const note = ref('')
const dragging = ref(false)
let dragDepth = 0

const bubble = computed(() => {
  const p = phase.value
  if (p === 'start') return { who: null, text: '嗨！我是 Amie 艾蜜 ✨ 先把你们两个人的照片发给我，合照、单人照都可以。' }
  if (p === 'loading') return { who: null, text: '正在打开你们的项目…' }
  if (p === 'done') return { who: null, text: task.value?.message || '你们的作品完成啦。' }
  if (p === 'failed') return { who: null, text: failureText(failure.value) }
  if (photoFix.value) return { who: null, text: task.value?.step_text || task.value?.questions?.[0]?.title || '照片还差一点，补传一下就能继续。' }
  if (p === 'pay') return { who: null, text: '这组照片已经定好了，解锁后就能下载 9 张高清图和婚礼物料。' }
  if (p === 'sample_review') return { who: null, text: '样片出来了，先看看方向对不对。满意的话我就安排拍 9 张；不满意告诉我哪里要改。' }
  if (p === 'set_review') return { who: null, text: '9 张套图都拍好了，修图师已经逐张检查过。挑一张做主视觉，请柬和海报都用它。' }
  const s = speaker.value
  return { who: s.name === 'Amie' ? null : s, text: task.value?.step_text || '马上就好…' }
})

const current = computed(() => {
  const p = phase.value
  const t = task.value
  const counts = framingCounts(t?.plan?.shots).map((c) => `${c.name} ${c.count}`).join(' · ')
  if (p === 'start') return { title: '上传照片', detail: '2～10 张，至少 1 张合照；宠物入镜请说明' }
  if (photoFix.value) return { title: '照片还差一点', detail: task.value?.questions?.find((q) => q.type === 'upload')?.title?.replace(/^照片还差一点：/, '') || '' }
  if (asking.value) return { title: `回答${named(speaker.value.name)}的 ${t?.questions?.length || 0} 个问题`, detail: speaker.value.role }
  if (p === 'composing') return { title: '整理拍摄指令', detail: '把妆造和镜头方案合成一份' }
  if (p === 'sample_gen') return { title: '拍 1 张样片', detail: '先看方向，再拍全套' }
  if (p === 'sample_review') return { title: '确认样片方向', detail: '确认、只要这一张，或者重做' }
  if (p === 'set_gen') return { title: '批量出片', detail: counts || '9 张不同镜头' }
  if (p === 'set_review') return { title: '挑主视觉，确认 9 张', detail: counts }
  if (p === 'pay') return { title: '解锁高清图和物料', detail: '演示版，不会真实扣款' }
  if (p === 'delivering') return { title: '制作婚礼物料', detail: '请柬、迎宾海报、婚礼大屏' }
  if (p === 'done') return { title: '作品已完成', detail: '去「成片交付」下载' }
  if (p === 'failed') {
    const e = failure.value
    if (e?.category === 'user_input') return { title: e.title || '上传的照片不符合要求', detail: e.message }
    return { title: e?.title || '系统异常，这一步没完成', detail: e?.retryable ? '模型/网络/服务异常，可以点「重试」' : (e?.message || '') }
  }
  return { title: `${named(speaker.value.name).trimStart()}正在准备`, detail: speaker.value.role }
})

const currentThumb = computed(() => {
  const t = task.value
  return t?.deliverables?.photo || t?.previews?.[0]?.url || state.sampleUrl || t?.plan?.photos?.bride?.[0] || null
})

const materials = computed(() => {
  const fromPlan = task.value?.plan?.photos?.all || []
  if (fromPlan.length) return fromPlan
  return state.draft.photos.map((p) => p.preview)
})

const draftPhotos = computed(() => state.draft.photos)
const canStart = computed(() => draftPhotos.value.some((p) => p.file_id) && !state.busy && state.uploading === 0)

// 开始前的灵感短句：点一下追加到"你们的想法"里
const IDEAS = ['想要东方中式喜嫁', '韩式影棚，干净简洁', '法式杂志感，有点胶片味', '新娘想保留眼镜']
function addIdea(text) {
  const current = state.draft.description.trim()
  state.draft.description = current ? `${current}，${text}` : text
}

const chips = computed(() => {
  const p = phase.value
  if (p === 'start') return IDEAS.map((idea) => ({ label: idea, run: () => addIdea(idea) }))
  // 确认类操作放在画布卡片里，这里只提修改意见，避免同一个操作出现在好几个地方
  if (!redoLeft.value && (p === 'sample_review' || p === 'set_review')) return []
  if (p === 'sample_review') return [
    { label: '脸不太像', run: () => openRedo('face') },
    { label: '我想换一种风格试试', run: () => openRedo('style') },
    { label: '帮我调整样片的氛围', run: () => openRedo('other', '调整一下样片的氛围和光线') },
  ]
  if (p === 'set_review') return [
    { label: '脸不太像', run: () => openRedo('face') },
    { label: '手部有点怪', run: () => openRedo('hands') },
    { label: '身材比例不对', run: () => openRedo('body') },
  ]
  if (asking.value) return [{ label: '去回答问题', run: () => { state.dialog = 'questions' } }]
  if (p === 'done') return [
    { label: '下载全部成片', run: () => { state.view = 'delivery' } },
    { label: '再做一组', run: restart },
  ]
  return []
})

function pick(event) {
  addPhotos([...event.target.files])
  event.target.value = ''
}

function onDragEnter(event) {
  if (!canAttach.value) return
  if (![...event.dataTransfer.types].includes('Files')) return
  event.preventDefault()
  dragDepth += 1
  dragging.value = true
}

function onDragOver(event) {
  if (!canAttach.value) return
  if (![...event.dataTransfer.types].includes('Files')) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'copy'
}

function onDragLeave(event) {
  if (!canAttach.value) return
  event.preventDefault()
  dragDepth = Math.max(0, dragDepth - 1)
  if (dragDepth === 0) dragging.value = false
}

function onDrop(event) {
  if (!canAttach.value) return
  event.preventDefault()
  dragDepth = 0
  dragging.value = false
  const files = [...(event.dataTransfer.files || [])].filter((f) => f.type.startsWith('image/'))
  if (files.length) addPhotos(files)
}

function send() {
  if (phase.value === 'start') {
    if (canStart.value) startTask()
    return
  }
  const text = note.value.trim()
  if (photoFix.value) {
    submitPhotoFix(text).then((ok) => { if (ok) note.value = '' })
    return
  }
  if (!text || !reviewing.value) return
  openRedo('other', text)
  note.value = ''
}

const placeholder = computed(() => {
  if (phase.value === 'start') return '说说你们想要的感觉（选填）'
  // 审片阶段单独文案，不与生成中混用
  if (reviewing.value) return redoLeft.value ? '哪里要改？说给 Amie 听' : '重做次数用完了，可以联系人工'
  if (photoFix.value) return '补传照片，或告诉 Amie（如：小狗要一起入镜）'
  if (asking.value) return '请在弹出的问题卡片里回答'
  // 处理中 / LLM 忙碌 / 出图中
  return '正在为您生成中'
})

</script>

<template>
  <aside
    class="amie"
    :class="{ 'drop-active': dragging }"
    aria-label="Amie 助手"
    @dragenter="onDragEnter"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <div class="amie-scroll">
    <section class="amie-card amie-intro">
      <img :src="AMIE.avatar" alt="Amie 艾蜜的形象照" />
      <div>
        <h2>{{ AMIE.title }}</h2>
        <p v-for="line in AMIE.intro" :key="line">{{ line }}</p>
      </div>
    </section>

    <section class="amie-bubble" aria-live="polite">
      <p v-if="bubble.who" class="bubble-who"><span class="who-dot" :style="{ background: bubble.who.color }" aria-hidden="true">{{ bubble.who.initial }}</span>{{ bubble.who.name }} · {{ bubble.who.role }}</p>
      <p>{{ bubble.text }}</p>
    </section>

    <section class="amie-card">
      <h3>当前任务</h3>
      <div class="current">
        <button v-if="currentThumb" type="button" class="current-thumb" aria-label="放大图片" @click="state.lightbox = currentThumb">
          <img :src="currentThumb" alt="" />
        </button>
        <div>
          <strong>{{ current.title }}</strong>
          <span>{{ current.detail }}</span>
        </div>
      </div>
    </section>

    <section v-if="phase !== 'start' && materials.length" class="amie-card">
      <div class="card-row"><h3>已上传的素材</h3><button type="button" class="link-btn" @click="state.view = 'library'">查看全部</button></div>
      <div class="material-row">
        <button v-for="(url, i) in materials.slice(0, 4)" :key="url" type="button" class="thumb-btn" :aria-label="`放大素材 ${i + 1}`" @click="state.lightbox = url">
          <img :src="url" :alt="`素材 ${i + 1}`" />
        </button>
      </div>
    </section>

    <section v-if="state.log.length" class="amie-card amie-log">
      <h3>动态</h3>
      <ol>
        <li v-for="(item, i) in state.log.slice(-5)" :key="i" :class="{ mine: item.mine }">
          <time>{{ item.at }}</time><b>{{ item.who }}</b>{{ item.text }}
        </li>
      </ol>
    </section>

    <section v-if="chips.length" class="amie-say">
      <h3>你可以这样说</h3>
      <div class="chip-row">
        <button v-for="chip in chips" :key="chip.label" type="button" class="chip" :disabled="state.busy" @click="chip.run">{{ chip.label }}</button>
      </div>
    </section>

    </div>

    <div class="amie-composer">
      <div v-if="canAttach && draftPhotos.length" class="composer-thumbs">
        <figure v-for="(photo, i) in draftPhotos" :key="photo.key" class="composer-thumb" :class="{ failed: photo.failed, pending: !photo.file_id && !photo.failed }">
          <img :src="photo.preview" :alt="`照片 ${i + 1}`" />
          <figcaption v-if="photo.failed">失败</figcaption>
          <figcaption v-else-if="!photo.file_id">上传中</figcaption>
          <button type="button" class="thumb-remove" :aria-label="`删除照片 ${i + 1}`" @click="removePhoto(i)"><Icon name="close" :size="12" /></button>
        </figure>
        <span class="composer-count">{{ draftPhotos.length }}/10</span>
      </div>

      <form class="amie-input" @submit.prevent="send">
        <label v-if="canAttach && draftPhotos.length < 10" class="attach-btn" title="添加附件">
          <input type="file" accept="image/jpeg,image/png" multiple class="sr-only" @change="pick" />
          <Icon name="paperclip" :size="18" />
          <span class="sr-only">添加附件</span>
        </label>
        <label class="sr-only" for="amie-input">给 Amie 留言</label>
        <input
          v-if="phase === 'start'"
          id="amie-input"
          v-model="state.draft.description"
          :placeholder="placeholder"
          maxlength="200"
        />
        <input v-else id="amie-input" v-model="note" :placeholder="placeholder" :disabled="!photoFix && (!reviewing || !redoLeft)" maxlength="200" />
        <button
          v-if="phase === 'start'"
          type="submit"
          class="send-btn"
          :aria-label="canStart ? '开始创作' : '请先添加照片'"
          :disabled="!canStart"
        >
          <Icon name="send" :size="18" />
        </button>
        <button v-else type="submit" class="send-btn" aria-label="发送" :disabled="photoFix ? (state.busy || (!note.trim() && !draftPhotos.some((p) => p.file_id))) : (!reviewing || !note.trim())"><Icon name="send" :size="18" /></button>
      </form>

      <p v-if="reviewing" class="hint">满意的话，在画布的{{ phase === 'set_review' ? '「九张成片」' : '「样片确认」' }}卡片里确认。</p>
      <div v-else-if="asking || phase === 'pay' || phase === 'done' || phase === 'failed'" class="amie-actions">
        <template v-if="asking">
          <button type="button" class="btn-primary" @click="state.dialog = 'questions'">回答问题</button>
        </template>
        <template v-else-if="phase === 'pay'">
          <button type="button" class="btn-primary" :disabled="state.busy" @click="state.dialog = 'pay'">去解锁高清</button>
        </template>
        <template v-else-if="phase === 'done'">
          <button type="button" class="btn-ghost" @click="restart">再做一组</button>
          <button type="button" class="btn-primary" @click="state.view = 'delivery'">查看并下载成片</button>
        </template>
        <template v-else-if="phase === 'failed'">
          <button v-if="failure?.retryable" type="button" class="btn-primary" :disabled="state.busy" @click="retryTask">重试</button>
          <button type="button" :class="failure?.retryable ? 'btn-ghost' : 'btn-primary'" @click="restart">重新开始</button>
        </template>
      </div>
    </div>
  </aside>
</template>
