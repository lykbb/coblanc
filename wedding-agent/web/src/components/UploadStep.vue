<script setup>
import { ref } from 'vue'
import { showToast } from 'vant'

defineProps({ busy: Boolean })
const emit = defineEmits(['start'])

const MAX_BYTES = 10 * 1024 * 1024
const MAX_COUNT = 10
const groomFiles = ref([])
const brideFiles = ref([])
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
  if (!groomFiles.value.length) return showToast('请上传至少 1 张新郎照片')
  if (!brideFiles.value.length) return showToast('请上传至少 1 张新娘照片')
  emit('start', {
    groomFiles: groomFiles.value.map((item) => item.file),
    brideFiles: brideFiles.value.map((item) => item.file),
    description: description.value.trim(),
  })
}
</script>

<template>
  <section class="card">
    <h2>上传你们俩的照片</h2>
    <p class="hint">新郎、新娘分开传，各 1～10 张：正脸、清晰，多几个角度会更像。</p>
    <h3 class="group-title">新郎照片（{{ groomFiles.length }}/{{ MAX_COUNT }}）</h3>
    <div class="uploader">
      <van-uploader v-model="groomFiles" multiple :max-count="MAX_COUNT" :before-read="beforeRead" accept="image/jpeg,image/png" preview-size="90" />
    </div>
    <h3 class="group-title">新娘照片（{{ brideFiles.length }}/{{ MAX_COUNT }}）</h3>
    <div class="uploader">
      <van-uploader v-model="brideFiles" multiple :max-count="MAX_COUNT" :before-read="beforeRead" accept="image/jpeg,image/png" preview-size="90" />
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
