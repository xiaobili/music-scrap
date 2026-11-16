<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { Root, SettingsResponse } from '../api/types'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import StatusStamp from '../components/StatusStamp.vue'
import { useToastStore } from '../stores/toast'

const toast = useToastStore()
const router = useRouter()

const settings = ref<SettingsResponse | null>(null)
const roots = ref<Root[]>([])
const loading = ref(true)
const saving = ref(false)
const newRoot = ref('')
const deleting = ref<Root | null>(null)

const form = reactive({
  field_policy: 'fill_only',
  cover_policy: 'if_missing',
  safe_mode: false,
})

const creds = reactive<Record<string, string>>({})
const enabled = reactive<Record<string, boolean>>({})

const credLabels: Record<string, string> = {
  'acoustid.apikey': 'API Key',
  'discogs.token': 'Token',
  'spotify.client_id': 'Client ID',
  'spotify.client_secret': 'Client Secret',
  'netease.cookie': 'Cookie',
}

function hydrate(data: SettingsResponse) {
  settings.value = data
  form.field_policy = String(data.values.field_policy || 'fill_only')
  form.cover_policy = String(data.values.cover_policy || 'if_missing')
  form.safe_mode = Boolean(data.values.safe_mode)
  for (const provider of data.providers) {
    enabled[provider.id] = Boolean(provider.enabled)
  }
}

async function load() {
  loading.value = true
  try {
    const [settingsData, rootData] = await Promise.all([api.settings.get(), api.roots.list()])
    hydrate(settingsData)
    roots.value = rootData
  } catch (error) {
    toast.push((error as Error).message, 'error')
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!settings.value) return
  saving.value = true
  try {
    const values: Record<string, unknown> = {
      field_policy: form.field_policy,
      cover_policy: form.cover_policy,
      safe_mode: form.safe_mode,
    }
    for (const provider of settings.value.providers) {
      values[`${provider.id}.enabled`] = Boolean(enabled[provider.id])
    }
    for (const [key, value] of Object.entries(creds)) {
      if (value.trim()) values[key] = value.trim()
    }
    const updated = await api.settings.update(values)
    hydrate(updated)
    for (const key of Object.keys(creds)) creds[key] = ''
    toast.push('设置已保存')
  } catch (error) {
    toast.push((error as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function addRoot() {
  if (!newRoot.value.trim()) return
  try {
    const root = await api.roots.create(newRoot.value.trim())
    roots.value.push(root)
    newRoot.value = ''
    toast.push('根目录已添加，可以开始扫描')
  } catch (error) {
    toast.push((error as Error).message, 'error')
  }
}

async function toggleRoot(root: Root) {
  try {
    const updated = await api.roots.update(root.id, !root.enabled)
    roots.value = roots.value.map((item) => (item.id === updated.id ? updated : item))
  } catch (error) {
    toast.push((error as Error).message, 'error')
  }
}

async function scanRoot(root: Root) {
  try {
    const job = await api.roots.scan(root.id)
    toast.push(`扫描任务 #${job.job_id} 已创建`)
    router.push('/tasks')
  } catch (error) {
    toast.push((error as Error).message, 'error')
  }
}

async function removeRoot() {
  if (!deleting.value) return
  try {
    await api.roots.remove(deleting.value.id)
    roots.value = roots.value.filter((root) => root.id !== deleting.value?.id)
    deleting.value = null
    toast.push('根目录已移除，音频文件未被删除')
  } catch (error) {
    toast.push((error as Error).message, 'error')
  }
}

onMounted(load)
</script>

<template>
  <section>
    <div class="border-b border-line pb-6">
      <p class="eyebrow">07 / SETTINGS</p>
      <h1 class="mt-3 font-display text-[clamp(2rem,4vw,3.2rem)] leading-none tracking-[-0.02em]">
        设置
      </h1>
      <p class="mt-3 font-mono text-[11px] text-ink/45">媒体库 · 写入策略 · 数据源 · 安全</p>
    </div>

    <div v-if="loading" class="mt-8 border border-line p-10 text-center font-mono text-[10px] text-ink/40">
      正在读取设置…
    </div>

    <div v-else class="mt-8 grid gap-8 lg:grid-cols-[1fr_300px]">
      <div class="space-y-8">
        <section>
          <div class="flex items-center justify-between">
            <h2 class="font-display text-2xl">媒体库根目录</h2>
            <div class="flex gap-2">
              <input
                v-model="newRoot"
                placeholder="/path/to/music"
                class="w-56 border border-line bg-transparent px-3 py-2 font-mono text-[10px] placeholder:text-ink/30 focus:border-ink focus:outline-none"
                @keyup.enter="addRoot"
              />
              <button class="stamp py-2 transition hover:bg-ink hover:text-paper" @click="addRoot">
                + 添加
              </button>
            </div>
          </div>

          <div class="mt-4 divide-y divide-line border border-line bg-[#fbf8f1]">
            <div v-for="root in roots" :key="root.id" class="flex flex-wrap items-center gap-4 p-4">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <p class="truncate font-mono text-[12px]">{{ root.path }}</p>
                  <span class="stamp" :class="root.enabled ? 'text-moss' : 'text-ink/40'">
                    {{ root.enabled ? '启用' : '停用' }}
                  </span>
                </div>
                <p class="mt-1 font-mono text-[9px] text-ink/35">
                  {{ root.album_count }} 张专辑
                  <span v-if="root.last_scan_at"> · 上次扫描 {{ new Date(root.last_scan_at).toLocaleString('zh-CN') }}</span>
                </p>
              </div>
              <button
                class="border border-line px-3 py-1.5 font-mono text-[10px] transition hover:border-ink"
                @click="scanRoot(root)"
              >
                重新扫描
              </button>
              <button
                class="border border-line px-3 py-1.5 font-mono text-[10px] text-rust transition hover:border-rust"
                @click="deleting = root"
              >
                移除
              </button>
              <button
                class="h-5 w-9 rounded-full p-0.5 transition"
                :class="root.enabled ? 'bg-ink' : 'bg-line'"
                :aria-label="root.enabled ? '停用根目录' : '启用根目录'"
                @click="toggleRoot(root)"
              >
                <span
                  class="block h-4 w-4 rounded-full bg-paper transition"
                  :class="root.enabled ? 'ml-auto' : 'border border-line'"
                ></span>
              </button>
            </div>
            <p v-if="!roots.length" class="p-5 font-mono text-[10px] text-ink/35">
              还没有根目录。添加一个本地路径后执行扫描。
            </p>
          </div>
        </section>

        <section>
          <h2 class="font-display text-2xl">写入策略</h2>
          <div class="mt-4 grid gap-4 sm:grid-cols-2">
            <div class="border border-line bg-[#fbf8f1] p-4">
              <div class="eyebrow">FIELD POLICY</div>
              <div class="mt-3 space-y-2 text-[12px]">
                <label class="flex items-center gap-2">
                  <input v-model="form.field_policy" type="radio" value="fill_only" class="accent-copper" />
                  仅补空字段
                </label>
                <label class="flex items-center gap-2">
                  <input v-model="form.field_policy" type="radio" value="overwrite" class="accent-copper" />
                  总是覆盖
                </label>
                <label class="flex items-center gap-2">
                  <input v-model="form.field_policy" type="radio" value="all" class="accent-copper" />
                  全部生成差异
                </label>
              </div>
            </div>
            <div class="border border-line bg-[#fbf8f1] p-4">
              <div class="eyebrow">COVER POLICY</div>
              <div class="mt-3 space-y-2 text-[12px]">
                <label class="flex items-center gap-2">
                  <input v-model="form.cover_policy" type="radio" value="if_missing" class="accent-copper" />
                  仅在缺失时写入 cover.jpg
                </label>
                <label class="flex items-center gap-2">
                  <input v-model="form.cover_policy" type="radio" value="always" class="accent-copper" />
                  总是覆盖 cover.jpg
                </label>
                <label class="flex items-center gap-2">
                  <input v-model="form.cover_policy" type="radio" value="never" class="accent-copper" />
                  不写 cover.jpg
                </label>
              </div>
            </div>
          </div>

          <div class="mt-4 flex items-start gap-3 border border-line p-4">
            <button
              class="mt-0.5 h-5 w-9 flex-none rounded-full p-0.5 transition"
              :class="form.safe_mode ? 'bg-ink' : 'bg-line'"
              @click="form.safe_mode = !form.safe_mode"
            >
              <span
                class="block h-4 w-4 rounded-full bg-paper"
                :class="form.safe_mode ? 'ml-auto' : 'border border-line'"
              ></span>
            </button>
            <div>
              <p class="text-[12px] font-medium">安全模式：先复制再写入</p>
              <p class="mt-1 font-mono text-[9px] leading-relaxed text-ink/40">
                默认关闭。开启后写入前复制原文件，风险更低但占用额外磁盘。
              </p>
            </div>
          </div>
        </section>

        <section>
          <div class="flex items-center justify-between">
            <h2 class="font-display text-2xl">数据源</h2>
            <span class="font-mono text-[9px] text-ink/35">限流由令牌桶统一调度</span>
          </div>

          <div class="mt-4 divide-y divide-line border border-line bg-[#fbf8f1]">
            <div
              v-for="provider in settings?.providers || []"
              :key="provider.id"
              class="p-4"
              :class="provider.id === 'netease' && !provider.enabled ? 'bg-paper2/40' : ''"
            >
              <div class="flex flex-wrap items-center gap-3">
                <span class="stamp w-12 justify-center text-ink/60">
                  {{ provider.id.slice(0, 2).toUpperCase() }}
                </span>
                <div class="min-w-0 flex-1">
                  <p class="text-[13px] font-medium">{{ provider.label }}</p>
                  <p class="mt-0.5 font-mono text-[9px] text-ink/35">
                    {{ provider.rate }} ·
                    {{
                      Object.keys(provider.masked || {}).length
                        ? provider.configured
                          ? '凭据已配置'
                          : '未配置凭据'
                        : '无需凭据'
                    }}
                  </p>
                </div>
                <span class="stamp" :class="provider.enabled ? 'text-moss' : 'text-ink/40'">
                  {{ provider.enabled ? '已启用' : '已停用' }}
                </span>
                <button
                  class="h-5 w-9 rounded-full p-0.5 transition"
                  :class="enabled[provider.id] ? 'bg-ink' : 'bg-line'"
                  @click="enabled[provider.id] = !enabled[provider.id]"
                >
                  <span
                    class="block h-4 w-4 rounded-full bg-paper"
                    :class="enabled[provider.id] ? 'ml-auto' : 'border border-line'"
                  ></span>
                </button>
              </div>

              <p
                v-if="provider.id === 'netease'"
                class="mt-2 font-mono text-[9px] text-rust"
              >
                非官方接口 · 默认关闭 · 需自备 Cookie
              </p>

              <div
                v-if="Object.keys(provider.masked || {}).length"
                class="mt-3 grid gap-2 sm:grid-cols-2"
              >
                <label
                  v-for="(masked, key) in provider.masked"
                  :key="key"
                  class="block"
                >
                  <span class="font-mono text-[9px] uppercase tracking-[0.14em] text-ink/35">
                    {{ credLabels[key] || key }}
                  </span>
                  <input
                    v-model="creds[key]"
                    :placeholder="masked || '未设置'"
                    class="mt-1 w-full border border-line bg-paper px-2.5 py-2 font-mono text-[10px] placeholder:text-ink/30 focus:border-ink focus:outline-none"
                  />
                </label>
              </div>
            </div>
          </div>
        </section>
      </div>

      <aside class="space-y-4">
        <div class="card p-5">
          <div class="eyebrow">SYSTEM</div>
          <div class="mt-4 space-y-2.5 font-mono text-[10px]">
            <div class="leader"><span class="text-ink/40">版本</span><span class="dots"></span><span>{{ settings?.system.version }}</span></div>
            <div class="leader"><span class="text-ink/40">fpcalc</span><span class="dots"></span><span :class="settings?.system.fpcalc ? 'text-moss' : 'text-rust'">{{ settings?.system.fpcalc ? '可用' : '缺失' }}</span></div>
            <div class="leader"><span class="text-ink/40">数据库</span><span class="dots"></span><span>SQLite · WAL</span></div>
          </div>
        </div>

        <div class="border border-line p-5">
          <div class="eyebrow">SECRET KEY</div>
          <p class="mt-3 break-all font-mono text-[10px] text-ink/45">••••••••••••••••••••</p>
          <p class="mt-2 font-mono text-[9px] leading-relaxed text-ink/35">
            用于 Fernet 加密数据源凭据，来自环境变量 SECRET_KEY。
          </p>
        </div>

        <div class="border border-rust/40 bg-[#fbf8f1] p-5">
          <div class="eyebrow text-rust">COMPLIANCE</div>
          <p class="mt-3 font-mono text-[10px] leading-relaxed text-ink/45">
            网易云 / QQ 适配器通过非官方接口实现，可能随时失效。启用即表示自行承担合规与稳定性风险。
          </p>
        </div>

        <button
          class="w-full bg-ink py-3 font-mono text-[11px] tracking-[0.18em] text-paper transition hover:bg-copper disabled:opacity-50"
          :disabled="saving"
          @click="save"
        >
          {{ saving ? '保存中…' : '保存设置' }}
        </button>
      </aside>
    </div>

    <ConfirmDialog
      :open="Boolean(deleting)"
      kicker="ROOT / REMOVE"
      :title="`移除 ${deleting?.path || ''}？`"
      confirm-text="确认移除"
      danger
      @cancel="deleting = null"
      @confirm="removeRoot"
    >
      <p>只移除索引与配置，不会删除任何音频文件。</p>
    </ConfirmDialog>
  </section>
</template>
