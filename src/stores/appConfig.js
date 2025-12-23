import { defineStore } from 'pinia'
import { ref } from 'vue'

const DEFAULT_CONFIG = {
  branding: {
    title: 'SimpleChat',
    brand_icon: 'ph-chat-teardrop-text',
    empty_state_icon: 'ph-sparkle',
    login_subtitle: 'Your premium AI assistant',
  },
  theme: {},
}

const THEME_VAR_MAP = {
  bg_primary: '--bg-primary',
  bg_secondary: '--bg-secondary',
  bg_surface: '--bg-surface',
  bg_input: '--bg-input',
  text_primary: '--text-primary',
  text_secondary: '--text-secondary',
  text_tertiary: '--text-tertiary',
  primary: '--primary',
  primary_hover: '--primary-hover',
  accent: '--accent',
  gradient_primary: '--gradient-primary',
  success: '--success',
  warning: '--warning',
  error: '--error',
  border_subtle: '--border-subtle',
  border_focus: '--border-focus',
}

const applyTheme = (theme = {}) => {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  Object.entries(THEME_VAR_MAP).forEach(([key, cssVar]) => {
    const value = theme[key]
    if (typeof value === 'string' && value.trim()) {
      root.style.setProperty(cssVar, value.trim())
    }
  })
}

export const useAppConfigStore = defineStore('appConfig', () => {
  const config = ref(DEFAULT_CONFIG)

  const loadConfig = async () => {
    try {
      const base = (window.__API_BASE__ || '').replace(/\/$/, '')
      const apiBase = base.endsWith('/api') ? base : `${base}/api`
      const response = await fetch(`${apiBase}/config`)
      if (!response.ok) {
        return
      }
      const data = await response.json()
      if (data && typeof data === 'object') {
        config.value = {
          branding: { ...DEFAULT_CONFIG.branding, ...(data.branding || {}) },
          theme: { ...(data.theme || {}) },
        }
        applyTheme(config.value.theme)
      }
    } catch (err) {
      console.warn('Failed to load app config', err)
    }
  }

  return { config, loadConfig }
})
