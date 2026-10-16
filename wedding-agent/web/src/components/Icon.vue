<script setup>
// 线条图标，统一 24×24、描边跟随文字颜色
defineProps({ name: { type: String, required: true }, size: { type: [Number, String], default: 18 } })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <template v-if="name === 'home'"><path d="M4 11.5 12 5l8 6.5" /><path d="M6 10v9h12v-9" /></template>
    <template v-else-if="name === 'spark'"><circle cx="12" cy="12" r="7.5" /><circle cx="12" cy="12" r="3" /></template>
    <template v-else-if="name === 'folder'"><rect x="4" y="5" width="16" height="14" rx="2" /></template>
    <template v-else-if="name === 'library'"><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M4 9h16M4 14h16M9 4v16M14 4v16" /></template>
    <template v-else-if="name === 'wall'"><rect x="4" y="4" width="7" height="9" rx="1.5" /><rect x="13" y="4" width="7" height="5" rx="1.5" /><rect x="4" y="15" width="7" height="5" rx="1.5" /><rect x="13" y="11" width="7" height="9" rx="1.5" /></template>
    <template v-else-if="name === 'deliver'"><path d="M5 19 19 5" /><path d="M9 5h10v10" /></template>
    <template v-else-if="name === 'key'"><circle cx="8" cy="15" r="3.5" /><path d="m10.5 12.5 8-8M16 7l2.5 2.5" /></template>
    <template v-else-if="name === 'list'"><path d="M9 6h11M9 12h11M9 18h11" /><circle cx="4.5" cy="6" r=".8" /><circle cx="4.5" cy="12" r=".8" /><circle cx="4.5" cy="18" r=".8" /></template>
    <template v-else-if="name === 'shield'"><path d="M12 3.5 19 6v6c0 4.2-3 7.2-7 8.5-4-1.3-7-4.3-7-8.5V6l7-2.5Z" /></template>
    <template v-else-if="name === 'gauge'"><path d="M4 18V12M9 18V8M14 18v-4M19 18V5" /></template>
    <template v-else-if="name === 'server'"><rect x="4" y="4" width="16" height="7" rx="1.5" /><rect x="4" y="13" width="16" height="7" rx="1.5" /><path d="M8 7.5h.01M8 16.5h.01" /></template>
    <template v-else-if="name === 'file'"><path d="M7 3.5h7l4 4V20.5H7z" /><path d="M14 3.5v4h4" /></template>
    <template v-else-if="name === 'check'"><path d="m5 12.5 4.5 4.5L19 7.5" /></template>
    <template v-else-if="name === 'close'"><path d="M6 6l12 12M18 6 6 18" /></template>
    <template v-else-if="name === 'plus'"><path d="M12 5v14M5 12h14" /></template>
    <template v-else-if="name === 'send'"><path d="M5 12h13" /><path d="m13 6 6 6-6 6" /></template>
    <template v-else-if="name === 'paperclip'"><path d="M21.44 11.05 12.25 20.24a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" /></template>
    <template v-else-if="name === 'flag'"><path d="M6 21V4" /><path d="M6 4h11l-2.5 4L17 12H6" /></template>
    <template v-else-if="name === 'refresh'"><path d="M19 8a7.5 7.5 0 1 0 1 5" /><path d="M19 3v5h-5" /></template>
    <template v-else-if="name === 'download'"><path d="M12 4v11" /><path d="m7 10 5 5 5-5" /><path d="M5 20h14" /></template>
    <template v-else-if="name === 'user'"><circle cx="12" cy="8.5" r="3.5" /><path d="M5 20c1.4-3.6 4-5.5 7-5.5s5.6 1.9 7 5.5" /></template>
    <template v-else-if="name === 'clock'"><circle cx="12" cy="12" r="8" /><path d="M12 8v4.5l3 2" /></template>
    <template v-else-if="name === 'alert'"><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5v5.5M12 16.5v.01" /></template>
    <template v-else-if="name === 'zoom'"><circle cx="11" cy="11" r="6" /><path d="m20 20-4.5-4.5" /></template>
    <template v-else-if="name === 'chevron-left'"><path d="m14.5 5.5-6 6.5 6 6.5" /></template>
    <template v-else-if="name === 'chevron-right'"><path d="m9.5 5.5 6 6.5-6 6.5" /></template>
  </svg>
</template>
