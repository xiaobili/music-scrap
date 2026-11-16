<script setup lang="ts">
import type { Candidate } from '../api/types'

defineProps<{ candidates: Candidate[]; loading?: boolean; selectingId?: number | null }>()
defineEmits<{ select: [candidate: Candidate] }>()

const badges: Record<string, string> = {
  musicbrainz: 'MB',
  discogs: 'DC',
  spotify: 'SP',
  netease: 'NE',
  qq: 'QQ',
  acoustid: 'AC',
}

function formatDuration(ms: number) {
  const total = Math.round((ms || 0) / 1000)
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}
</script>

<template>
  <div class="space-y-2">
    <div v-if="loading" class="border border-line p-6 text-center font-mono text-[10px] text-ink/40">
      正在检索各数据源…
    </div>
    <div v-else-if="!candidates.length" class="border border-line p-6 text-center text-[12px] text-ink/45">
      暂无候选，试试手动关键词检索。
    </div>
    <div
      v-for="(candidate, index) in candidates"
      :key="candidate.id"
      class="border border-line p-4 transition"
      :class="index === 0 ? 'border-l-2 border-l-copper bg-[#fbf8f1]' : 'bg-transparent'"
    >
      <div class="flex items-start gap-4">
        <span class="stamp mt-0.5 text-ink/60">{{ badges[candidate.provider] || candidate.provider }}</span>
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-2">
            <h3 class="font-display text-lg leading-tight">{{ candidate.title || '未知标题' }}</h3>
            <span v-if="index === 0" class="stamp text-copper">推荐</span>
          </div>
          <p class="mt-1 font-mono text-[10px] text-ink/45">
            {{ candidate.artist || '未知艺术家' }}
            <span v-if="candidate.year"> · {{ candidate.year }}</span>
            · {{ candidate.track_count }} tracks
            <span v-if="candidate.duration_ms"> · {{ formatDuration(candidate.duration_ms) }}</span>
            <span v-if="candidate.label"> · {{ candidate.label }}</span>
          </p>
          <p class="mt-1 font-mono text-[9px] text-ink/30">
            {{ candidate.provider }} · {{ candidate.provider_id }}
          </p>
        </div>
        <div class="flex-none text-right">
          <div class="font-display text-2xl leading-none">{{ candidate.score.toFixed(2) }}</div>
          <div class="mt-2 h-1 w-24 bg-line">
            <div class="h-full bg-copper" :style="{ width: `${Math.round(candidate.score * 100)}%` }"></div>
          </div>
          <button
            class="stamp mt-3 py-1.5 transition hover:bg-ink hover:text-paper"
            :disabled="selectingId === candidate.id"
            @click="$emit('select', candidate)"
          >
            {{ selectingId === candidate.id ? '生成中…' : '选择' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
