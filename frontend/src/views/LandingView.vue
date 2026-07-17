<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { useTheme } from '../composables/useTheme'

const { theme, toggle } = useTheme()

const features = [
  { title: 'Multi-exchange', body: 'Trade Tabdeal futures and Hyperliquid from one place with encrypted API keys.' },
  { title: 'Copy trading', body: 'Subscribe to vetted master strategies; trades mirror to your own account, sized to your risk.' },
  { title: 'Backtest & optimize', body: 'Validate Pine strategies on historical data with grid and Monte-Carlo optimization before going live.' },
  { title: 'Fair fees', body: 'Keep 80% of profits. The platform earns only on new gains above your high-water mark.' },
]
</script>

<template>
  <div class="min-h-screen bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
    <header class="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
      <span class="text-lg font-semibold">AlgoTrader</span>
      <div class="flex items-center gap-3">
        <button
          type="button"
          class="rounded-lg p-2 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          :aria-label="theme === 'dark' ? 'Switch to light' : 'Switch to dark'"
          @click="toggle"
        >
          <span aria-hidden="true">{{ theme === 'dark' ? '☀️' : '🌙' }}</span>
        </button>
        <RouterLink
          to="/login"
          class="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500"
        >
          Log in
        </RouterLink>
      </div>
    </header>

    <main class="mx-auto max-w-6xl px-6">
      <section class="py-20 text-center">
        <h1 class="mx-auto max-w-3xl text-4xl font-bold tracking-tight sm:text-5xl">
          Automated crypto trading, without the guesswork
        </h1>
        <p class="mx-auto mt-5 max-w-2xl text-lg text-zinc-500 dark:text-zinc-400">
          Build and backtest strategies, or copy proven ones — executed on your own
          Tabdeal and Hyperliquid accounts. You keep custody; you keep 80% of profits.
        </p>
        <div class="mt-8 flex justify-center gap-3">
          <RouterLink
            to="/login"
            class="rounded-lg bg-violet-600 px-6 py-3 text-sm font-medium text-white hover:bg-violet-500"
          >
            Get started
          </RouterLink>
          <a
            href="mailto:access@algotrader.app?subject=Request%20access"
            class="rounded-lg border border-zinc-300 px-6 py-3 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
          >
            Request access
          </a>
        </div>
      </section>

      <section class="grid gap-6 pb-24 sm:grid-cols-2 lg:grid-cols-4">
        <div
          v-for="f in features"
          :key="f.title"
          class="rounded-xl border border-zinc-200 p-5 dark:border-zinc-800"
        >
          <h3 class="text-sm font-semibold">{{ f.title }}</h3>
          <p class="mt-2 text-sm text-zinc-500 dark:text-zinc-400">{{ f.body }}</p>
        </div>
      </section>
    </main>
  </div>
</template>
