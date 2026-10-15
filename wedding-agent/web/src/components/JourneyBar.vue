<script setup>
import Icon from './Icon.vue'
import { STAGES, progress, stageStatus } from '../store.js'
</script>

<template>
  <div class="journey" aria-label="整体进度">
    <div class="journey-track">
      <div class="journey-rail" aria-hidden="true"><div class="journey-fill" :style="{ width: progress + '%' }"></div></div>
      <ol class="journey-stops">
        <li v-for="(stage, i) in STAGES" :key="stage.key" :class="stageStatus(i)">
          <span class="journey-dot" aria-hidden="true"></span>
          <span>{{ stage.title }}</span>
        </li>
      </ol>
    </div>
    <div class="journey-pct" role="status">
      <strong>{{ progress }}%</strong>
      <Icon name="flag" :size="20" />
    </div>
  </div>
</template>
