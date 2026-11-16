<script setup lang="ts">
import { ref, watch } from 'vue'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'

const props = defineProps<{
  open: boolean
  covers: { provider: string; url: string; width?: number; height?: number }[]
  current?: string | null
}>()

const emit = defineEmits<{ select: [url: string]; close: [] }>()
const chosen = ref<string | null>(props.current || null)

watch(
  () => props.open,
  (open) => {
    if (open) chosen.value = props.current || null
  },
)

function confirm() {
  if (chosen.value) emit('select', chosen.value)
}
</script>

<template>
  <Dialog :open="open" class="relative z-[90]" @close="$emit('close')">
    <div class="fixed inset-0 bg-ink/60 backdrop-blur-sm" aria-hidden="true"></div>
    <div class="fixed inset-0 flex items-center justify-center p-5">
      <DialogPanel class="w-full max-w-lg border border-ink bg-paper shadow-2xl">
        <div class="flex items-start justify-between border-b border-line px-6 py-4">
          <div>
            <p class="eyebrow">COVER / PICK</p>
            <DialogTitle class="mt-1 font-display text-2xl">选择封面</DialogTitle>
          </div>
          <button class="p-1 text-ink/40 hover:text-ink" @click="$emit('close')">
            <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
              <path stroke-linecap="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div class="px-6 py-5">
          <div v-if="!covers.length" class="border border-dashed border-line p-8 text-center font-mono text-[10px] text-ink/35">
            暂无封面候选
          </div>
          <div v-else class="grid grid-cols-3 gap-2">
            <button
              v-for="cover in covers"
              :key="cover.url"
              class="aspect-square overflow-hidden border"
              :class="chosen === cover.url ? 'border-2 border-ink' : 'border-line'"
              @click="chosen = cover.url"
            >
              <img :src="cover.url" alt="" class="h-full w-full object-cover" />
            </button>
          </div>
          <div class="mt-4 flex items-center justify-between border-t border-line pt-3 font-mono text-[9px] text-ink/40">
            <span>{{ covers.length }} 个候选 · 统一转为 JPEG</span>
            <span>内嵌 + cover.jpg</span>
          </div>
        </div>
        <div class="flex justify-end gap-2 border-t border-line px-6 py-4">
          <button class="border border-line px-4 py-2 font-mono text-[10px] tracking-[0.16em]" @click="$emit('close')">
            取消
          </button>
          <button
            class="bg-ink px-5 py-2 font-mono text-[10px] tracking-[0.16em] text-paper transition hover:bg-copper disabled:opacity-40"
            :disabled="!chosen"
            @click="confirm"
          >
            使用此封面
          </button>
        </div>
      </DialogPanel>
    </div>
  </Dialog>
</template>
