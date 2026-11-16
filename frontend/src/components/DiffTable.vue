<script setup lang="ts">
import type { ChangeItem } from '../api/types'

const props = defineProps<{ items: ChangeItem[] }>()
const emit = defineEmits<{
  update: [payload: { id: number; selected?: boolean; new_value?: string }]
}>()

function targetLabel(item: ChangeItem) {
  return item.target_type === 'album' ? '专辑' : `曲目 #${item.target_id}`
}

function toggle(item: ChangeItem, event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  emit('update', { id: item.id, selected: checked })
}

function edit(item: ChangeItem, event: Event) {
  const value = (event.target as HTMLInputElement).value
  if (value !== item.new_value) {
    emit('update', { id: item.id, new_value: value })
  }
}
</script>

<template>
  <div class="overflow-x-auto border border-line bg-[#fbf8f1]">
    <table class="w-full min-w-[820px] text-left">
      <thead>
        <tr class="border-b border-line">
          <th class="w-10 px-3 py-2.5"></th>
          <th class="eyebrow px-3 py-2.5 font-normal">TARGET</th>
          <th class="eyebrow px-3 py-2.5 font-normal">FIELD</th>
          <th class="eyebrow px-3 py-2.5 font-normal">CURRENT</th>
          <th class="w-6"></th>
          <th class="eyebrow px-3 py-2.5 font-normal">NEW</th>
          <th class="eyebrow px-3 py-2.5 text-right font-normal">ACTION</th>
        </tr>
      </thead>
      <tbody class="text-[12px]">
        <tr
          v-for="item in items"
          :key="item.id"
          class="border-b border-line/50 transition"
          :class="item.selected ? '' : 'opacity-40'"
        >
          <td class="px-3 py-2.5">
            <input
              type="checkbox"
              class="h-3.5 w-3.5 accent-copper"
              :checked="item.selected"
              @change="toggle(item, $event)"
            />
          </td>
          <td class="px-3 py-2.5 font-mono text-[10px] text-ink/35">{{ targetLabel(item) }}</td>
          <td class="px-3 py-2.5 font-mono text-[11px]">{{ item.field }}</td>
          <td class="px-3 py-2.5 font-mono text-[11px] text-ink/35">
            <span :class="item.old_value ? 'line-through text-ink/40' : ''">
              {{ item.old_value || '— 空' }}
            </span>
          </td>
          <td class="px-3 py-2.5 text-center text-copper">→</td>
          <td class="px-3 py-2.5">
            <input
              :value="item.new_value || ''"
              class="w-full border border-transparent bg-transparent px-1 py-0.5 font-sans text-[12px] font-medium focus:border-line focus:bg-paper focus:outline-none"
              @change="edit(item, $event)"
            />
          </td>
          <td class="px-3 py-2.5 text-right">
            <span class="stamp" :class="item.action === 'add' ? 'text-moss' : 'text-ink/40'">
              {{ item.action === 'add' ? '新增' : item.action === 'same' ? '相同' : '更新' }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
