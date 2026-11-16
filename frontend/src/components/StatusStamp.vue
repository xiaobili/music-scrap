<script setup lang="ts">
defineProps<{ status: string; label?: string }>()

const map: Record<string, { label: string; cls: string }> = {
  matched: { label: '已匹配', cls: 'text-moss' },
  pending: { label: '待选择', cls: 'text-amber' },
  unmatched: { label: '未匹配', cls: 'text-rust' },
  applied: { label: '已写入', cls: 'text-moss' },
  failed: { label: '失败', cls: 'text-rust' },
  reverted: { label: '已回滚', cls: 'text-ink/45' },
  running: { label: '运行中', cls: 'text-copper' },
  queued: { label: '排队中', cls: 'text-ink/40' },
  succeeded: { label: '成功', cls: 'text-moss' },
  cancelled: { label: '已取消', cls: 'text-ink/40' },
  draft: { label: '草稿', cls: 'text-ink/45' },
  approved: { label: '待写入', cls: 'text-amber' },
}
</script>

<template>
  <span class="stamp" :class="map[status]?.cls || 'text-ink/40'">
    {{ label || map[status]?.label || status }}
  </span>
</template>
