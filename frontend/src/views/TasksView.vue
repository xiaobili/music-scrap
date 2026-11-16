<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import type { Job } from '../api/types'
import JobProgress from '../components/JobProgress.vue'
import StatusStamp from '../components/StatusStamp.vue'
import { useJobsStore } from '../stores/jobs'
import { useToastStore } from '../stores/toast'

const store = useJobsStore()
const toast = useToastStore()
const streams = new Map<number, EventSource>()

const activeJobs = computed(() =>
  store.jobs.filter((job) => ['queued', 'running'].includes(job.status)),
)
const finishedJobs = computed(() =>
  store.jobs.filter((job) => ['succeeded', 'failed', 'cancelled'].includes(job.status)),
)

function upsert(job: Job) {
  const index = store.jobs.findIndex((item) => item.id === job.id)
  if (index >= 0) store.jobs[index] = job
  else store.jobs.unshift(job)
}

function syncStreams() {
  for (const job of activeJobs.value) {
    if (streams.has(job.id)) continue
    const source = new EventSource(`/api/jobs/${job.id}/events`)
    const handle = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as Job
        upsert(payload)
        if (['succeeded', 'failed', 'cancelled'].includes(payload.status)) {
          source.close()
          streams.delete(job.id)
        }
      } catch {
        /* ignore malformed frame */
      }
    }
    source.addEventListener('progress', handle as EventListener)
    source.addEventListener('done', handle as EventListener)
    source.onerror = () => {
      source.close()
      streams.delete(job.id)
    }
    streams.set(job.id, source)
  }
  for (const [id, source] of streams) {
    if (!activeJobs.value.some((job) => job.id === id)) {
      source.close()
      streams.delete(id)
    }
  }
}

async function cancel(job: Job) {
  try {
    await store.cancel(job.id)
    toast.push(`任务 #${job.id} 已取消`)
  } catch (error) {
    toast.push((error as Error).message, 'error')
  }
}

watch(
  () => activeJobs.value.map((job) => `${job.id}:${job.status}`).join(','),
  syncStreams,
)

onMounted(() => {
  store.startPolling()
})

onUnmounted(() => {
  store.stopPolling()
  for (const source of streams.values()) source.close()
  streams.clear()
})

function formatTime(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function summarize(job: Job) {
  if (job.error) return job.error
  const result = job.result || {}
  if (job.type === 'scan') return `${result.albums ?? 0} 张专辑 · ${result.files ?? 0} 个文件`
  if (job.type === 'match') return `${result.candidates ?? 0} 个候选`
  if (job.type === 'apply') return `写入 ${result.written ?? 0} / ${result.total ?? 0} 个文件`
  if (job.type === 'rollback') return `还原 ${result.restored ?? 0} / ${result.total ?? 0} 个文件`
  return JSON.stringify(result)
}
</script>

<template>
  <section>
    <div class="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-6">
      <div>
        <p class="eyebrow">05 / TASKS</p>
        <h1 class="mt-3 font-display text-[clamp(2rem,4vw,3.2rem)] leading-none tracking-[-0.02em]">
          任务中心
        </h1>
        <p class="mt-3 font-mono text-[11px] text-ink/45">
          扫描 1 · 检索 3 · 写入 1 · 全部持久化
        </p>
      </div>
      <RouterLink to="/settings" class="stamp py-2.5 transition hover:bg-ink hover:text-paper">
        管理根目录
      </RouterLink>
    </div>

    <div class="mt-8 grid gap-8 lg:grid-cols-[1fr_320px]">
      <div class="space-y-4">
        <div v-if="!activeJobs.length" class="border border-line p-8 text-center">
          <p class="font-display text-xl">当前没有运行中的任务</p>
          <p class="mt-2 font-mono text-[10px] text-ink/40">
            扫描、匹配、写入、回滚都会出现在这里。
          </p>
        </div>
        <JobProgress v-for="job in activeJobs" :key="job.id" :job="job" />
      </div>

      <aside class="space-y-4">
        <div class="border border-line p-5">
          <div class="eyebrow">QUEUE</div>
          <div class="mt-3 space-y-3">
            <div v-for="job in activeJobs" :key="job.id" class="flex items-start gap-2">
              <span class="mt-1 h-1.5 w-1.5 flex-none rounded-full bg-amber"></span>
              <div class="min-w-0">
                <p class="text-[12px]">{{ job.type }} · #{{ job.id }}</p>
                <p class="mt-0.5 font-mono text-[9px] text-ink/35">
                  {{ Math.round((job.progress || 0) * 100) }}% · {{ job.done }}/{{ job.total }}
                </p>
              </div>
            </div>
            <p v-if="!activeJobs.length" class="font-mono text-[10px] text-ink/35">队列为空。</p>
          </div>
        </div>

        <div class="border border-line p-5">
          <div class="eyebrow">CONCURRENCY</div>
          <div class="mt-3 space-y-2 font-mono text-[10px]">
            <div class="leader"><span class="text-ink/40">扫描</span><span class="dots"></span><span>1</span></div>
            <div class="leader"><span class="text-ink/40">远程检索</span><span class="dots"></span><span>3</span></div>
            <div class="leader"><span class="text-ink/40">写入</span><span class="dots"></span><span>1</span></div>
          </div>
        </div>
      </aside>
    </div>

    <div class="mt-10">
      <h2 class="font-display text-2xl">任务历史</h2>
      <div class="mt-4 overflow-x-auto border-t border-line">
        <table class="w-full min-w-[760px] text-left">
          <thead>
            <tr class="border-b border-line/70">
              <th class="eyebrow py-2 font-normal">JOB</th>
              <th class="eyebrow py-2 font-normal">TYPE</th>
              <th class="eyebrow py-2 font-normal">STATUS</th>
              <th class="eyebrow py-2 font-normal">PROGRESS</th>
              <th class="eyebrow py-2 font-normal">RESULT</th>
              <th class="eyebrow py-2 text-right font-normal">WHEN</th>
            </tr>
          </thead>
          <tbody class="font-mono text-[11px] text-ink/60">
            <tr v-for="job in finishedJobs" :key="job.id" class="border-b border-line/50">
              <td class="py-3 text-ink/35">#{{ job.id }}</td>
              <td class="py-3">{{ job.type }}</td>
              <td class="py-3"><StatusStamp :status="job.status" /></td>
              <td class="py-3">{{ Math.round((job.progress || 0) * 100) }}%</td>
              <td class="py-3 max-w-[280px] truncate font-sans text-[12px]">
                {{ summarize(job) }}
              </td>
              <td class="py-3 text-right text-ink/35">{{ formatTime(job.created_at) }}</td>
            </tr>
            <tr v-if="!finishedJobs.length">
              <td colspan="6" class="py-8 text-center font-sans text-[12px] text-ink/40">
                暂无历史任务。
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
