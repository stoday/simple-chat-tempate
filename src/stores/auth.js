import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import router from '../router'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(JSON.parse(localStorage.getItem('user')) || null)
  const token = ref(localStorage.getItem('auth_token') || null)
  const isLoading = ref(false)
  const error = ref(null)

  const isAuthenticated = computed(() => !!token.value)

  // Mock Login Action
  const login = async (email, password) => {
    isLoading.value = true
    error.value = null
    
    try {
      // Simulate API delay
      await new Promise(resolve => setTimeout(resolve, 1000))
      
      // Mock Success (Any non-empty inputs work for now)
      if (email && password) {
        const mockUser = {
          id: 'u_123',
          name: 'Demo User',
          email: email,
          avatar: null, // null will show default icon
          plan: 'Premium' 
        }
        const mockToken = 'mock-jwt-token-xyz'

        // Update State
        user.value = mockUser
        token.value = mockToken

        // Persist
        localStorage.setItem('user', JSON.stringify(mockUser))
        localStorage.setItem('auth_token', mockToken)

        // Navigate
        router.push('/')
      } else {
        throw new Error('Invalid credentials')
      }
    } catch (e) {
      error.value = e.message || 'Login failed'
    } finally {
      isLoading.value = false
    }
  }

  const logout = () => {
    user.value = null
    token.value = null
    localStorage.removeItem('user')
    localStorage.removeItem('auth_token')
    router.push('/login')
  }

  return {
    user,
    token,
    isLoading,
    error,
    isAuthenticated,
    login,
    logout
  }
})
