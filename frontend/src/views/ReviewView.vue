<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import type { Plan } from '../api/types'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import CoverPicker from '../components/CoverPicker.vue'
import DiffTable from '../components/DiffTable.vue'
import StatusStamp from '../components/StatusStamp.vue'
import { useToastStore } from '../stores/toast'

const route = useRoute()
const router = useRouter()
const toast = useToastStore()

const plan = ref<Plan | null>(null)
const loading = ref(true)
const applying = ref(false)
const applyOpen = ref(false)
const coverOpen = ref(false)
const covers = ref<{ provider: string; url: string; width?: number; height?: number }[]>([])

const albumId = computed(() => Number(route.params.id))
const selectedCount = computed(
  () => plan.value?.items.filter((item) => item.selected).length || 0,
)

async function load() {
  const planId = Number(route.query.plan)
  if (!planId) {
    router.replace(`/albums/${albumId.value}`)
    return
  }
  loading.value = true
  try {
    plan.value = await api.plans.get(planId)
  } catch (error) {
    toast.push((error as Error).message, 'error')
    router.replace(`/albums/${albumId.value}`)
  } finally {
    loading.value = false
  }
}

async function update(payload: { id: number; selected?: boolean; new_value?: string }) {
  if (!plan.value) return
  try {
    plan.value = await api.plans.patchItems(plan.value.id, [payload])
  } catch (error) {
    toast.push((error as Error).message, 'error')
  }
}

async function toggleAll(selected: boolean) {
  if (!plan.value) return
  try {
    plan.value = await api.plans.patchItems(
      plan.value.id,
      plan.value.items.map((item) => ({ id: item.id, selected })),
    )
  } catch (error) {
    toast.push((error as Error).message, 'error')
  }
}

async function openCovers() {
  if (!plan.value?.candidate_id) {
    toast.push('该计划缺少候选中标，无法获取封面', 'error')
    return
  }
  try {
    covers.value = await api.albums.covers(plan.value.album_id, plan.value.candidate_id)
    coverOpen.value = true
  } catch (error) {
    toast.push((error as Error).message, 'error')
  }
}

async function chooseCover(url: string) {
  if (!plan.value) return
  try {
    await api.albums.setCover(plan.value.album_id, url, plan.value.id)
    plan.value.cover_url = url
    coverOpen.value = false
    toast.push('封面已更新')
  } catch (error) {
    toast.push((error as Error).message, 'error')
  }
}

async function apply() {
  if (!plan.value) return
  applying.value = true
  try {
    await api.plans.apply(plan.value.id, plan.value.cover_url)
    applyOpen.value = false
    toast.push('写入任务已创建，可在任务中心查看进度')
    router.push('/tasks')
  } catch (error) {
    toast.push((error as Error).message, 'error')
  } finally {
    applying.value = false
  }
}

onMounted(load)
</script>

<template>
  <section>
    <div v-if="loading" class="border border-line p-10 text-center font-mono text-[10px] text-ink/40">
      正在读取变更计划…
    </div>

    <div v-else-if="plan">
      <div class="border-b border-line pb-6">
        <p class="eyebrow">04 / REVIEW</p>
        <h1 class="mt-3 font-display text-[clamp(2rem,4vw,3.2rem)] leading-none tracking-[-0.02em]">
          写入前，逐行过目。
        </h1>
        <div class="mt-5 flex flex-wrap items-center gap-x-8 gap-y-2 font-mono text-[10px] text-ink/50">
          <span><span class="text-ink">{{ plan.album.title }}</span> — {{ plan.album.artist }}</span>
          <span>{{ plan.file_count }} 个文件</span>
          <span>{{ plan.total_count }} 个字段</span>
          <span>{{ selectedCount }} 已选</span>
          <StatusStamp :status="plan.status" />
        </div>
      </div>

      <div class="mt-8 grid gap-8 xl:grid-cols-[1fr_300px]">
        <div>
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-3">
              <h2 class="font-display text-2xl">字段差异</h2>
              <span class="stamp text-ink/45">{{ selectedCount }} / {{ plan.total_count }}</span>
            </div>
            <div class="flex border border-line">
              <button
                class="px-3 py-2 font-mono text-[10px] tracking-[0.12em] text-ink/50 transition hover:text-ink"
                @click="toggleAll(true)"
              >
                全选
              </button>
              <button
                class="border-l border-line px-3 py-2 font-mono text-[10px] tracking-[0.12em] text-ink/50 transition hover:text-ink"
                @click="toggleAll(false)"
              >
                全不选
              </button>
              <span class="border-l border-line bg-ink px-3 py-2 font-mono text-[10px] tracking-[0.12em] text-paper">
                {{ plan.policy === 'fill_only' ? '仅补空' : plan.policy === 'overwrite' ? '总是覆盖' : '全部' }}
              </span>
            </div>
          </div>

          <DiffTable class="mt-4" :items="plan.items" @update="update" />
          <p class="mt-3 font-mono text-[9px] text-ink/35">
            取消勾选的字段不会写入；双击新值可编辑。
          </p>

          <div class="mt-10">
            <h2 class="font-display text-2xl">封面</h2>
            <div class="mt-4 flex flex-wrap items-center gap-6 border border-line bg-[#fbf8f1] p-5">
              <div class="text-center">
                <div
                  class="flex h-24 w-24 items-center justify-center overflow-hidden border border-dashed border-line font-mono text-[9px] text-ink/30"
                >
                  <img
                    v-if="plan.cover_url"
                    :src="plan.cover_url"
                    alt=""
                    class="h-full w-full object-cover"
                  />
                  <span v-else>无封面</span>
                </div>
                <p class="mt-2 font-mono text-[9px] text-ink/35">将写入</p>
              </div>
              <span class="text-xl text-copper">→</span>
              <div class="min-w-[180px] flex-1">
                <p class="text-[13px] font-medium">
                  {{ plan.cover_provider || (plan.cover_url ? '自定义封面' : '未选择封面') }}
                </p>
                <p class="mt-1 font-mono text-[10px] leading-relaxed text-ink/40">
                  内嵌至音频标签，并按封面策略写入 cover.jpg
                </p>
                <button
                  class="stamp mt-3 py-2 transition hover:bg-ink hover:text-paper"
                  @click="openCovers"
                >
                  更换封面
                </button>
              </div>
            </div>
          </div>
        </div>

        <aside class="space-y-4">
          <div class="card p-5">
            <div class="eyebrow">WRITE PLAN</div>
            <div class="mt-4 space-y-2.5 font-mono text-[11px]">
              <div class="leader"><span class="text-ink/40">文件</span><span class="dots"></span><span>{{ plan.file_count }}</span></div>
              <div class="leader"><span class="text-ink/40">字段</span><span class="dots"></span><span>{{ selectedCount }}</span></div>
              <div class="leader"><span class="text-ink/40">封面</span><span class="dots"></span><span>{{ plan.cover_url ? 1 : 0 }}</span></div>
              <div class="leader"><span class="text-ink/40">策略</span><span class="dots"></span><span>{{ plan.policy }}</span></div>
              <div class="leader"><span class="text-ink/40">快照</span><span class="dots"></span><span class="text-moss">写入前生成</span></div>
            </div>
            <div class="mt-5 border-t border-line pt-4">
              <p class="font-mono text-[9px] leading-relaxed text-ink/35">
                写入串行执行，单文件失败不影响其余文件。完成后可随时回滚。
              </p>
            </div>
          </div>

          <div class="border border-line p-5">
            <div class="eyebrow">SOURCE</div>
            <div class="mt-3 space-y-2 font-mono text-[10px] text-ink/55">
              <div class="leader">
                <span>候选来源</span><span class="dots"></span>
                <span>{{ plan.release?.provider || '—' }}</span>
              </div>
              <div class="leader">
                <span>发行标题</span><span class="dots"></span>
                <span class="truncate">{{ plan.release?.title || '—' }}</span>
              </div>
              <div class="leader">
                <span>年份</span><span class="dots"></span>
                <span>{{ plan.release?.year || '—' }}</span>
              </div>
            </div>
          </div>
        </aside>
      </div>

      <div class="sticky bottom-4 z-30 mt-8 flex flex-wrap items-center gap-3 border border-ink bg-ink px-5 py-4 text-paper shadow-2xl">
        <button
          class="font-mono text-[10px] tracking-[0.16em] text-paper/50 transition hover:text-paper"
          @click="router.push(`/albums/${plan.album_id}`)"
        >
          取消
        </button>
        <div class="ml-auto flex items-center gap-4">
          <span class="font-mono text-[10px] text-paper/50">
            已选 {{ selectedCount }} 项 · {{ plan.file_count }} 个文件
          </span>
          <button
            class="bg-copper px-6 py-2.5 font-mono text-[11px] tracking-[0.18em] text-paper transition hover:bg-paper hover:text-ink disabled:opacity-40"
            :disabled="!selectedCount || plan.status === 'applied'"
            @click="applyOpen = true"
          >
            确认并写入 →
          </button>
        </div>
      </div>
    </div>

    <ConfirmDialog
      :open="applyOpen"
      kicker="WRITE / CONFIRM"
      :title="`写入 ${plan?.file_count || 0} 个文件？`"
      confirm-text="确认写入"
      @cancel="applyOpen = false"
      @confirm="apply"
    >
      <p>将向 {{ plan?.album.title }} 的 {{ plan?.file_count }} 个文件写入 {{ selectedCount }} 个字段。</p>
      <div class="mt-4 space-y-2 border-t border-line pt-3 font-mono text-[10px] text-ink/50">
        <div class="leader"><span>覆盖策略</span><span class="dots"></span><span>{{ plan?.policy }}</span></div>
        <div class="leader"><span>写入前快照</span><span class="dots"></span><span class="text-moss">自动生成</span></div>
        <div class="leader"><span>写入方式</span><span class="dots"></span><span>串行 · 写后校验</span></div>
      </div>
      <p class="mt-4 text-[11px] text-ink/40">完成后可在历史与回滚中恢复。</p>
    </ConfirmDialog>

    <CoverPicker
      :open="coverOpen"
      :covers="covers"
      :current="plan?.cover_url"
      @select="chooseCover"
      @close="coverOpen = false"
    />
  </section>
</template>
