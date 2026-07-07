import { createI18n } from 'vue-i18n'
import en from '../locales/en.json'
import fa from '../locales/fa.json'

export const i18n = createI18n({
  legacy: false,
  locale: localStorage.getItem('locale') || 'en',
  fallbackLocale: 'en',
  messages: { en, fa },
})

export function setLocale(locale: 'en' | 'fa') {
  i18n.global.locale.value = locale
  localStorage.setItem('locale', locale)
  document.documentElement.dir = locale === 'fa' ? 'rtl' : 'ltr'
  document.documentElement.lang = locale
}

const savedLocale = localStorage.getItem('locale') as 'en' | 'fa' | null
if (savedLocale) {
  document.documentElement.dir = savedLocale === 'fa' ? 'rtl' : 'ltr'
  document.documentElement.lang = savedLocale
}
