<script setup lang="ts">
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'

defineProps<{
  open: boolean
  title: string
  kicker?: string
  confirmText?: string
  danger?: boolean
}>()

defineEmits<{ confirm: []; cancel: [] }>()
</script>

<template>
  <Dialog :open="open" class="relative z-[90]" @close="$emit('cancel')">
    <div class="fixed inset-0 bg-ink/60 backdrop-blur-sm" aria-hidden="true"></div>
    <div class="fixed inset-0 flex items-center justify-center p-5">
      <DialogPanel class="w-full max-w-lg border border-ink bg-paper shadow-2xl">
        <div class="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div>
            <p class="eyebrow">{{ kicker || 'CONFIRM' }}</p>
            <DialogTitle class="mt-1 font-display text-2xl leading-tight">{{ title }}</DialogTitle>
          </div>
          <button class="p-1 text-ink/40 transition hover:text-ink" @click="$emit('cancel')">
            <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
              <path stroke-linecap="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div class="px-6 py-5 text-[13px] leading-relaxed text-ink/65">
          <slot />
        </div>
        <div class="flex justify-end gap-2 border-t border-line px-6 py-4">
          <button
            class="border border-line px-4 py-2 font-mono text-[10px] tracking-[0.16em] transition hover:border-ink"
            @click="$emit('cancel')"
          >
            取消
          </button>
          <button
            class="px-5 py-2 font-mono text-[10px] tracking-[0.16em] text-paper transition"
            :class="danger ? 'bg-rust hover:bg-ink' : 'bg-ink hover:bg-copper'"
            @click="$emit('confirm')"
          >
            {{ confirmText || '确认' }}
          </button>
        </div>
      </DialogPanel>
    </div>
  </Dialog>
</template>
