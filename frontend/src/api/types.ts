export interface Root {
  id: number
  path: string
  enabled: boolean
  last_scan_at: string | null
  album_count: number
}

export interface Album {
  id: number
  root_id: number
  rel_path: string
  kind: 'whole' | 'split'
  status: 'matched' | 'pending' | 'unmatched'
  artist: string | null
  title: string | null
  year: number | null
  track_count: number
  duration_ms: number
  confidence: number
  mbid: string | null
  has_cover: boolean
  cover_url: string | null
  selected_cover_url?: string | null
  directory?: string | null
  tracks?: Track[]
  tags?: Record<string, string[]>
  track_tags?: Record<string, Record<string, string[]>>
  candidates_count?: number
}

export interface Track {
  id: number
  path: string
  ext: string
  format: string
  track_no: number | null
  disc_no: number | null
  title: string | null
  artist: string | null
  duration_ms: number | null
  bitrate: number | null
  sample_rate: number | null
}

export interface Candidate {
  id: number
  provider: string
  provider_id: string
  score: number
  parts: Record<string, unknown>
  title: string | null
  artist: string | null
  year: number | null
  label: string | null
  catalog_number: string | null
  track_count: number
  duration_ms: number
  release_mbid: string | null
  covers: { provider: string; url: string; width?: number; height?: number }[]
  fetched_at: string | null
}

export interface ChangeItem {
  id: number
  target_type: 'album' | 'track'
  target_id: number | null
  field: string
  old_value: string | null
  new_value: string | null
  action: string
  selected: boolean
}

export interface Plan {
  id: number
  album_id: number
  status: string
  policy: string
  created_at: string | null
  candidate_id?: number | null
  cover_url: string | null
  cover_provider: string | null
  release: Record<string, unknown> | null
  album: { id: number; artist: string | null; title: string | null; year: number | null; kind: string }
  items: ChangeItem[]
  file_count: number
  selected_count: number
  total_count: number
}

export interface Job {
  id: number
  type: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  progress: number
  total: number
  done: number
  payload: Record<string, unknown>
  result: Record<string, unknown>
  error: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string | null
}

export interface BackupBatch {
  batch_id: string
  backup_id: number
  album_id: number
  album_title: string | null
  artist: string | null
  cover_url: string | null
  plan_id: number | null
  status: string
  files: number
  created_at: string | null
}

export interface ProviderState {
  id: string
  label: string
  rate: string
  enabled: boolean
  configured: boolean
  enabled_by_user: boolean
  masked: Record<string, string>
}

export interface SettingsResponse {
  values: Record<string, unknown>
  masked: Record<string, string>
  providers: ProviderState[]
  system: { fpcalc: boolean; version: string; db: string }
}
