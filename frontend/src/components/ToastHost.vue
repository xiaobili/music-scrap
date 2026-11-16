<script setup lang="ts">
import { useToastStore } from '../stores/toast'

const toast = useToastStore()
</script>

<template>
  <div class="pointer-events-none fixed bottom-8 right-6 z-[95] flex flex-col gap-2">
    <TransitionGroup
      enter-active-class="transition duration-300"
      enter-from-class="opacity-0 translate-y-2"
      leave-active-class="transition duration-200"
      leave-to-class="opacity-0 translate-y-2"
    >
      <button
        v-for="item in toast.items"
        :key="item.id"
        class="pointer-events-auto border px-4 py-3 text-left font-mono text-[10px] tracking-[0.12em] shadow-2xl"
        :class="item.kind === 'error' ? 'border-rust bg-rust text-paper' : 'border-ink bg-ink text-paper'"
        @click="toast.remove(item.id)"
      >
        {{ item.text }}
      </button>
    </TransitionGroup>
  </div>
</template>
