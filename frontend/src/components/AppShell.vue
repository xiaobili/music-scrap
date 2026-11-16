<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLibraryStore } from '../stores/library'
import { useToastStore } from '../stores/toast'

const route = useRoute()
const router = useRouter()
const library = useLibraryStore()
const toast = useToastStore()

const drawer = ref(false)
const query = ref('')
const scanning = ref(false)

const nav = [
  { to: '/', idx: '01', label: '概览', en: 'OVERVIEW' },
  { to: '/albums', idx: '02', label: '专辑库', en: 'LIBRARY' },
  { to: '/tasks', idx: '03', label: '任务中心', en: 'TASKS' },
  { to: '/history', idx: '04', label: '历史与回滚', en: 'HISTORY' },
  { to: '/settings', idx: '05', label: '设置', en: 'SETTINGS' },
]

const crumb = computed(() => String(route.meta.label || 'OVERVIEW'))

function isActive(to: string) {
  if (to === '/') return route.path === '/'
  return route.path === to || route.path.startsWith(`${to}/`) ||
    (to === '/albums' && route.name === 'album') ||
    (to === '/albums' && route.name === 'review')
}

async function scan() {
  const root = library.roots.find((item) => item.enabled) || library.roots[0]
  if (!root) {
    toast.push('请先在设置中添加媒体库根目录', 'error')
    router.push('/settings')
    return
  }
  scanning.value = true
  try {
    const job = await library.scan(root.id)
    toast.push(`扫描任务 #${job.job_id} 已创建`)
    router.push('/tasks')
  } catch (error) {
    toast.push((error as Error).message, 'error')
  } finally {
    scanning.value = false
  }
}

function search() {
  const text = query.value.trim()
  if (!text) return
  router.push({ path: '/albums', query: { q: text } })
  query.value = ''
  drawer.value = false
}

onMounted(() => {
  library.loadRoots().catch(() => undefined)
})
</script>

<template>
  <div class="flex min-h-screen">
    <aside
      class="fixed inset-y-0 left-0 z-50 flex w-[248px] flex-col bg-ink text-paper transition-transform duration-300"
      :class="drawer ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'"
    >
      <div class="border-b border-paper/10 px-6 pb-6 pt-7">
        <RouterLink to="/" class="flex items-center gap-3" @click="drawer = false">
          <span class="vinyl"></span>
          <div>
            <div class="font-display text-xl italic leading-none">
              music<span class="not-italic text-copper">·</span>scrap
            </div>
            <div class="mt-1.5 font-mono text-[8px] tracking-[0.28em] text-paper/35">
              METADATA ATELIER
            </div>
          </div>
        </RouterLink>
      </div>

      <nav class="flex-1 space-y-0.5 px-2 py-4">
        <RouterLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="nav-item"
          :class="{ 'is-active': isActive(item.to) }"
          @click="drawer = false"
        >
          <span class="nav-idx">{{ item.idx }}</span>
          <span class="flex-1">
            {{ item.label }}
            <span class="mt-0.5 block font-mono text-[9px] tracking-[0.2em] opacity-40">
              {{ item.en }}
            </span>
          </span>
        </RouterLink>
      </nav>

      <div class="border-t border-paper/10 px-5 py-5">
        <div class="font-mono text-[10px] text-paper/35">NAS · LOCAL</div>
        <div class="mt-2 flex items-center gap-2 font-mono text-[10px] text-paper/50">
          <span class="h-1.5 w-1.5 rounded-full bg-moss"></span>服务正常 · v0.1
        </div>
      </div>
    </aside>

    <div v-if="drawer" class="fixed inset-0 z-40 bg-ink/50 lg:hidden" @click="drawer = false"></div>

    <div class="min-w-0 flex-1 lg:pl-[248px]">
      <header class="sticky top-0 z-30 border-b border-line bg-paper/85 backdrop-blur">
        <div class="flex h-16 items-center gap-3 px-5 sm:px-8">
          <button
            class="border border-line p-2 lg:hidden"
            aria-label="菜单"
            @click="drawer = true"
          >
            <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
              <path stroke-linecap="round" d="M3.75 6.75h16.5M3.75 12h16.5M3.75 17.25h16.5" />
            </svg>
          </button>
          <div class="hidden font-mono text-[10px] tracking-[0.2em] text-ink/35 sm:block">
            LIBRARY / <span class="text-ink/70">{{ crumb }}</span>
          </div>
          <div class="ml-auto flex items-center gap-3">
            <div class="relative hidden md:block">
              <svg
                class="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink/35"
                fill="none"
                stroke="currentColor"
                stroke-width="1.6"
                viewBox="0 0 24 24"
              >
                <circle cx="11" cy="11" r="7" />
                <path stroke-linecap="round" d="m16.5 16.5 4 4" />
              </svg>
              <input
                v-model="query"
                placeholder="搜索专辑、艺术家、目录…"
                class="w-72 border border-line bg-transparent py-2 pl-8 pr-14 font-mono text-[11px] placeholder:text-ink/30 focus:border-ink focus:outline-none"
                @keyup.enter="search"
              />
              <span
                class="absolute right-1.5 top-1/2 -translate-y-1/2 border border-line px-1.5 py-0.5 font-mono text-[9px] text-ink/35"
              >
                ↵
              </span>
            </div>
            <button class="stamp py-2.5 transition hover:bg-ink hover:text-paper" @click="scan">
              {{ scanning ? '正在创建…' : '扫描曲库' }}
              <svg class="h-3 w-3" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 12h16m-6-6 6 6-6 6" />
              </svg>
            </button>
          </div>
        </div>
      </header>

      <main class="mx-auto max-w-[1500px] px-5 py-8 sm:px-8 lg:py-10">
        <slot />
      </main>

      <footer class="border-t border-line px-5 py-6 sm:px-8">
        <div
          class="mx-auto flex max-w-[1500px] flex-wrap items-center justify-between gap-2 font-mono text-[9px] tracking-[0.14em] text-ink/30"
        >
          <span>MUSIC·SCRAP</span>
          <span>ALL WRITES ARE REVERSIBLE</span>
        </div>
      </footer>
    </div>
  </div>
</template>
