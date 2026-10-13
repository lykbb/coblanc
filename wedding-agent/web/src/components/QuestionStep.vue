<script setup>
import { reactive } from 'vue'
import { showToast } from 'vant'
import { api } from '../api.js'

const props = defineProps({ questions: Array, busy: Boolean, step: String, text: String })
const emit = defineEmits(['submit'])

// 等用户回答时，step 表示是谁在问，text 是他说的话
const SPEAKERS = {
  intake: { mark: '囍', name: '小囍', role: '项目经理' },
  styling: { mark: '妆', name: '妆造师', role: '负责妆容、发型、服饰' },
  framing: { mark: '摄', name: '摄影师', role: '负责互动、场景、灯光' },
}
const speaker = SPEAKERS[props.step] ?? SPEAKERS.intake

// 单选默认选中推荐项；跳过的题由后端用推荐值或默认值补齐
const values = reactive({})
const uploadLists = reactive({})
for (const q of props.questions) {
  values[q.question_id] = q.type === 'multi_choice' ? [] : (q.recommended ?? '')
  uploadLists[q.question_id] = []
}

async function onUpload(item, question) {
  try {
    const result = await api.uploadImage(item.file)
    values[question.question_id] = result.file_id
  } catch (error) {
    showToast(error.message)
    uploadLists[question.question_id] = []
  }
}

function isEmpty(value) {
  return value === '' || value == null || (Array.isArray(value) && value.length === 0)
}

function submit(useRecommended) {
  const answers = props.questions.map((q) => {
    const value = values[q.question_id]
    if (useRecommended || isEmpty(value)) return { question_id: q.question_id, skipped: true }
    return { question_id: q.question_id, value }
  })
  const missing = props.questions.find((q, i) => !q.allow_skip && answers[i].skipped)
  if (missing) return showToast(`请先回答：${missing.title}`)
  emit('submit', answers)
}
</script>

<template>
  <section class="card">
    <div class="speaker">
      <div class="avatar">{{ speaker.mark }}</div>
      <div>
        <p class="speaker-name">{{ speaker.name }}<span>{{ speaker.role }}</span></p>
        <p class="speech">{{ text || '想再确认几件事' }}</p>
      </div>
    </div>
    <div v-for="q in questions" :key="q.question_id" class="question">
      <p class="question-title">{{ q.title }}</p>

      <van-radio-group v-if="q.type === 'single_choice'" v-model="values[q.question_id]" class="options">
        <van-radio v-for="option in q.options" :key="option.value" :name="option.value" class="option">
          <img v-if="option.image" :src="option.image" alt="" class="option-image" />
          {{ option.label }}
          <van-tag v-if="option.value === q.recommended" plain type="primary">推荐</van-tag>
        </van-radio>
      </van-radio-group>

      <van-checkbox-group v-else-if="q.type === 'multi_choice'" v-model="values[q.question_id]" class="options">
        <van-checkbox v-for="option in q.options" :key="option.value" :name="option.value" shape="square" class="option">
          {{ option.label }}
        </van-checkbox>
      </van-checkbox-group>

      <van-uploader
        v-else-if="q.type === 'upload'"
        v-model="uploadLists[q.question_id]"
        :max-count="1"
        accept="image/jpeg,image/png"
        :after-read="(item) => onUpload(item, q)"
      />

      <van-field v-else v-model="values[q.question_id]" :placeholder="q.placeholder" class="field" />
    </div>

    <van-button type="primary" block round :loading="busy" @click="submit(false)">好了，开拍</van-button>
    <van-button block round plain class="secondary" :disabled="busy" @click="submit(true)">都用推荐</van-button>
  </section>
</template>
