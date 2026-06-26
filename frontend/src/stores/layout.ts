import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'tradebot-nav-collapsed'

export const useLayoutStore = defineStore('layout', () => {
  const isNavCollapsed = ref(localStorage.getItem(STORAGE_KEY) === '1')

  function toggleNav() {
    isNavCollapsed.value = !isNavCollapsed.value
  }

  watch(isNavCollapsed, (v) => {
    localStorage.setItem(STORAGE_KEY, v ? '1' : '0')
  })

  return { isNavCollapsed, toggleNav }
})
