import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
import type { Job } from '../api/types'

export const useJobsStore = defineStore('jobs', () => {
  const jobs = ref<Job[]>([])
  const loading = ref(false)
  let timer: number | null = null

  async function load() {
    loading.value = true
    try {
      jobs.value = await api.jobs.list()
    } finally {
      loading.value = false
    }
  }

  function startPolling(interval = 2000) {
    stopPolling()
    load()
    timer = window.setInterval(() => {
      if (jobs.value.some((job) => ['queued', 'running'].includes(job.status))) {
        load()
      }
    }, interval)
  }

  function stopPolling() {
    if (timer !== null) {
      window.clearInterval(timer)
      timer = null
    }
  }

  async function cancel(id: number) {
    await api.jobs.cancel(id)
    await load()
  }

  return { jobs, loading, load, startPolling, stopPolling, cancel }
})
