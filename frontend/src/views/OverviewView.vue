<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { Album, Job } from '../api/types'
import CoverArt from '../components/CoverArt.vue'
import JobProgress from '../components/JobProgress.vue'
import StatusStamp from '../components/StatusStamp.vue'

const stats = ref({
  albums: 0,
  files: 0,
  pending: 0,
  roots: 0,
  running_jobs: 0,
  recent_albums: [] as Album[],
})
const jobs = ref<Job[]>([])
const reviewAlbums = ref<Album[]>([])
const loading = ref(true)

const activeJob = computed(
  () => jobs.value.find((job) => job.status === 'running' || job.status === 'queued') || null,
)

function formatTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

async function load() {
  loading.value = true
  try {
    const [statsData, jobData, pending, unmatched] = await Promise.all([
      api.stats(),
      api.jobs.list(6),
      api.albums.list({ status: 'pending', page_size: 3 }),
      api.albums.list({ status: 'unmatched', page_size: 3 }),
    ])
    stats.value = statsData
    jobs.value = jobData
    reviewAlbums.value = [...pending.items, ...unmatched.items].slice(0, 5)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section>
    <div class="flex flex-wrap items-end justify-between gap-8 border-b border-line pb-8">
      <div class="max-w-2xl">
        <p class="eyebrow">01 / OVERVIEW</p>
        <h1 class="mt-3 font-display text-[clamp(2.5rem,5vw,4.4rem)] leading-[0.95] tracking-[-0.02em]">
          唱片柜，<em class="italic text-copper">已索引</em>。
        </h1>
        <p class="mt-5 max-w-lg text-sm leading-relaxed text-ink/55">
          {{ stats.files.toLocaleString() }} 个文件完成归档，{{ stats.albums }} 张专辑等待或已经完成裁决。每一次写入都会留下快照，随时可以退回。
        </p>
      </div>
      <div class="flex gap-8 sm:gap-12">
        <div>
          <div class="font-display text-[3.2rem] leading-none tracking-tight">
            {{ stats.files.toLocaleString() }}
          </div>
          <div class="eyebrow mt-2">FILES</div>
        </div>
        <div>
          <div class="font-display text-[3.2rem] leading-none tracking-tight">{{ stats.albums }}</div>
          <div class="eyebrow mt-2">ALBUMS</div>
        </div>
        <div>
          <div class="font-display text-[3.2rem] leading-none tracking-tight text-copper">
            {{ stats.pending }}
          </div>
          <div class="eyebrow mt-2">TO REVIEW</div>
        </div>
      </div>
    </div>

    <div class="mt-10 grid gap-10 lg:grid-cols-12">
      <div class="lg:col-span-8">
        <div class="flex items-center justify-between">
          <h2 class="font-display text-2xl">待你裁决</h2>
          <RouterLink class="eyebrow transition hover:text-copper" to="/albums">
            全部 {{ stats.pending }} 张 →
          </RouterLink>
        </div>

        <div class="mt-4 stagger border-t border-line">
          <p v-if="!reviewAlbums.length" class="border-b border-line/70 py-6 text-center text-[12px] text-ink/40">
            没有待处理专辑。先扫描曲库，或所有专辑都已完成匹配。
          </p>
          <RouterLink
            v-for="album in reviewAlbums"
            :key="album.id"
            :to="`/albums/${album.id}`"
            class="group flex items-center gap-4 border-b border-line/70 py-3.5 transition hover:bg-paper2/40"
          >
            <div class="h-12 w-12 flex-none overflow-hidden border border-line">
              <CoverArt :album="album" :src="album.cover_url || album.selected_cover_url" />
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <h3 class="truncate font-display text-base">{{ album.title || '未知专辑' }}</h3>
                <StatusStamp :status="album.status" />
              </div>
              <div class="leader mt-1.5 font-mono text-[10px] text-ink/45">
                <span>{{ album.artist || '未知艺术家' }} · {{ album.track_count }} 曲 · {{ album.kind === 'whole' ? '整轨' : '分轨' }}</span>
                <span class="dots"></span>
                <span>{{ album.confidence.toFixed(2) }}</span>
              </div>
            </div>
            <span class="hidden font-mono text-[10px] text-copper sm:block">查看 →</span>
          </RouterLink>
        </div>

        <div class="mt-10">
          <h2 class="font-display text-2xl">最近任务</h2>
          <div class="mt-4 overflow-x-auto border-t border-line">
            <table class="w-full min-w-[560px] text-left">
              <thead>
                <tr class="border-b border-line/70">
                  <th class="eyebrow py-2 font-normal">JOB</th>
                  <th class="eyebrow py-2 font-normal">TYPE</th>
                  <th class="eyebrow py-2 font-normal">STATUS</th>
                  <th class="eyebrow py-2 font-normal">PROGRESS</th>
                  <th class="eyebrow py-2 text-right font-normal">WHEN</th>
                </tr>
              </thead>
              <tbody class="font-mono text-[11px] text-ink/65">
                <tr v-for="job in jobs.slice(0, 5)" :key="job.id" class="border-b border-line/50">
                  <td class="py-3 text-ink/35">#{{ job.id }}</td>
                  <td class="py-3">{{ job.type }}</td>
                  <td class="py-3"><StatusStamp :status="job.status" /></td>
                  <td class="py-3">{{ Math.round((job.progress || 0) * 100) }}%</td>
                  <td class="py-3 text-right text-ink/35">{{ formatTime(job.created_at) }}</td>
                </tr>
                <tr v-if="!jobs.length">
                  <td colspan="5" class="py-6 text-center font-sans text-[12px] text-ink/40">
                    还没有任务记录。
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="lg:col-span-4">
        <JobProgress v-if="activeJob" :job="activeJob" />
        <div v-else class="card p-5">
          <div class="eyebrow">IDLE</div>
          <h3 class="mt-2 font-display text-xl">当前没有运行中的任务</h3>
          <p class="mt-2 font-mono text-[10px] leading-relaxed text-ink/40">
            扫描、匹配、写入与回滚都会进入任务队列，可中断续跑。
          </p>
          <RouterLink
            to="/tasks"
            class="mt-4 inline-block border border-line px-4 py-2 font-mono text-[10px] tracking-[0.16em] transition hover:border-ink"
          >
            打开任务中心
          </RouterLink>
        </div>

        <div class="mt-6 border border-line p-5">
          <div class="flex items-center justify-between">
            <span class="eyebrow">RECENT ALBUMS</span>
            <span class="font-mono text-[9px] text-ink/35">{{ stats.roots }} 个</span>
          </div>
          <div class="mt-4 space-y-3">
            <div
              v-for="album in stats.recent_albums.slice(0, 3)"
              :key="album.id"
              class="flex items-center gap-3"
            >
              <div class="h-9 w-9 flex-none overflow-hidden border border-line">
                <CoverArt :album="album" :src="album.cover_url || album.selected_cover_url" />
              </div>
              <div class="min-w-0 flex-1">
                <p class="truncate text-[12px]">{{ album.title || '未知专辑' }}</p>
                <p class="truncate font-mono text-[9px] text-ink/35">{{ album.rel_path }}</p>
              </div>
            </div>
            <p v-if="!stats.recent_albums.length" class="font-mono text-[10px] text-ink/35">
              尚未扫描媒体库。
            </p>
          </div>
          <RouterLink
            to="/settings"
            class="mt-4 block border-t border-line pt-3 font-mono text-[10px] text-copper"
          >
            管理根目录与数据源 →
          </RouterLink>
        </div>
      </div>
    </div>
  </section>
</template>
