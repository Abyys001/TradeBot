import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { i18n } from './i18n'
import { useAuthStore } from './stores/auth'
import './theme'
import './style.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(i18n)

const auth = useAuthStore()
auth.init().catch(() => {
  console.warn('CSRF fetch failed — mutations may not work')
}).finally(() => {
  app.mount('#app')
})
