<script setup>
import { onMounted, ref } from 'vue'
import { portal, tasks, when } from '../api.js'
import { KINDS, money, num } from '../usage.js'
import StatusLegend from './StatusLegend.vue'
import StatusBar from './StatusBar.vue'
import { errorSummary } from '../status.js'

const ASKERS = { intake: '小囍', style: '妆造师', styling: '妆造师', frame: '摄影师', framing: '摄影师' }
const props = defineProps({ target: { type: String, default: '' } })
const items = ref([])
const error = ref('')
const open = ref(null)
const big = ref(null)

async function load() {
  try {
    items.value = (await tasks.list()).items
    error.value = ''
  } catch (e) {
    error.value = e.message
  }
}
onMounted(async () => {
  await load()
  if (props.target) {
    await view({ task_id: props.target })
    document.querySelector('tr.detail')?.scrollIntoView({ block: 'start' })
  }
})

async function view(item) {
  if (open.value?.task_id === item.task_id) return (open.value = null)
  try {
    open.value = await tasks.get(item.task_id)
  } catch (e) {
    error.value = e.message
  }
}
const GROUPS = [['photos', '用户照片'], ['candidates', '生图候选'], ['previews', '样片 / 预览'], ['deliverables', '交付']]
const fmt = (v) => (typeof v === 'string' ? v : JSON.stringify(v, null, 2))
const answer = (a) => (a.skipped ? '（跳过）' : Array.isArray(a.answer_label ?? a.answer) ? (a.answer_label ?? a.answer).join('、') : fmt(a.answer_label ?? a.answer ?? '—'))
const clock = (at) => new Date(at * 1000).toLocaleString('zh-CN', { hour12: false })
function title(t) {
  if (t.kind === 'image') return `${t.engine} · ${t.model} · ${t.status}${t.error_code ? ' · ' + t.error_code : ''} · ${t.seconds}s`
  return `${t.model} · ${KINDS[t.role] || t.role}${t.error ? ' · 失败 ' + t.error : ''}${t.usage ? ` · 入 ${num(t.usage.input)} / 缓存 ${num(t.usage.cached)} / 出 ${num(t.usage.output)}` : ''}`
}
</script>

<template>
  <section class="portal-page">
    <header class="page-head"><h1>任务</h1><span class="page-count">{{ items.length }}</span>
      <StatusLegend :keys="items.map((t) => t.status)" /><button type="button" class="ghost-btn" @click="load">刷新</button></header>
    <p v-if="error" class="page-error" role="alert">{{ error }}</p>
    <table class="data-table">
      <thead><tr><th>操作人</th><th>步骤</th><th>更新</th></tr></thead>
      <tbody>
        <template v-for="t in items" :key="t.task_id">
          <tr class="clickable" :class="{ on: open?.task_id === t.task_id }" @click="view(t)">
            <td><StatusBar :s="t.status" :detail="t.status === 'failed' ? errorSummary(t.error) : ''" />{{ t.operator || '—' }}<span v-if="t.operator && t.operator_source === 'backfill'" class="tag" title="按 IP 推断">推断</span></td>
            <td>{{ t.step_text || t.step || '—' }}</td>
            <td class="muted-s">{{ when(t.updated_at) }}</td>
          </tr>
          <tr v-if="open?.task_id === t.task_id" class="detail">
            <td colspan="3">
              <div class="task-detail">
                <p class="task-id">任务 <span class="mono">{{ open.task_id }}</span></p>
                <a class="link-btn" :href="'#outputs/' + open.task_id">在生成记录中查看 →</a>
                <div v-if="open.error"><h3>错误</h3><pre class="err">{{ fmt(open.error) }}</pre></div>

                <div v-for="[key, label] in GROUPS" :key="key">
                  <template v-if="open.images[key].length">
                    <h3>{{ label }} · {{ open.images[key].length }}</h3>
                    <div class="task-thumbs">
                      <img v-for="url in open.images[key]" :key="url" :src="portal.asset(url)" alt="" loading="lazy" @click="big = portal.asset(url)" />
                    </div>
                  </template>
                </div>

                <div v-if="open.chat.length || open.pending_questions.length">
                  <h3>对话问答</h3>
                  <div class="qa">
                    <template v-for="(a, i) in open.chat" :key="i">
                      <span class="muted-s">{{ ASKERS[a.asker] || a.asker }} · 第{{ a.round }}轮</span>
                      <span><b>{{ a.question || a.question_id }}</b>　{{ answer(a) }}</span>
                    </template>
                    <template v-for="q in open.pending_questions" :key="q.question_id">
                      <span class="muted-s">待回答</span><span><b>{{ q.title }}</b></span>
                    </template>
                  </div>
                </div>

                <details v-for="f in open.fields" :key="f.key" :open="f.key === 'prompt'">
                  <summary>{{ f.label }}</summary><pre>{{ fmt(f.value) }}</pre>
                </details>

                <div>
                  <h3>过程记录 · {{ open.trace.length }}</h3>
                  <span v-if="!open.trace.length" class="muted-s">无（过程记录上线前的任务）</span>
                  <details v-for="(t, i) in open.trace" :key="i">
                    <summary><span class="muted-s">{{ clock(t.at) }}</span>　{{ t.step_label }} · {{ t.kind === 'image' ? '生图请求' : '模型调用' }} · {{ title(t) }}</summary>
                    <template v-if="t.kind === 'image'">
                      <h3>提示词</h3><pre>{{ t.prompt }}</pre>
                      <h3>参数与响应</h3><pre>{{ fmt({ parameters: t.parameters, photos: t.photos, references: t.references, response: t.response, seed: t.seed }) }}</pre>
                    </template>
                    <template v-else>
                      <h3>输入</h3><pre>{{ fmt(t.input) }}</pre>
                      <h3>输出</h3><pre>{{ fmt(t.output) }}</pre>
                    </template>
                  </details>
                </div>

                <div>
                  <h3>用量与费用 · {{ money(open.usage.total) }}</h3>
                  <table class="data-table">
                    <thead><tr><th>步骤</th><th>模型</th><th class="right">调用</th><th class="right">输入</th><th class="right">缓存</th><th class="right">输出</th><th class="right">生图</th><th class="right">费用</th></tr></thead>
                    <tbody>
                      <tr v-for="r in open.usage.step_models" :key="r.step + r.model + r.kind">
                        <td>{{ r.label }}</td><td class="mono">{{ r.model }}</td><td class="right">{{ num(r.calls) }}</td><td class="right">{{ num(r.input) }}</td><td class="right">{{ num(r.cached) }}</td><td class="right">{{ num(r.output) }}</td><td class="right">{{ num(r.images) }}</td><td class="right">{{ money(r) }}</td>
                      </tr>
                      <tr v-if="!open.usage.step_models.length"><td colspan="8" class="muted-s">无记录</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
    <div v-if="big" class="modal dark" @click="big = null"><img class="task-big" :src="big" alt="" /></div>
  </section>
</template>
