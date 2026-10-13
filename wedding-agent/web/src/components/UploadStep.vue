<script setup>
import { ref } from 'vue'
import { showToast } from 'vant'

defineProps({ busy: Boolean })
const emit = defineEmits(['start'])

const MAX_BYTES = 10 * 1024 * 1024
const files = ref([])
const description = ref('')

function beforeRead(file) {
  if (!['image/jpeg', 'image/png'].includes(file.type)) {
    showToast('只支持 jpg 和 png 图片')
    return false
  }
  if (file.size > MAX_BYTES) {
    showToast('图片不能超过 10 MB')
    return false
  }
  return true
}

function start() {
  if (!files.value.length) return showToast('请先上传一张合照')
  emit('start', { file: files.value[0].file, description: description.value.trim() })
}
</script>

<template>
  <section class="card">
    <h2>上传你们的合照</h2>
    <p class="hint">一张就够：两个人都在、正脸、清晰，最好拍到腰部以上。</p>
    <div class="uploader">
      <van-uploader v-model="files" :max-count="1" :before-read="beforeRead" accept="image/jpeg,image/png" preview-size="160" />
    </div>
    <van-field
      v-model="description"
      type="textarea"
      rows="2"
      autosize
      maxlength="200"
      show-word-limit
      placeholder="说说你们的想法，比如：想要韩式影棚风，婚礼在 12 月"
      class="field"
    />
    <van-button type="primary" block round :loading="busy" @click="start">开始拍</van-button>
    <p class="fine">照片只用来生成你们的作品，保存 7 天后自动删除。</p>
  </section>
</template>
