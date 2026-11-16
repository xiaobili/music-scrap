import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'
import { api } from '../api/client'
import type { Album, Root } from '../api/types'

export const useLibraryStore = defineStore('library', () => {
  const roots = ref<Root[]>([])
  const albums = ref<Album[]>([])
  const total = ref(0)
  const loading = ref(false)
  const filters = reactive({
    status: '',
    kind: '',
    root_id: '' as number | '',
    q: '',
    page: 1,
    page_size: 24,
  })

  async function loadRoots() {
    roots.value = await api.roots.list()
  }

  async function loadAlbums() {
    loading.value = true
    try {
      const data = await api.albums.list({ ...filters })
      albums.value = data.items
      total.value = data.total
    } finally {
      loading.value = false
    }
  }

  async function scan(rootId: number) {
    return api.roots.scan(rootId)
  }

  return { roots, albums, total, loading, filters, loadRoots, loadAlbums, scan }
})
