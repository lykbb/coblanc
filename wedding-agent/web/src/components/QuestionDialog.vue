<script setup>
import { computed, reactive, ref } from 'vue'
import Modal from './Modal.vue'
import Icon from './Icon.vue'
import { AMIE, STYLE_ART, speakerOf } from '../agents.js'
import { api } from '../api.js'
import { state, submitAnswers } from '../store.js'

const task = computed(() => state.task)
const questions = computed(() => task.value?.questions || [])
const speaker = computed(() => speakerOf(task.value?.step))
const isAmie = computed(() => speaker.value.name === 'Amie')

// 单选默认选推荐项，多选默认勾推荐项；补传题的值是上传后的 file_id 列表
const values = reactive({})
const uploads = reactive({})
for (const q of questions.value) {
  if (q.type === 'multi_choice') values[q.question_id] = Array.isArray(q.recommended) ? [...q.recommended] : []
  else if (q.type === 'upload') values[q.question_id] = []
  else values[q.question_id] = q.type === 'single_choice' ? (q.recommended ?? '') : ''
  uploads[q.question_id] = []
}
const missing = ref('')

function optionImage(q, option) {
  return option.image || (q.question_id === 'q_style' ? STYLE_ART[option.value] : null) || null
}

const hasImages = (q) => q.options.some((option) => optionImage(q, option))

function toggle(q, value) {
  const list = values[q.question_id]
  const at = list.indexOf(value)
  if (at >= 0) list.splice(at, 1)
  else list.push(value)
}

async function addUpload(q, event) {
  for (const file of [...event.target.files]) {
    const item = reactive({ preview: URL.createObjectURL(file), done: false })
    uploads[q.question_id].push(item)
    try {
      const res = await api.uploadImage(file)
      values[q.question_id].push(res.file_id)
      item.done = true
    } catch (error) {
      item.failed = true
      state.error = { code: error.code || null, message: error.message }
    }
  }
  event.target.value = ''
}

function empty(value) {
  return value === '' || value == null || (Array.isArray(value) && !value.length)
}

function build(useRecommended) {
  const answers = []
  for (const q of questions.value) {
    let value = values[q.question_id]
    if (typeof value === 'string') value = value.trim()
    if (useRecommended && q.allow_skip !== false) {
      answers.push({ question_id: q.question_id, skipped: true })
      continue
    }
    if (empty(value)) {
      if (q.allow_skip === false) {
        missing.value = q.question_id
        return null
      }
      answers.push({ question_id: q.question_id, skipped: true })
    } else {
      answers.push({ question_id: q.question_id, value })
    }
  }
  missing.value = ''
  return answers
}

async function submit(useRecommended = false) {
  const answers = build(useRecommended)
  if (answers) await submitAnswers(answers)
}
</script>

<template>
  <Modal :title="`${speaker.name}想和你确认几件事`" wide @close="state.dialog = null">
    <template #head>
      <div class="q-speaker">
        <img loading="lazy" decoding="async" v-if="isAmie" :src="AMIE.avatar" alt="" class="q-avatar" />
        <span v-else class="q-avatar initial" :style="{ background: speaker.color }" aria-hidden="true">{{ speaker.initial }}</span>
        <div>
          <h2>{{ isAmie ? AMIE.name : speaker.name }}</h2>
          <span>{{ speaker.role }}</span>
        </div>
      </div>
    </template>

    <p v-if="task?.step_text" class="q-bubble">{{ task.step_text }}</p>

    <div v-for="q in questions" :key="q.question_id" class="q-item" :class="{ missing: missing === q.question_id }">
      <h3>{{ q.title }} <span v-if="q.allow_skip === false" class="badge">必答</span><span v-else-if="q.type === 'multi_choice'" class="muted">（多选）</span></h3>

      <div v-if="q.type === 'single_choice'" class="q-options" role="radiogroup" :aria-label="q.title">
        <button
          v-for="option in q.options"
          :key="option.value"
          type="button"
          role="radio"
          :aria-checked="values[q.question_id] === option.value"
          class="q-option"
          :class="{ selected: values[q.question_id] === option.value, 'has-image': optionImage(q, option) }"
          @click="values[q.question_id] = option.value"
        >
          <img loading="lazy" decoding="async" v-if="optionImage(q, option)" :src="optionImage(q, option)" alt="" />
          <span v-else-if="hasImages(q)" class="q-noimg" aria-hidden="true">暂无示意图</span>
          <span>{{ option.label }}</span>
          <span v-if="q.recommended === option.value" class="rec">推荐</span>
        </button>
      </div>

      <div v-else-if="q.type === 'multi_choice'" class="chip-row">
        <button
          v-for="option in q.options"
          :key="option.value"
          type="button"
          class="chip"
          :class="{ on: values[q.question_id].includes(option.value) }"
          :aria-pressed="values[q.question_id].includes(option.value)"
          @click="toggle(q, option.value)"
        >
          {{ option.label }}
        </button>
      </div>

      <input v-else-if="q.type === 'text'" v-model="values[q.question_id]" class="q-input" :placeholder="q.placeholder || '可以跳过'" :aria-label="q.title" maxlength="100" />

      <div v-else-if="q.type === 'upload'" class="q-upload">
        <figure v-for="(item, i) in uploads[q.question_id]" :key="i" class="upload-thumb" :class="{ pending: !item.done && !item.failed, failed: item.failed }">
          <img loading="lazy" decoding="async" :src="item.preview" :alt="`补传照片 ${i + 1}`" />
          <figcaption v-if="item.failed">上传失败</figcaption>
          <figcaption v-else-if="!item.done">上传中…</figcaption>
        </figure>
        <label class="upload-add">
          <input type="file" accept="image/jpeg,image/png" multiple class="sr-only" @change="addUpload(q, $event)" />
          <Icon name="plus" :size="22" />
          <span>补传照片</span>
        </label>
      </div>

      <p v-if="missing === q.question_id" class="q-missing" role="alert">这一题需要回答</p>
    </div>

    <template #foot>
      <button type="button" class="btn-ghost" :disabled="state.busy" @click="submit(true)">都用推荐的</button>
      <button type="button" class="btn-primary" :disabled="state.busy" @click="submit(false)">{{ state.busy ? '提交中…' : '提交' }}</button>
    </template>
  </Modal>
</template>
