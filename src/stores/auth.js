import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import router from '../router'
import apiClient from '../services/api'

const safeParse = (value) => {
  try {
    return JSON.parse(value)
  } catch (err) {
    console.warn('Failed to parse stored user, clearing session', err)
    return null
  }
}

const formatUser = (raw) => {
  if (!raw) return null
  return {
    id: raw.id,
    email: raw.email,
    displayName: raw.displayName ?? raw.display_name ?? raw.name ?? raw.email,
    role: raw.role ?? raw.plan ?? 'user',
    createdAt: raw.createdAt ?? raw.created_at ?? null,
    lastLoginAt: raw.lastLoginAt ?? raw.last_login_at ?? null
  }
}

const loadStoredUser = () => {
  const stored = safeParse(localStorage.getItem('user'))
  return formatUser(stored)
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref(loadStoredUser())
  const token = ref(localStorage.getItem('auth_token') || null)
  const isLoading = ref(false)
  const error = ref(null)

  const isAuthenticated = computed(() => Boolean(token.value))

  const persistSession = (userData, jwt) => {
    user.value = userData
    token.value = jwt
    localStorage.setItem('user', JSON.stringify(userData))
    localStorage.setItem('auth_token', jwt)
  }

  const clearSession = () => {
    user.value = null
    token.value = null
    localStorage.removeItem('user')
    localStorage.removeItem('auth_token')
  }

  const performLoginRequest = async (email, password) => {
    const { data } = await apiClient.post('/auth/login', { email, password })
    const formattedUser = formatUser(data.user)
    persistSession(formattedUser, data.access_token)
  }

  const login = async (email, password) => {
    isLoading.value = true
    error.value = null
    try {
      await performLoginRequest(email, password)
      router.push('/')
    } catch (err) {
      error.value = err?.response?.data?.detail || err.message || 'Login failed'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  const register = async ({ email, password, displayName }) => {
    isLoading.value = true
    error.value = null
    try {
      await apiClient.post('/auth/register', {
        email,
        password,
        display_name: displayName
      })
      await performLoginRequest(email, password)
      router.push('/')
    } catch (err) {
      error.value = err?.response?.data?.detail || err.message || 'Registration failed'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  const logout = () => {
    clearSession()
    error.value = null
    router.push('/login')
  }

  return {
    user,
    token,
    isLoading,
    error,
    isAuthenticated,
    login,
    register,
    logout
  }
})
