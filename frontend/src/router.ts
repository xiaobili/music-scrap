import { createRouter, createWebHistory } from 'vue-router'
import OverviewView from './views/OverviewView.vue'
import AlbumsView from './views/AlbumsView.vue'
import AlbumDetailView from './views/AlbumDetailView.vue'
import ReviewView from './views/ReviewView.vue'
import TasksView from './views/TasksView.vue'
import HistoryView from './views/HistoryView.vue'
import SettingsView from './views/SettingsView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: OverviewView, meta: { label: 'OVERVIEW' } },
    { path: '/albums', name: 'albums', component: AlbumsView, meta: { label: 'LIBRARY' } },
    { path: '/albums/:id', name: 'album', component: AlbumDetailView, meta: { label: 'RELEASE' } },
    {
      path: '/albums/:id/review',
      name: 'review',
      component: ReviewView,
      meta: { label: 'REVIEW' },
    },
    { path: '/tasks', name: 'tasks', component: TasksView, meta: { label: 'TASKS' } },
    { path: '/history', name: 'history', component: HistoryView, meta: { label: 'HISTORY' } },
    { path: '/settings', name: 'settings', component: SettingsView, meta: { label: 'SETTINGS' } },
  ],
})

router.afterEach(() => {
  window.scrollTo({ top: 0 })
})
