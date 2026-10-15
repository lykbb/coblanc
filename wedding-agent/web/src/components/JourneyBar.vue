<script setup>
import { computed } from 'vue'
import { STAGES, progress, stageStatus, state } from '../store.js'

const pct = computed(() => Math.min(100, Math.max(0, Number(progress.value) || 0)))
// 任务未开始 / 空闲：静止；流水线 busy（进度推进中）才跑跳
const isMoving = computed(() => Boolean(state.busy) && pct.value < 100)
// 填充与新人共用同一百分比；左右留白由 .journey-lane 内边距保证不溢出
const fillWidth = computed(() => `${pct.value}%`)
const laneStyle = computed(() => ({ '--tip': `${pct.value}%` }))
</script>

<template>
  <div class="journey" role="status" :aria-label="`整体进度 ${pct}%`">
    <div class="journey-scene">
      <div class="journey-road">
        <div class="journey-lane" aria-hidden="true" :style="laneStyle">
          <div class="journey-rail">
            <div class="journey-fill" :style="{ width: fillWidth }"></div>
          </div>
          <ol class="journey-dots">
            <li v-for="(stage, i) in STAGES" :key="stage.key" :class="stageStatus(i)">
              <span class="journey-dot"></span>
            </li>
          </ol>
          <div
            class="journey-runner"
            :class="{ 'is-moving': isMoving, settled: pct >= 100 }"
          >
            <svg class="journey-couple" viewBox="0 0 64 40" width="52" height="32" fill="none" overflow="visible">
              <g class="runner-groom">
                <circle cx="42" cy="9" r="4.2" fill="#5c4a3a" />
                <path d="M36.5 15.5c1.2-2.2 3.2-3.4 5.5-3.4s4.3 1.2 5.5 3.4L50 28h-15l1.5-12.5z" fill="#4a5f7a" />
                <path d="M38 28v8" stroke="#3d342c" stroke-width="1.7" stroke-linecap="round" class="leg leg-l" />
                <path d="M47 28v8" stroke="#3d342c" stroke-width="1.7" stroke-linecap="round" class="leg leg-r" />
                <path d="M50 17.5h6" stroke="#c47a62" stroke-width="1.6" stroke-linecap="round" />
              </g>
              <g class="runner-bride">
                <circle cx="20" cy="10" r="4" fill="#f0d8c8" />
                <path d="M20 6.2c2.4-2.8 7-1.2 6.2 2.4" stroke="#f2e6ee" stroke-width="2.2" stroke-linecap="round" />
                <path d="M14.5 16c1-2.4 3-3.6 5.5-3.6s4.5 1.2 5.5 3.6L27.5 29H13l1.5-13z" fill="#f4e9f0" />
                <path d="M16 29v7" stroke="#b89aa8" stroke-width="1.6" stroke-linecap="round" class="leg leg-l" />
                <path d="M24.5 29v7" stroke="#b89aa8" stroke-width="1.6" stroke-linecap="round" class="leg leg-r" />
                <path d="M27.5 18.5h9" stroke="#c47a62" stroke-width="1.6" stroke-linecap="round" />
              </g>
              <path class="runner-heart" d="M31 8.5c0-1.1.9-1.8 1.8-1.8.7 0 1.3.4 1.7 1 .4-.6 1-.1 1.7-1 .9 0 1.8.7 1.8 1.8 0 2.2-3.5 3.8-3.5 3.8S31 10.7 31 8.5z" fill="#e8a090" opacity="0.85" />
            </svg>
          </div>
        </div>
      </div>

      <div class="journey-dest" aria-hidden="true">
        <svg class="journey-house" viewBox="0 0 52 44" width="42" height="36" fill="none">
          <path d="M8 20.5 26 7l18 13.5" stroke="#8b7355" stroke-width="1.8" stroke-linejoin="round" />
          <path d="M11 20.5h30V38H11V20.5z" fill="#f7f1ea" stroke="#c4a882" stroke-width="1.4" />
          <path d="M14 20.5h24L26 10.5 14 20.5z" fill="#e8d2bc" />
          <rect x="22.5" y="27" width="7" height="11" rx="1" fill="#c47a62" />
          <rect x="15" y="24" width="5.5" height="5.5" rx="0.8" fill="#d7e6f0" stroke="#9eb6c6" stroke-width="0.8" />
          <rect x="31.5" y="24" width="5.5" height="5.5" rx="0.8" fill="#d7e6f0" stroke="#9eb6c6" stroke-width="0.8" />
          <path d="M38 8.5v8" stroke="#c45c4a" stroke-width="1.5" stroke-linecap="round" />
          <path d="M38.2 8.5h8.5l-1.4 3.2 1.4 3.1H38.2V8.5z" fill="#d96555" />
        </svg>
        <span class="journey-pct-tiny">{{ pct }}%</span>
      </div>
    </div>
  </div>
</template>
