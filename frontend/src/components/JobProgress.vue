<script setup lang="ts">
import { computed } from 'vue'
import type { Job } from '../api/types'
import StatusStamp from './StatusStamp.vue'

const props = defineProps<{ job: Job }>()

const steps = computed(() => {
  const table: Record<string, string[]> = {
    scan: ['遍历目录', '解析标签与 CUE', '生成目录指纹', '写入索引'],
    match: ['构建查询', '多源检索', '打分排序', '写入候选'],
    apply: ['快照标签', '写入字段', '嵌入封面', '回读校验'],
    rollback: ['载入快照', '还原标签', '还原封面', '完成'],
  }
  return table[props.job.type] || ['执行中']
})

const active = computed(() => {
  const count = steps.value.length
  return Math.min(count - 1, Math.floor((props.job.progress || 0) * count))
})

const segments = computed(() => Math.round((props.job.progress || 0) * 12))
</script>

<template>
  <div class="card p-5">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span v-if="job.status === 'running'" class="spinner"></span>
        <StatusStamp :status="job.status" />
        <span class="font-mono text-[10px] text-ink/35">#{{ job.id }} · {{ job.type }}</span>
      </div>
      <span class="font-mono text-[10px] text-ink/35">{{ job.done }} / {{ job.total }}</span>
    </div>

    <h3 class="mt-2 font-display text-xl">
      {{ String(job.payload?.root_id ? `扫描根目录 #${job.payload.root_id}` : job.payload?.album_id ? `匹配专辑 #${job.payload.album_id}` : job.payload?.plan_id ? `写入计划 #${job.payload.plan_id}` : job.payload?.batch_id ? `回滚 ${job.payload.batch_id}` : job.type) }}
    </h3>

    <div class="mt-4 flex gap-1">
      <span
        v-for="index in 12"
        :key="index"
        class="seg"
        :class="index <= segments ? 'on' : 'soft'"
      ></span>
    </div>
    <div class="mt-2 flex justify-between font-mono text-[10px] text-ink/45">
      <span>{{ Math.round((job.progress || 0) * 100) }}%</span>
      <span>{{ String(job.result?.message || '') }}</span>
    </div>

    <ol class="mt-5 space-y-2 text-[12px]">
      <li
        v-for="(step, index) in steps"
        :key="step"
        class="flex items-center gap-2"
        :class="index < active ? 'text-ink/40' : index === active ? 'text-ink' : 'text-ink/30'"
      >
        <svg
          v-if="index < active"
          class="h-3.5 w-3.5 text-moss"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5" />
        </svg>
        <span v-else-if="index === active" class="spinner"></span>
        <span v-else class="h-3.5 w-3.5 rounded-full border border-line"></span>
        {{ step }}
      </li>
    </ol>

    <p v-if="job.error" class="mt-4 border-t border-line pt-3 font-mono text-[9px] leading-relaxed text-rust">
      {{ job.error }}
    </p>
  </div>
</template>
