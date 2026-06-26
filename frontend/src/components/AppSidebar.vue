<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useLayoutStore } from '../stores/layout'

const { t } = useI18n()
const route = useRoute()
const layout = useLayoutStore()

const navItems = [
  { name: 'overview', path: '/', label: 'nav.overview', icon: 'overview' },
  { name: 'strategies', path: '/strategies', label: 'nav.strategies', icon: 'strategies' },
  { name: 'settings', path: '/settings', label: 'nav.settings', icon: 'settings' },
] as const

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<template>
  <aside
    class="shrink-0 border-e border-zinc-800 bg-zinc-900/50 flex flex-col transition-[width] duration-200 ease-out"
    :class="layout.isNavCollapsed ? 'w-16' : 'w-60'"
  >
    <div class="flex items-center border-b border-zinc-800/80 px-2 py-2">
      <button
        type="button"
        class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
        :title="layout.isNavCollapsed ? t('nav.expand') : t('nav.collapse')"
        @click="layout.toggleNav()"
      >
        <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
      <span
        v-if="!layout.isNavCollapsed"
        class="ms-2 truncate text-xs font-medium uppercase tracking-wide text-zinc-500"
      >
        {{ t('app.title') }}
      </span>
    </div>

    <nav class="flex flex-col gap-0.5 p-2">
      <RouterLink
        v-for="item in navItems"
        :key="item.name"
        :to="item.path"
        :title="layout.isNavCollapsed ? t(item.label) : undefined"
        class="flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors"
        :class="
          isActive(item.path)
            ? 'bg-zinc-800 text-zinc-100 font-medium'
            : 'text-zinc-500 hover:bg-zinc-800/50 hover:text-zinc-300'
        "
      >
        <span class="flex h-6 w-6 shrink-0 items-center justify-center">
          <svg
            v-if="item.icon === 'overview'"
            class="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
          </svg>
          <svg
            v-else-if="item.icon === 'strategies'"
            class="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
          </svg>
          <svg
            v-else
            class="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </span>
        <span v-if="!layout.isNavCollapsed" class="truncate">{{ t(item.label) }}</span>
      </RouterLink>
    </nav>
  </aside>
</template>
