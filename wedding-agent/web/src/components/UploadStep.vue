<script setup>
import { reactive, ref } from 'vue'
import { showToast } from 'vant'
import { api } from '../api.js'

defineProps({ busy: Boolean })
const emit = defineEmits(['start'])

const MAX_BYTES = 10 * 1024 * 1024
const MAX_COUNT = 10
// 选好照片就上传（POST /api/uploads），每张拿到 file_id
const groups = reactive({ groom: [], bride: [] })
const description = ref('')

function beforeRead(file) {
  for (const item of Array.isArray(file) ? file : [file]) {
    if (!['image/jpeg', 'image/png'].includes(item.type)) {
      showToast('只支持 jpg 和 png 图片')
      return false
    }
    if (item.size > MAX_BYTES) {
      showToast('图片不能超过 10 MB')
      return false
    }
  }
  return true
}

async function afterRead(items) {
  for (const item of Array.isArray(items) ? items : [items]) {
    item.status = 'uploading'
    item.message = '上传中'
    try {
      const result = await api.uploadImage(item.file)
      item.fileId = result.file_id
      item.status = 'done'
      item.message = ''
    } catch (error) {
      item.status = 'failed'
      item.message = '上传失败'
      showToast(error.message)
    }
  }
}

const ids = (list) => list.filter((item) => item.fileId).map((item) => item.fileId)
const uploading = (list) => list.some((item) => item.status === 'uploading')

function start() {
  if (uploading(groups.groom) || uploading(groups.bride)) return showToast('照片还在上传，请稍等')
  const groomFileIds = ids(groups.groom)
  const brideFileIds = ids(groups.bride)
  if (!groomFileIds.length) return showToast('请上传至少 1 张新郎照片')
  if (!brideFileIds.length) return showToast('请上传至少 1 张新娘照片')
  emit('start', { groomFileIds, brideFileIds, description: description.value.trim() })
}
</script>

<template>
  <section class="card">
    <h2>上传你们俩的照片</h2>
    <p class="hint">新郎、新娘分开传，各 1～10 张。正脸、清晰，多几个角度会更像。只支持 jpg / png，每张不超过 10 MB。</p>

    <h3>新郎照片（已传 {{ ids(groups.groom).length }} / {{ MAX_COUNT }}）</h3>
    <van-uploader
      v-model="groups.groom"
      multiple
      :max-count="MAX_COUNT"
      :before-read="beforeRead"
      :after-read="afterRead"
      accept="image/jpeg,image/png"
      preview-size="80"
    />

    <h3>新娘照片（已传 {{ ids(groups.bride).length }} / {{ MAX_COUNT }}）</h3>
    <van-uploader
      v-model="groups.bride"
      multiple
      :max-count="MAX_COUNT"
      :before-read="beforeRead"
      :after-read="afterRead"
      accept="image/jpeg,image/png"
      preview-size="80"
    />

    <h3>你们的想法（选填）</h3>
    <van-field
      v-model="description"
      type="textarea"
      rows="3"
      autosize
      maxlength="200"
      show-word-limit
      placeholder="比如：想要韩式影棚风，婚礼在 12 月，杭州"
      class="field"
    />
    <div class="actions">
      <van-button type="primary" block :loading="busy" @click="start">开始制作</van-button>
    </div>
    <p class="fine">照片只用来生成你们的作品，默认保存 7 天后自动删除。</p>
  </section>
</template>
