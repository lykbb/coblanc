<script setup>
// 生成记录（只读）：操作人 → 任务 → 用户上传 / 候选与样片 / 成片与交付 / 过程提示词 / 质检
import { computed, onMounted, ref } from 'vue'
import { outputs, portal, when } from '../api.js'
import { TASK_LEGEND, TASK_STATUS as STATUS, bar, taskTone } from '../status.js'
import StatusLegend from './StatusLegend.vue'

const props = defineProps({ target: { type: String, default: '' } })
const items = ref([])
const error = ref('')
const person = ref('')
const status = ref('')
const since = ref('')
const open = ref({})
const details = ref({})
const big = ref(null)

async function load() {
  try { items.value = (await outputs.list()).items; error.value = '' } catch (e) { error.value = e.message }
}
async function toggle(id) {
  open.value = { ...open.value, [id]: !open.value[id] }
  if (open.value[id] && !details.value[id]) {
    try { details.value = { ...details.value, [id]: await outputs.get(id) } } catch (e) { error.value = e.message }
  }
}
onMounted(async () => {
  await load()
  if (props.target) {
    await toggle(props.target)
    document.getElementById('out-' + props.target)?.scrollIntoView({ block: 'start' })
  }
})

const day = (ts) => { const d = new Date(ts * 1000); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
const people = computed(() => [...new Set(items.value.map((t) => t.operator || '未知'))].sort())
const groups = computed(() => {
  const rows = items.value.filter((t) => (!person.value || (t.operator || '未知') === person.value)
    && (!status.value || t.status === status.value) && (!since.value || day(t.updated_at) >= since.value))
  const map = new Map()
  for (const t of rows) {
    const key = t.operator || '未知'
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(t)
  }
  return [...map.entries()]
})
const CATS = [['uploads', '用户上传'], ['candidates', '候选 / 样片'], ['previews', '预览'], ['deliverables', '成片 / 交付']]
const url = (u) => portal.asset(u)
function show(item, label) { big.value = { src: url(item.url || item), prompt: item.prompt, label } }
</script>

<template>
  <section class="portal-page">
    <header class="page-head"><h1>生成记录</h1><span class="page-count">{{ items.length }}</span>
      <div class="filters push">
        <select v-model="person" aria-label="操作人"><option value="">全部人</option><option v-for="p in people" :key="p" :value="p">{{ p }}</option></select>
        <select v-model="status" aria-label="状态"><option value="">全部状态</option><option v-for="(label, key) in STATUS" :key="key" :value="key">{{ label }}</option></select>
        <input v-model="since" type="date" aria-label="起始日期" />
        <StatusLegend :items="TASK_LEGEND" />
      </div>
    </header>
    <p v-if="error" class="page-error" role="alert">{{ error }}</p>
    <p v-if="!groups.length" class="empty-s">暂无数据</p>

    <section v-for="[who, tasks] in groups" :key="who" class="out-person">
      <h2 class="sub-h">{{ who }} <span class="muted-s">{{ tasks.length }} 个任务</span></h2>
      <article v-for="t in tasks" :id="'out-' + t.task_id" :key="t.task_id" class="out-task" :class="bar(taskTone(t.status))">
        <header class="out-head" @click="toggle(t.task_id)">
          <img v-if="t.cover" :src="url(t.cover)" alt="" loading="lazy" class="out-cover" />
          <span v-else class="out-cover empty" />
          <div class="out-meta">
            <strong class="mono">{{ t.task_id }}</strong>
            <span class="muted-s">{{ when(t.updated_at) }} · {{ STATUS[t.status] || t.status }}<span v-if="t.operator_source === 'backfill'" class="tag">推断</span></span>
            <span class="muted-s">上传 {{ t.counts.uploads }} · 候选 {{ t.counts.candidates }} · 交付 {{ t.counts.deliverables }} · 提示词 {{ t.counts.prompts }} · 质检 {{ t.counts.review }}</span>
          </div>
          <a class="link-btn push" :href="'#tasks/' + t.task_id" @click.stop>任务详情 →</a>
        </header>
        <div v-if="open[t.task_id]" class="out-body">
          <p v-if="!details[t.task_id]" class="muted-s">加载中…</p>
          <template v-else>
            <template v-for="[key, label] in CATS" :key="key">
              <div v-if="details[t.task_id][key].length" class="out-cat">
                <h3>{{ label }} · {{ details[t.task_id][key].length }}</h3>
                <div class="out-grid">
                  <figure v-for="(item, i) in details[t.task_id][key]" :key="i" class="out-fig" :class="{ best: item.best }">
                    <img :src="url(item.url || item)" alt="" loading="lazy" @click="show(item, label)" />
                    <figcaption v-if="item.url">
                      <span class="muted-s">{{ item.image_id || item.label }}<template v-if="item.slot != null"> · 镜头 {{ item.slot }}</template><template v-if="item.stage"> · {{ item.stage === 'set' ? '套图' : '样片' }}</template><template v-if="item.best"> · 选中</template><template v-if="item.current === false"> · 往轮</template></span>
                      <p v-if="item.prompt" class="out-prompt">{{ item.prompt }}</p>
                    </figcaption>
                  </figure>
                </div>
              </div>
            </template>
            <details v-for="p in details[t.task_id].prompts" :key="p.label" class="out-text" :open="p.label.includes('最终提示词')">
              <summary>过程提示词 · {{ p.label }}</summary><pre>{{ p.text }}</pre>
            </details>
            <details v-for="r in details[t.task_id].review" :key="r.label" class="out-text">
              <summary>质检 · {{ r.label }}</summary><pre>{{ r.text }}</pre>
            </details>
          </template>
        </div>
      </article>
    </section>

    <div v-if="big" class="modal dark out-lightbox" @click="big = null">
      <img :src="big.src" alt="" />
      <aside v-if="big.prompt" @click.stop><span class="muted-s">{{ big.label }} · 提示词</span><pre>{{ big.prompt }}</pre></aside>
    </div>
  </section>
</template>
