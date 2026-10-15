<script setup>
import Icon from './Icon.vue'
import { addPhotos, removePhoto, startTask, state } from '../store.js'

function pick(event) {
  addPhotos([...event.target.files])
  event.target.value = ''
}
</script>

<template>
  <section class="start-strip" aria-labelledby="start-title">
    <div class="strip-text">
      <h2 id="start-title">上传你们的照片</h2>
      <p>合照、单人照都可以，1～10 张，越清晰越像。Amie 会帮你们分好新郎和新娘。</p>
    </div>
    <div class="strip-photos">
      <figure v-for="(photo, i) in state.draft.photos" :key="photo.key" class="strip-thumb" :class="{ failed: photo.failed, pending: !photo.file_id && !photo.failed }">
        <img :src="photo.preview" :alt="`照片 ${i + 1}`" />
        <figcaption v-if="photo.failed">失败</figcaption>
        <figcaption v-else-if="!photo.file_id">上传中</figcaption>
        <button type="button" class="thumb-remove" :aria-label="`删除照片 ${i + 1}`" @click="removePhoto(i)"><Icon name="close" :size="12" /></button>
      </figure>
      <label v-if="state.draft.photos.length < 10" class="strip-add">
        <input type="file" accept="image/jpeg,image/png" multiple class="sr-only" @change="pick" />
        <Icon name="plus" :size="20" />
        <span>添加照片</span>
      </label>
    </div>
    <div class="strip-action">
      <button type="button" class="btn-primary" :disabled="state.busy || state.uploading > 0 || !state.draft.photos.length" @click="startTask">
        {{ state.uploading ? '上传中…' : state.busy ? '创建中…' : '开始创作' }}
      </button>
      <span class="hint">{{ state.draft.photos.length }} / 10 张</span>
    </div>
  </section>
</template>
