<script setup>
import { onMounted, ref } from 'vue'
import { bytes, ops } from '../api.js'

const tree = ref({}) // 路径 → 子项
const open = ref(new Set(['']))
const file = ref(null)
const error = ref('')

async function load(path) {
  try { tree.value = { ...tree.value, [path]: (await ops.list(path)).items } } catch (e) { error.value = e.message }
}
async function toggle(item) {
  if (!item.dir) return show(item)
  const next = new Set(open.value)
  if (next.has(item.path)) next.delete(item.path)
  else { next.add(item.path); if (!tree.value[item.path]) await load(item.path) }
  open.value = next
}
async function show(item) {
  error.value = ''
  try { file.value = await ops.view(item.path) } catch (e) { error.value = e.message; file.value = null }
}
function rows(path = '', depth = 0) {
  return (tree.value[path] || []).flatMap((item) => [{ item, depth }, ...(item.dir && open.value.has(item.path) ? rows(item.path, depth + 1) : [])])
}
onMounted(() => load(''))
</script>

<template>
  <section class="portal-page files-page">
    <header class="page-head"><h1>项目文件</h1></header>
    <p v-if="error" class="page-error" role="alert">{{ error }}</p>
    <div class="files-split">
      <nav class="files-tree">
        <button v-for="{ item, depth } in rows()" :key="item.path" type="button" class="files-node"
                :class="{ on: file && file.path === item.path, dir: item.dir }" :style="{ paddingLeft: 10 + depth * 14 + 'px' }" @click="toggle(item)">
          <span class="files-caret">{{ item.dir ? (open.has(item.path) ? '▾' : '▸') : '' }}</span>{{ item.name }}
        </button>
      </nav>
      <div class="files-view">
        <template v-if="file">
          <div class="files-head">
            <span class="mono">{{ file.path }}</span><span class="muted-s">{{ bytes(file.size) }}</span>
            <a class="ghost-btn push" :href="ops.raw(file.path, true)">下载</a>
          </div>
          <img v-if="file.kind === 'image'" class="files-img" :src="ops.raw(file.path)" :alt="file.path" />
          <pre v-else-if="file.kind === 'text'" class="files-code">{{ file.text }}</pre>
          <p v-else class="empty-s">二进制文件</p>
          <p v-if="file.truncated" class="muted-s">只显示前 512 KB</p>
        </template>
      </div>
    </div>
  </section>
</template>
