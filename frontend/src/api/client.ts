import type {
  Album,
  BackupBatch,
  Candidate,
  Job,
  Plan,
  Root,
  SettingsResponse,
} from './types'

export class ApiError extends Error {
  status: number
  code: string
  traceId?: string

  constructor(message: string, status: number, code = 'error', traceId?: string) {
    super(message)
    this.status = status
    this.code = code
    this.traceId = traceId
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  })
  if (response.status === 204) return undefined as T
  const text = await response.text()
  const payload = text ? JSON.parse(text) : null
  if (!response.ok) {
    throw new ApiError(
      payload?.message || `请求失败 (${response.status})`,
      response.status,
      payload?.code,
      payload?.trace_id,
    )
  }
  return payload as T
}

function query(params: Record<string, unknown>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value))
    }
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const api = {
  health: () => request<Record<string, unknown>>('/health'),
  stats: () =>
    request<{
      albums: number
      files: number
      pending: number
      roots: number
      running_jobs: number
      recent_albums: Album[]
    }>('/stats'),
  roots: {
    list: () => request<Root[]>('/roots'),
    create: (path: string) =>
      request<Root>('/roots', { method: 'POST', body: JSON.stringify({ path }) }),
    update: (id: number, enabled: boolean) =>
      request<Root>(`/roots/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ enabled }),
      }),
    remove: (id: number) => request<void>(`/roots/${id}`, { method: 'DELETE' }),
    scan: (id: number) =>
      request<{ job_id: number; status: string }>(`/roots/${id}/scan`, { method: 'POST' }),
  },
  albums: {
    list: (params: Record<string, unknown>) =>
      request<{ items: Album[]; total: number; page: number; page_size: number }>(
        `/albums${query(params)}`,
      ),
    detail: (id: number) => request<Album>(`/albums/${id}`),
    candidates: (id: number) => request<Candidate[]>(`/albums/${id}/candidates`),
    search: (id: number, text: string) =>
      request<Candidate[]>(`/albums/${id}/search`, {
        method: 'POST',
        body: JSON.stringify({ query: text }),
      }),
    select: (id: number, candidateId: number, policy = 'fill_only') =>
      request<Plan>(`/albums/${id}/select`, {
        method: 'POST',
        body: JSON.stringify({ candidate_id: candidateId, policy }),
      }),
    covers: (id: number, candidateId: number) =>
      request<{ provider: string; url: string; width?: number; height?: number }[]>(
        `/albums/${id}/covers?candidate_id=${candidateId}`,
      ),
    setCover: (id: number, url: string, planId?: number) =>
      request<{ plan_id: number | null; cover_url: string }>(`/albums/${id}/cover`, {
        method: 'POST',
        body: JSON.stringify({ url, plan_id: planId }),
      }),
    batchMatch: (albumIds: number[]) =>
      request<{ job_ids: number[] }>('/albums/batch/match', {
        method: 'POST',
        body: JSON.stringify({ album_ids: albumIds }),
      }),
  },
  plans: {
    get: (id: number) => request<Plan>(`/plans/${id}`),
    patchItems: (
      id: number,
      items: { id: number; selected?: boolean; new_value?: string }[],
    ) =>
      request<Plan>(`/plans/${id}/items`, {
        method: 'PATCH',
        body: JSON.stringify({ items }),
      }),
    apply: (id: number, coverUrl?: string | null) =>
      request<{ job_id: number; status: string; plan_id: number }>(`/plans/${id}/apply`, {
        method: 'POST',
        body: JSON.stringify({ cover_url: coverUrl || null }),
      }),
  },
  jobs: {
    list: (limit = 50) => request<Job[]>(`/jobs?limit=${limit}`),
    get: (id: number) => request<Job>(`/jobs/${id}`),
    cancel: (id: number) =>
      request<Job>(`/jobs/${id}/cancel`, { method: 'POST' }),
  },
  backups: {
    list: (albumId?: number) =>
      request<BackupBatch[]>(`/backups${albumId ? `?album_id=${albumId}` : ''}`),
    restore: (batch: string) =>
      request<{ job_id: number; status: string; batch_id: string }>(
        `/backups/${batch}/restore`,
        { method: 'POST' },
      ),
  },
  settings: {
    get: () => request<SettingsResponse>('/settings'),
    update: (values: Record<string, unknown>) =>
      request<SettingsResponse>('/settings', {
        method: 'PUT',
        body: JSON.stringify({ values }),
      }),
  },
  audit: () => request<Record<string, unknown>[]>('/audit-logs?limit=100'),
}
