<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ score: number }>()
const filled = computed(() => Math.round((props.score || 0) * 5))
const color = computed(() =>
  props.score >= 0.85 ? 'bg-moss' : props.score >= 0.6 ? 'bg-amber' : 'bg-rust',
)
</script>

<template>
  <div class="flex justify-end gap-[2px]">
    <span
      v-for="index in 5"
      :key="index"
      class="h-2.5 w-[3px]"
      :class="index <= filled ? color : 'bg-line'"
    ></span>
  </div>
</template>
