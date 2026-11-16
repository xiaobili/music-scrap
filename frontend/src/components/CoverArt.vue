<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Album } from '../api/types'

const props = defineProps<{
  src?: string | null
  album?: Album | null
  title?: string
  subtitle?: string
}>()

const failed = ref(false)
watch(
  () => props.src,
  () => {
    failed.value = false
  },
)

const palettes = [
  ['#101d28', '#e9e3d6', '#b8622d'],
  ['#1d2e26', '#efe9dc', '#b8622d'],
  ['#2b4a52', '#e9e3d6', '#7d4a33'],
  ['#1a0f16', '#efe9dc', '#e06a9a'],
  ['#e7dcc6', '#1f3552', '#c08a3e'],
  ['#16232e', '#efe9dc', '#8a9aa5'],
]

function escapeXml(value: string) {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

const seed = computed(() => {
  const key = `${props.album?.id || 0}:${props.title || props.album?.title || props.album?.rel_path || ''}`
  return [...key].reduce((sum, char) => sum + char.charCodeAt(0), 0)
})

const palette = computed(() => palettes[seed.value % palettes.length])

const fallback = computed(() => {
  const [bg, fg, accent] = palette.value
  const title = escapeXml((props.title || props.album?.title || 'Untitled').slice(0, 22))
  const subtitle = escapeXml((props.subtitle || props.album?.artist || '').slice(0, 26))
  const shift = (seed.value % 220) - 110
  const radius = 140 + (seed.value % 90)
  const cx = 540 + shift * 0.4
  const cy = 250 + ((seed.value % 70) - 35)
  const variant = seed.value % 3
  const variants = [
    `<rect x="86" y="150" width="210" height="320" fill="${fg}" opacity="0.10"/>
     <path d="M80 610 720 190" stroke="${accent}" stroke-width="2" opacity="0.35"/>`,
    `<g fill="${accent}" opacity="0.35"><rect x="86" y="470" width="40" height="230"/><rect x="146" y="380" width="40" height="320"/><rect x="206" y="540" width="40" height="160"/></g>
     <path d="M80 330h300" stroke="${fg}" stroke-width="1" opacity="0.3"/>`,
    `<circle cx="${cx}" cy="${cy}" r="${radius + 70}" fill="none" stroke="${fg}" stroke-width="18" opacity="0.18"/>
     <path d="M80 560h640" stroke="${accent}" stroke-width="3" opacity="0.5"/>`,
  ]
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="800" viewBox="0 0 800 800">
    <rect width="800" height="800" fill="${bg}"/>
    <circle cx="${cx}" cy="${cy}" r="${radius}" fill="${fg}" opacity="0.94"/>
    <circle cx="${cx}" cy="${cy}" r="${radius}" fill="none" stroke="${accent}" stroke-width="2" stroke-dasharray="2 9"/>
    <path d="M80 120v420" stroke="${fg}" stroke-width="1" opacity="0.25"/>
    ${variants[variant]}
    <rect x="470" y="545" width="240" height="6" fill="${accent}"/>
    <rect x="470" y="571" width="150" height="3" fill="${fg}" opacity="0.45"/>
    <g fill="${fg}" font-family="IBM Plex Mono, monospace" font-size="25" letter-spacing="4">
      <text x="64" y="682">${subtitle || 'ARCHIVE'}</text>
      <text x="64" y="722" opacity="0.5">${title}</text>
    </g>
    <filter id="n"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter>
    <rect width="800" height="800" filter="url(#n)" opacity="0.05"/>
  </svg>`
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
})
</script>

<template>
  <img
    :src="src && !failed ? src : fallback"
    :alt="title || album?.title || 'cover'"
    class="h-full w-full object-cover"
    @error="failed = true"
  />
</template>
