<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { BackupBatch } from '../api/types'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import CoverArt from '../components/CoverArt.vue'
import StatusStamp from '../components/StatusStamp.vue'
import { useToastStore } from '../stores/toast'
import { useRouter } from 'vue-router'

const toast = useToastStore()
const router = useRouter()

const batches = ref<BackupBatch[]>([])
const loading = ref(true)
const confirming = ref(false)
const target = ref<BackupBatch | null>(null)
const restoring = ref(false)

async function load() {
  loading.value = true
  try {
    batches.value = await api.backups.list()
  } catch (error) {
    toast.push((error as Error).message, 'error')
  } finally {
    loading.value = false
  }
}

function askRestore(batch: BackupBatch) {
  target.value = batch
  confirming.value = true
}

async function restore() {
  if (!target.value) return
  restoring.value = true
  try {
    await api.backups.restore(target.value.batch_id)
    confirming.value = false
    toast.push('回滚任务已创建，可在任务中心查看进度')
    router.push('/tasks')
  } catch (error) {
    toast.push((error as Error).message, 'error')
  } finally {
    restoring.value = false
  }
}

function formatTime(value: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

onMounted(load)
</script>

<template>
  <section>
    <div class="border-b border-line pb-6">
      <p class="eyebrow">06 / HISTORY</p>
      <h1 class="mt-3 font-display text-[clamp(2rem,4vw,3.2rem)] leading-none tracking-[-0.02em]">
        历史与回滚
      </h1>
      <p class="mt-3 font-mono text-[11px] text-ink/45">
        每次写入都有快照 · 还原标签与内嵌封面
      </p>
    </div>

    <div class="mt-8 grid gap-8 lg:grid-cols-[1fr_300px]">
      <div>
        <div class="flex items-center justify-between">
          <h2 class="font-display text-2xl">写入批次</h2>
          <span class="font-mono text-[10px] text-ink/35">{{ batches.length }} 个批次</span>
        </div>

        <div v-if="loading" class="mt-4 border border-line p-8 text-center font-mono text-[10px] text-ink/40">
          正在读取备份…
        </div>

        <div v-else class="mt-4 space-y-3">
          <div
            v-for="batch in batches"
            :key="batch.batch_id"
            class="border border-line bg-[#fbf8f1] p-5"
            :class="batch.status === 'reverted' ? 'opacity-65' : ''"
          >
            <div class="flex flex-wrap items-start justify-between gap-4">
              <div class="flex items-start gap-4">
                <div class="h-14 w-14 flex-none overflow-hidden border border-line">
                  <CoverArt
                    :src="batch.cover_url"
                    :title="batch.album_title || ''"
                    :subtitle="batch.artist || ''"
                  />
                </div>
                <div>
                  <div class="flex flex-wrap items-center gap-2">
                    <h3 class="font-display text-lg">
                      {{ batch.album_title || '未知专辑' }}
                      <span v-if="batch.artist" class="text-ink/45">— {{ batch.artist }}</span>
                    </h3>
                    <StatusStamp :status="batch.status" />
                  </div>
                  <p class="mt-1 font-mono text-[10px] text-ink/45">
                    {{ batch.files }} 文件 · {{ batch.batch_id }}
                  </p>
                  <p class="mt-1 font-mono text-[9px] text-ink/30">
                    {{ formatTime(batch.created_at) }}
                  </p>
                </div>
              </div>
              <div class="flex gap-2">
                <RouterLink
                  :to="`/albums/${batch.album_id}`"
                  class="stamp py-2 text-ink/55 transition hover:border-ink hover:text-ink"
                >
                  查看专辑
                </RouterLink>
                <button
                  class="stamp py-2 text-rust transition hover:bg-rust hover:text-paper disabled:opacity-40"
                  :disabled="batch.status === 'reverted'"
                  @click="askRestore(batch)"
                >
                  回滚
                </button>
              </div>
            </div>
          </div>

          <div v-if="!batches.length" class="border border-line p-8 text-center">
            <p class="font-display text-xl">还没有写入记录</p>
            <p class="mt-2 font-mono text-[10px] text-ink/40">
              完成一次变更计划后，这里会出现可回滚的批次。
            </p>
          </div>
        </div>
      </div>

      <aside class="space-y-4">
        <div class="card p-5">
          <div class="eyebrow">SNAPSHOT CONTENT</div>
          <ul class="mt-3 space-y-2 font-mono text-[10px] text-ink/50">
            <li class="flex gap-2"><span class="text-copper">·</span>完整原生标签（含 TXXX）</li>
            <li class="flex gap-2"><span class="text-copper">·</span>内嵌图片二进制</li>
            <li class="flex gap-2"><span class="text-copper">·</span>文件 size / mtime</li>
            <li class="flex gap-2"><span class="text-copper">·</span>快照哈希校验</li>
          </ul>
        </div>
        <div class="border border-line p-5">
          <div class="eyebrow">RETENTION</div>
          <p class="mt-3 font-mono text-[10px] leading-relaxed text-ink/40">
            备份保存在 BACKUP_DIR 下，按专辑与批次分目录。清理备份前请确认不再需要回滚。
          </p>
        </div>
        <div class="border border-line p-5">
          <div class="eyebrow">SAFE WRITE</div>
          <p class="mt-3 font-mono text-[10px] leading-relaxed text-ink/40">
            默认原地写入并强制生成快照。可在设置中开启「安全模式」以复制后写。
          </p>
        </div>
      </aside>
    </div>

    <ConfirmDialog
      :open="confirming"
      kicker="ROLLBACK / CONFIRM"
      :title="`回滚 ${target?.album_title || '该批次'}？`"
      confirm-text="确认回滚"
      danger
      @cancel="confirming = false"
      @confirm="restore"
    >
      <p>
        将把 {{ target?.files }} 个文件的标签与封面还原到写入前的快照。
      </p>
      <p class="mt-3 font-mono text-[10px] leading-relaxed text-rust">
        回滚会覆盖此后的标签修改，且不涉及音频流本身。
      </p>
    </ConfirmDialog>
  </section>
</template>
