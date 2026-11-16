<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import AlbumCard from '../components/AlbumCard.vue'
import { useLibraryStore } from '../stores/library'
import { useToastStore } from '../stores/toast'

const library = useLibraryStore()
const route = useRoute()
const router = useRouter()
const toast = useToastStore()

const selected = ref<Set<number>>(new Set())
const qInput = ref(String(route.query.q || ''))
const batchLoading = ref(false)
let searchTimer: number | null = null

const statuses = [
  { value: '', label: '全部' },
  { value: 'matched', label: '已匹配' },
  { value: 'pending', label: '待选择' },
  { value: 'unmatched', label: '未匹配' },
]

function toggle(id: number) {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

function clearSelection() {
  selected.value = new Set()
}

async function applyFilters() {
  library.filters.page = 1
  await library.loadAlbums()
}

function setPage(page: number) {
  library.filters.page = page
  library.loadAlbums()
}

async function batchMatch() {
  if (!selected.value.size) return
  batchLoading.value = true
  try {
    const result = await api.albums.batchMatch([...selected.value])
    toast.push(`已创建 ${result.job_ids.length} 个匹配任务`)
    clearSelection()
    router.push('/tasks')
  } catch (error) {
    toast.push((error as Error).message, 'error')
  } finally {
    batchLoading.value = false
  }
}

watch(qInput, (value) => {
  if (searchTimer) window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    library.filters.q = value
    library.filters.page = 1
    library.loadAlbums()
    router.replace({ path: '/albums', query: value ? { q: value } : {} })
  }, 350)
})

watch(
  () => route.query.q,
  (value) => {
    const text = String(value || '')
    if (text !== qInput.value) qInput.value = text
  },
)

watch(
  () => [library.filters.status, library.filters.kind, library.filters.root_id],
  applyFilters,
)

onMounted(async () => {
  library.filters.q = String(route.query.q || '')
  await library.loadRoots().catch(() => undefined)
  await library.loadAlbums()
})

const pageCount = () => Math.max(1, Math.ceil(library.total / library.filters.page_size))
</script>

<template>
  <section>
    <div class="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-6">
      <div>
        <p class="eyebrow">02 / LIBRARY</p>
        <h1 class="mt-3 font-display text-[clamp(2rem,4vw,3.2rem)] leading-none tracking-[-0.02em]">
          专辑库
        </h1>
        <p class="mt-3 font-mono text-[11px] text-ink/45">
          {{ library.total }} 张专辑 · {{ library.roots.length }} 个根目录
        </p>
      </div>
      <div class="flex items-center gap-2">
        <div class="relative">
          <input
            v-model="qInput"
            placeholder="筛选标题、艺术家、目录"
            class="w-52 border border-line bg-transparent px-3 py-2 font-mono text-[10px] placeholder:text-ink/30 focus:border-ink focus:outline-none"
          />
        </div>
        <RouterLink
          to="/settings"
          class="stamp py-2.5 transition hover:bg-ink hover:text-paper"
        >
          管理根目录
        </RouterLink>
      </div>
    </div>

    <div class="mt-8 grid gap-10 lg:grid-cols-[190px_1fr]">
      <aside class="space-y-7">
        <div>
          <h3 class="eyebrow mb-3">STATUS</h3>
          <div class="space-y-1">
            <button
              v-for="item in statuses"
              :key="item.value"
              class="flex w-full items-center justify-between border px-3 py-2 font-mono text-[10px] tracking-[0.1em] transition"
              :class="
                library.filters.status === item.value
                  ? 'border-ink bg-ink text-paper'
                  : 'border-transparent text-ink/55 hover:border-line'
              "
              @click="library.filters.status = item.value"
            >
              {{ item.label }}
              <span v-if="item.value === ''" class="opacity-50">{{ library.total }}</span>
            </button>
          </div>
        </div>

        <div>
          <h3 class="eyebrow mb-3">FORMAT</h3>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="item in [
                { value: '', label: '全部' },
                { value: 'whole', label: '整轨' },
                { value: 'split', label: '分轨' },
              ]"
              :key="item.value"
              class="stamp py-2"
              :class="
                library.filters.kind === item.value
                  ? 'border-ink bg-ink text-paper'
                  : 'text-ink/55'
              "
              @click="library.filters.kind = item.value"
            >
              {{ item.label }}
            </button>
          </div>
        </div>

        <div>
          <h3 class="eyebrow mb-3">ROOT</h3>
          <div class="space-y-1 font-mono text-[10px] text-ink/55">
            <button
              class="flex w-full items-center gap-2 px-1 py-1.5 text-left hover:text-ink"
              @click="library.filters.root_id = ''"
            >
              <span class="h-1.5 w-1.5" :class="library.filters.root_id === '' ? 'bg-copper' : 'bg-line'"></span>
              全部根目录
            </button>
            <button
              v-for="root in library.roots"
              :key="root.id"
              class="flex w-full items-center gap-2 truncate px-1 py-1.5 text-left hover:text-ink"
              @click="library.filters.root_id = root.id"
            >
              <span
                class="h-1.5 w-1.5 flex-none"
                :class="library.filters.root_id === root.id ? 'bg-copper' : 'bg-line'"
              ></span>
              <span class="truncate">{{ root.path }}</span>
            </button>
          </div>
        </div>
      </aside>

      <div>
        <div v-if="library.loading" class="border border-line p-10 text-center font-mono text-[10px] text-ink/40">
          正在读取专辑索引…
        </div>
        <div
          v-else
          class="grid grid-cols-2 gap-x-5 gap-y-9 md:grid-cols-3 xl:grid-cols-4"
        >
          <AlbumCard
            v-for="album in library.albums"
            :key="album.id"
            :album="album"
            :selected="selected.has(album.id)"
            @toggle="toggle"
          />
        </div>

        <div v-if="!library.loading && !library.albums.length" class="border border-line p-10 text-center">
          <p class="font-display text-xl">这里还没有专辑</p>
          <p class="mt-2 font-mono text-[10px] text-ink/40">在设置中添加根目录并执行扫描。</p>
          <RouterLink to="/settings" class="stamp mt-4 inline-block py-2">前往设置</RouterLink>
        </div>

        <div class="mt-10 flex items-center justify-between border-t border-line pt-4">
          <span class="font-mono text-[10px] text-ink/40">
            第 {{ library.filters.page }} / {{ pageCount() }} 页 · 共 {{ library.total }} 张
          </span>
          <div class="flex gap-1">
            <button
              class="stamp px-3 py-2"
              :class="library.filters.page <= 1 ? 'text-ink/25' : 'text-ink/55 hover:border-ink'"
              :disabled="library.filters.page <= 1"
              @click="setPage(library.filters.page - 1)"
            >
              ←
            </button>
            <button
              class="stamp bg-ink px-3 py-2 text-paper"
            >
              {{ library.filters.page }}
            </button>
            <button
              class="stamp px-3 py-2"
              :class="
                library.filters.page >= pageCount() ? 'text-ink/25' : 'text-ink/55 hover:border-ink'
              "
              :disabled="library.filters.page >= pageCount()"
              @click="setPage(library.filters.page + 1)"
            >
              →
            </button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="selected.size"
      class="fixed bottom-6 left-1/2 z-40 flex -translate-x-1/2 items-center gap-5 border border-ink bg-ink px-5 py-3 text-paper shadow-2xl lg:left-[calc(50%+124px)]"
    >
      <span class="font-mono text-[10px] tracking-[0.14em]">{{ selected.size }} 张专辑已选</span>
      <span class="h-4 w-px bg-paper/20"></span>
      <button class="font-mono text-[10px] tracking-[0.14em] text-paper/60 hover:text-paper" @click="clearSelection">
        清除
      </button>
      <button
        class="bg-copper px-4 py-2 font-mono text-[10px] tracking-[0.14em] transition hover:bg-paper hover:text-ink disabled:opacity-50"
        :disabled="batchLoading"
        @click="batchMatch"
      >
        {{ batchLoading ? '创建中…' : '批量匹配 →' }}
      </button>
    </div>
  </section>
</template>
