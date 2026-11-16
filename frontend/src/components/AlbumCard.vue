<script setup lang="ts">
import type { Album } from '../api/types'
import CoverArt from './CoverArt.vue'
import ConfidenceMeter from './ConfidenceMeter.vue'
import StatusStamp from './StatusStamp.vue'

const props = defineProps<{ album: Album; selected: boolean }>()
const emit = defineEmits<{ toggle: [id: number] }>()
</script>

<template>
  <article class="group">
    <div class="relative">
      <input
        type="checkbox"
        class="absolute left-2 top-2 z-10 h-4 w-4 accent-copper opacity-0 transition group-hover:opacity-100 checked:opacity-100"
        :checked="selected"
        :aria-label="`选择 ${album.title}`"
        @change="emit('toggle', props.album.id)"
      />
      <RouterLink
        :to="`/albums/${album.id}`"
        class="block aspect-square overflow-hidden border border-line bg-paper2 transition duration-500 group-hover:-translate-y-1 group-hover:shadow-[0_22px_34px_-24px_rgba(20,21,15,0.7)]"
      >
        <CoverArt :album="album" :src="album.cover_url || album.selected_cover_url" />
      </RouterLink>
      <span class="stamp absolute right-2 top-2 bg-paper/90">
        {{ album.kind === 'whole' ? '整轨' : '分轨' }}
      </span>
      <StatusStamp
        v-if="album.status !== 'matched'"
        :status="album.status"
        class="absolute bottom-2 left-2 bg-paper/90"
      />
    </div>
    <div class="mt-3 flex items-start justify-between gap-2">
      <RouterLink :to="`/albums/${album.id}`" class="min-w-0">
        <h3 class="truncate font-display text-[17px] leading-tight">
          {{ album.title || '未知专辑' }}
        </h3>
        <p class="mt-1 truncate font-mono text-[10px] text-ink/45">
          {{ album.artist || '未知艺术家' }}
          <span v-if="album.year"> · {{ album.year }}</span>
        </p>
      </RouterLink>
      <div class="flex-none text-right">
        <span
          class="font-mono text-[10px]"
          :class="
            album.confidence >= 0.85
              ? 'text-ink/40'
              : album.confidence >= 0.6
                ? 'text-copper'
                : 'text-rust'
          "
        >
          {{ album.confidence.toFixed(2) }}
        </span>
        <ConfidenceMeter :score="album.confidence" class="mt-1" />
      </div>
    </div>
  </article>
</template>
