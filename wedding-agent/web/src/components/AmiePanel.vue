<script setup>
import { computed, ref } from 'vue'
import Icon from './Icon.vue'
import { AMIE, speakerOf } from '../agents.js'
import { framingCounts } from '../plan.js'
import { MAX_REDO, openRedo, phase, restart, state } from '../store.js'

const task = computed(() => state.task)
const speaker = computed(() => speakerOf(task.value?.step))
// 中文里夹英文名时两边加空格："回答 Amie 的"、"回答妆造师的"
const named = (name) => (/^[A-Za-z]/.test(name) ? ` ${name} ` : name)
const asking = computed(() => phase.value.endsWith('_ask'))
const reviewing = computed(() => phase.value === 'sample_review' || phase.value === 'set_review')
const redoLeft = computed(() => Math.max(0, MAX_REDO - state.redoUsed))
const note = ref('')

const bubble = computed(() => {
  const p = phase.value
  if (p === 'start') return { who: null, text: '嗨！我是 Amie 艾蜜 ✨ 先把你们两个人的照片发给我，我来组织妆造师、摄影师和修图师。' }
  if (p === 'loading') return { who: null, text: '正在打开你们的项目…' }
  if (p === 'done') return { who: null, text: task.value?.message || '你们的作品完成啦。' }
  if (p === 'failed') return { who: null, text: task.value?.error?.message || '这次没拍好，换几张更清晰的照片再试试吧。' }
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
  if (p === 'start') return { title: '上传照片', detail: '新郎、新娘各 1～10 张正面照' }
  if (asking.value) return { title: `回答${named(speaker.value.name)}的 ${t?.questions?.length || 0} 个问题`, detail: speaker.value.role }
  if (p === 'composing') return { title: '整理拍摄指令', detail: '把妆造和镜头方案合成一份' }
  if (p === 'sample_gen') return { title: '拍 1 张样片', detail: '先看方向，再拍全套' }
  if (p === 'sample_review') return { title: '确认样片方向', detail: '确认、只要这一张，或者重做' }
  if (p === 'set_gen') return { title: '批量出片', detail: counts || '9 张不同镜头' }
  if (p === 'set_review') return { title: '挑主视觉，确认 9 张', detail: counts }
  if (p === 'pay') return { title: '解锁高清图和物料', detail: '演示版，不会真实扣款' }
  if (p === 'delivering') return { title: '制作婚礼物料', detail: '请柬、迎宾海报、婚礼大屏' }
  if (p === 'done') return { title: '作品已完成', detail: '去「成片交付」下载' }
  if (p === 'failed') return { title: '这次没拍好', detail: task.value?.error?.code || '' }
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

function send() {
  const text = note.value.trim()
  if (!text || !reviewing.value) return
  openRedo('other', text)
  note.value = ''
}

const placeholder = computed(() => {
  if (phase.value === 'start') return '说说你们想要的感觉（选填），比如风格、婚期'
  if (reviewing.value) return redoLeft.value ? '哪里要改？说给 Amie 听' : '重做次数用完了，可以联系人工'
  if (asking.value) return '请在弹出的问题卡片里回答'
  return 'Amie 正在忙，出图后可以提修改意见'
})
</script>

<template>
  <aside class="amie" aria-label="Amie 助手">
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

    <section v-if="materials.length" class="amie-card">
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

    <form class="amie-input" @submit.prevent="send">
      <label class="sr-only" for="amie-input">给 Amie 留言</label>
      <input
        v-if="phase === 'start'"
        id="amie-input"
        v-model="state.draft.description"
        :placeholder="placeholder"
        maxlength="200"
      />
      <input v-else id="amie-input" v-model="note" :placeholder="placeholder" :disabled="!reviewing || !redoLeft" maxlength="200" />
      <button v-if="phase !== 'start'" type="submit" class="send-btn" aria-label="发送" :disabled="!reviewing || !note.trim()"><Icon name="send" :size="18" /></button>
    </form>

    <p v-if="phase === 'start'" class="hint">写好想法、传好照片后，点画布上方的「开始创作」。</p>
    <p v-else-if="reviewing" class="hint">满意的话，在画布的{{ phase === 'set_review' ? '「九张成片」' : '「样片确认」' }}卡片里确认。</p>
    <div v-else class="amie-actions">
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
        <button type="button" class="btn-primary" @click="restart">重新开始</button>
      </template>
    </div>
  </aside>
</template>
