<script setup>
import { reactive } from 'vue'
import { showToast } from 'vant'
import { api } from '../api.js'

const props = defineProps({ questions: Array, busy: Boolean, step: String, text: String })
const emit = defineEmits(['submit'])

// 等用户回答时，step 表示是谁在问，text 是他说的话
const SPEAKERS = {
  intake: '小囍（项目经理）',
  styling: '妆造师（妆容、发型、服饰）',
  framing: '摄影师（互动、场景、灯光）',
}

// 单选默认选中推荐项，多选默认勾上推荐项；补传照片题的 value 是上传后的 file_id 列表
const values = reactive({})
const uploadLists = reactive({})
for (const q of props.questions) {
  if (q.type === 'multi_choice') values[q.question_id] = Array.isArray(q.recommended) ? [...q.recommended] : []
  else if (q.type === 'upload') values[q.question_id] = []
  else values[q.question_id] = q.recommended ?? ''
  uploadLists[q.question_id] = []
}

async function onUpload(items, question) {
  for (const item of Array.isArray(items) ? items : [items]) {
    item.status = 'uploading'
    try {
      const result = await api.uploadImage(item.file)
      item.fileId = result.file_id
      item.status = 'done'
    } catch (error) {
      item.status = 'failed'
      item.message = '上传失败'
      showToast(error.message)
    }
  }
  syncUpload(question)
}

function syncUpload(question) {
  values[question.question_id] = uploadLists[question.question_id].filter((i) => i.fileId).map((i) => i.fileId)
}

function isEmpty(value) {
  return value === '' || value == null || (Array.isArray(value) && value.length === 0)
}

function submit(useRecommended) {
  const answers = props.questions.map((q) => {
    const value = values[q.question_id]
    if ((useRecommended && q.allow_skip) || isEmpty(value)) return { question_id: q.question_id, skipped: true }
    return { question_id: q.question_id, value }
  })
  const missing = props.questions.find((q, i) => !q.allow_skip && answers[i].skipped)
  if (missing) return showToast(`这题必须回答：${missing.title}`)
  emit('submit', answers)
}
</script>

<template>
  <section class="card">
    <h2>{{ SPEAKERS[step] || step || '小囍' }}</h2>
    <p class="hint">{{ text || '想再确认几件事' }}</p>

    <div v-for="q in questions" :key="q.question_id" class="question">
      <p class="question-title">
        {{ q.title }}<span v-if="!q.allow_skip" class="required">*必答</span>
      </p>

      <van-radio-group v-if="q.type === 'single_choice'" v-model="values[q.question_id]" class="options">
        <van-radio v-for="option in q.options" :key="option.value" :name="option.value">
          <img v-if="option.image" :src="option.image" alt="" class="option-image" />
          {{ option.label }}
          <span v-if="option.value === q.recommended" class="muted">（推荐）</span>
        </van-radio>
      </van-radio-group>

      <van-checkbox-group v-else-if="q.type === 'multi_choice'" v-model="values[q.question_id]" class="options">
        <van-checkbox v-for="option in q.options" :key="option.value" :name="option.value" shape="square">
          <img v-if="option.image" :src="option.image" alt="" class="option-image" />
          {{ option.label }}
          <span v-if="Array.isArray(q.recommended) && q.recommended.includes(option.value)" class="muted">（推荐）</span>
        </van-checkbox>
      </van-checkbox-group>

      <template v-else-if="q.type === 'upload'">
        <van-uploader
          v-model="uploadLists[q.question_id]"
          multiple
          :max-count="10"
          accept="image/jpeg,image/png"
          :after-read="(items) => onUpload(items, q)"
          :after-delete="() => syncUpload(q)"
          preview-size="80"
        />
        <p class="fine">已上传 {{ values[q.question_id].length }} 张</p>
      </template>

      <van-field
        v-else
        v-model="values[q.question_id]"
        :placeholder="q.placeholder || (q.recommended ? `不填就用：${q.recommended}` : '')"
        class="field"
      />
    </div>

    <div class="actions">
      <van-button type="primary" block :loading="busy" @click="submit(false)">提交回答</van-button>
      <van-button block plain :disabled="busy" @click="submit(true)">选填的都用推荐（必答题仍要回答）</van-button>
    </div>
  </section>
</template>
