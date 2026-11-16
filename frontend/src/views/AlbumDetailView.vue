<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import type { Album, Candidate } from '../api/types'
import CandidateTable from '../components/CandidateTable.vue'
import CoverArt from '../components/CoverArt.vue'
import CoverPicker from '../components/CoverPicker.vue'
import StatusStamp from '../components/StatusStamp.vue'
import { useToastStore } from '../stores/toast'

const route = useRoute()
const router = useRouter()
const toast = useToastStore()

const album = ref<Album | null>(null)
const candidates = ref<Candidate[]>([])
const loading = ref(true)
const searching = ref(false)
const selectingId = ref<number | null>(null)
const manualQuery = ref('')
const planId = ref<number | null>(null)
const coverOpen = ref(false)
const covers = ref<{ provider: string; url: string; width?: number; height?: number }[]>([])

const albumId = computed(() => Number(route.params.id))

const tagRows = computed(() => {
  const tags = album.value?.tags || {}
  return [
    ['ALBUM', tags.ALBUM?.[0]],
    ['ALBUMARTIST', tags.ALBUMARTIST?.[0]],
    ['DATE', tags.DATE?.[0]],
    ['LABEL', tags.LABEL?.[0]],
    ['CATALOGNUMBER', tags.CATALOGNUMBER?.[0]],
    ['MUSICBRAINZ_ALBUMID', tags.MUSICBRAINZ_ALBUMID?.[0]],
  ] as [string, string | undefined][]
})

function formatDuration(ms: number | null | undefined) {
  if (!ms) return '—'
  const total = Math.round(ms / 1000)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

async function load() {
  loading.value = true
  try {
    const [detail, candidateList] = await Promise.all([
      api.albums.detail(albumId.value),
      api.albums.candidates(albumId.value),
    ])
    album.value = detail
    candidates.value = candidateList
  } catch (error) {
    toast.push((error as Error).message, 'error')
  } finally {
    loading.value = false
  }
}

async function search() {
  if (!manualQuery.value.trim()) return
  searching.value = true
  try {
    candidates.value = await api.albums.search(albumId.value, manualQuery.value.trim())
    toast.push(`检索到 ${candidates.value.length} 个候选`)
  } catch (error) {
    toast.push((error as Error).message, 'error')
  } finally {
    searching.value = false
  }
}

async function selectCandidate(candidate: Candidate) {
  selectingId.value = candidate.id
  try {
    const plan = await api.albums.select(albumId.value, candidate.id)
    planId.value = plan.id
    router.push({ path: `/albums/${albumId.value}/review`, query: { plan: plan.id } })
  } catch (error) {
    toast.push((error as Error).message, 'error')
  } finally {
    selectingId.value = null
  }
}

async function openCovers() {
  const candidate = candidates.value[0]
  if (!candidate) {
    toast.push('先检索并选择一个候选，再挑选封面', 'error')
    return
  }
  try {
    covers.value = await api.albums.covers(albumId.value, candidate.id)
    coverOpen.value = true
  } catch (error) {
    toast.push((error as Error).message, 'error')
  }
}

async function chooseCover(url: string) {
  try {
    await api.albums.setCover(albumId.value, url, planId.value || undefined)
    if (album.value) album.value.selected_cover_url = url
    coverOpen.value = false
    toast.push('封面已选定，将在写入时应用')
  } catch (error) {
    toast.push((error as Error).message, 'error')
  }
}

function openOriginal() {
  const url = album.value?.cover_url || album.value?.selected_cover_url
  if (url) window.open(url, '_blank')
}

onMounted(load)
</script>

<template>
  <section>
    <RouterLink to="/albums" class="eyebrow transition hover:text-copper">← 返回专辑库</RouterLink>

    <div v-if="loading" class="mt-8 border border-line p-10 text-center font-mono text-[10px] text-ink/40">
      正在读取专辑…
    </div>

    <div v-else-if="album" class="mt-7 grid gap-10 lg:grid-cols-[minmax(0,360px)_1fr]">
      <div>
        <div class="cover-frame">
          <div class="aspect-square overflow-hidden">
            <CoverArt
              :album="album"
              :src="album.selected_cover_url || album.cover_url"
            />
          </div>
        </div>
        <div class="mt-5 grid grid-cols-2 gap-2">
          <button
            class="border border-line py-2.5 font-mono text-[10px] tracking-[0.16em] transition hover:border-ink"
            @click="openCovers"
          >
            更换封面
          </button>
          <button
            class="border border-line py-2.5 font-mono text-[10px] tracking-[0.16em] transition hover:border-ink disabled:opacity-40"
            :disabled="!album.cover_url && !album.selected_cover_url"
            @click="openOriginal"
          >
            查看原图
          </button>
        </div>

        <div class="mt-6 border border-line p-4">
          <div class="flex items-center justify-between">
            <span class="eyebrow">COVER</span>
            <span class="font-mono text-[9px] text-ink/35">
              {{ album.has_cover ? '已内嵌' : album.selected_cover_url ? '待写入' : '缺失' }}
            </span>
          </div>
          <p class="mt-3 font-mono text-[9px] leading-relaxed text-ink/40">
            写入时统一转为 JPEG，内嵌至音频标签，并在专辑目录生成 cover.jpg。
          </p>
        </div>
      </div>

      <div class="min-w-0">
        <p class="eyebrow">RELEASE / {{ album.kind === 'whole' ? 'WHOLE' : 'SPLIT' }}</p>
        <h1 class="mt-3 font-display text-[clamp(2.2rem,4vw,3.6rem)] leading-none tracking-[-0.02em]">
          {{ album.title || '未知专辑' }}
        </h1>
        <p class="mt-3 font-display text-xl italic text-ink/55">{{ album.artist || '未知艺术家' }}</p>

        <div class="mt-5 flex flex-wrap gap-2">
          <span v-if="album.year" class="stamp text-ink/55">{{ album.year }}</span>
          <span class="stamp text-ink/55">{{ album.track_count }} 曲</span>
          <span class="stamp text-ink/55">{{ album.kind === 'whole' ? '整轨' : '分轨' }}</span>
          <StatusStamp :status="album.status" />
          <span class="stamp text-ink/55">{{ album.confidence.toFixed(2) }}</span>
        </div>

        <div class="mt-8 grid gap-x-8 gap-y-2.5 border-t border-line pt-5 sm:grid-cols-2">
          <div v-for="[field, value] in tagRows" :key="field" class="leader font-mono text-[11px]">
            <span class="w-36 flex-none text-ink/35">{{ field }}</span>
            <span class="dots"></span>
            <span :class="value ? '' : 'text-ink/25'">{{ value || '— 空' }}</span>
          </div>
        </div>
        <p class="mt-3 font-mono text-[9px] text-ink/35">
          目录 {{ album.directory || album.rel_path }}
        </p>

        <div class="mt-10">
          <div class="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 class="font-display text-2xl">候选匹配</h2>
              <p class="mt-1 font-mono text-[10px] text-ink/40">
                按置信度排序 · {{ candidates.length }} 个候选
              </p>
            </div>
            <div class="flex gap-2">
              <input
                v-model="manualQuery"
                placeholder="手动关键词"
                class="w-44 border border-line bg-transparent px-3 py-2 font-mono text-[10px] placeholder:text-ink/30 focus:border-ink focus:outline-none"
                @keyup.enter="search"
              />
              <button
                class="stamp py-2 transition hover:bg-ink hover:text-paper disabled:opacity-40"
                :disabled="searching || !manualQuery.trim()"
                @click="search"
              >
                {{ searching ? '检索中…' : '重新检索' }}
              </button>
            </div>
          </div>

          <CandidateTable
            class="mt-4"
            :candidates="candidates"
            :selecting-id="selectingId"
            @select="selectCandidate"
          />
        </div>

        <div class="mt-10">
          <div class="flex items-end justify-between">
            <h2 class="font-display text-2xl">曲目</h2>
            <span class="font-mono text-[10px] text-ink/40">{{ album.tracks?.length || 0 }} 个文件</span>
          </div>
          <div class="mt-4 overflow-x-auto border-t border-line">
            <table class="w-full min-w-[620px] text-left">
              <thead>
                <tr class="border-b border-line/70">
                  <th class="eyebrow w-10 py-2 font-normal">#</th>
                  <th class="eyebrow py-2 font-normal">TITLE</th>
                  <th class="eyebrow py-2 font-normal">DURATION</th>
                  <th class="eyebrow py-2 font-normal">FORMAT</th>
                  <th class="eyebrow py-2 text-right font-normal">STATE</th>
                </tr>
              </thead>
              <tbody class="text-[13px]">
                <tr
                  v-for="track in album.tracks"
                  :key="track.id"
                  class="border-b border-line/50"
                >
                  <td class="py-2.5 font-mono text-[11px] text-ink/35">
                    {{ String(track.track_no || 0).padStart(2, '0') }}
                  </td>
                  <td class="py-2.5">
                    {{ album.track_tags?.[String(track.id)]?.TITLE?.[0] || track.title || '—' }}
                  </td>
                  <td class="py-2.5 font-mono text-[11px] text-ink/45">
                    {{ formatDuration(track.duration_ms) }}
                  </td>
                  <td class="py-2.5 font-mono text-[10px] text-ink/40">
                    {{ track.format }}
                    <span v-if="track.sample_rate"> · {{ Math.round(track.sample_rate / 1000) }}kHz</span>
                  </td>
                  <td class="py-2.5 text-right">
                    <span
                      class="stamp"
                      :class="album.track_tags?.[String(track.id)]?.TITLE ? 'text-moss' : 'text-amber'"
                    >
                      {{ album.track_tags?.[String(track.id)]?.TITLE ? '有标签' : '待补' }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="mt-10 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-5">
          <p class="max-w-md font-mono text-[10px] leading-relaxed text-ink/40">
            选择候选后将生成字段级变更计划，预览确认后才写入文件。
          </p>
          <button
            class="bg-ink px-6 py-3 font-mono text-[11px] tracking-[0.18em] text-paper transition hover:bg-copper disabled:opacity-40"
            :disabled="!candidates.length"
            @click="candidates[0] && selectCandidate(candidates[0])"
          >
            使用推荐候选 →
          </button>
        </div>
      </div>
    </div>

    <CoverPicker
      :open="coverOpen"
      :covers="covers"
      :current="album?.selected_cover_url"
      @select="chooseCover"
      @close="coverOpen = false"
    />
  </section>
</template>
