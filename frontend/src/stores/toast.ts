import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface ToastItem {
  id: number
  text: string
  kind: 'info' | 'error'
}

export const useToastStore = defineStore('toast', () => {
  const items = ref<ToastItem[]>([])
  let seq = 0

  function remove(id: number) {
    items.value = items.value.filter((item) => item.id !== id)
  }

  function push(text: string, kind: 'info' | 'error' = 'info') {
    const id = ++seq
    items.value.push({ id, text, kind })
    window.setTimeout(() => remove(id), 3800)
  }

  return { items, push, remove }
})
