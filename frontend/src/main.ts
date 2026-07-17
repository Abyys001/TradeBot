import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { i18n } from './i18n'
import { useAuthStore } from './stores/auth'
import { initTheme } from './composables/useTheme'
import './style.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(i18n)

initTheme()

const auth = useAuthStore()
auth.init().finally(() => {
  app.mount('#app')
})
