<script setup lang="ts">
import AppShell from './components/AppShell.vue'
import ToastHost from './components/ToastHost.vue'
</script>

<template>
  <div class="grain"></div>
  <AppShell>
    <RouterView v-slot="{ Component }">
      <component :is="Component" class="view-enter" />
    </RouterView>
  </AppShell>
  <ToastHost />
</template>
