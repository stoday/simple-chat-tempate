<script setup>
import { ref, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAuthStore } from '../stores/auth'
import { useAppConfigStore } from '../stores/appConfig'

const authStore = useAuthStore()
const { isLoading, error } = storeToRefs(authStore)
const appConfigStore = useAppConfigStore()
const { config } = storeToRefs(appConfigStore)

const displayName = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const localError = ref('')

onMounted(() => {
  authStore.error = null
})

const combinedError = computed(() => localError.value || error.value)

const handleRegister = async () => {
  localError.value = ''
  if (password.value !== confirmPassword.value) {
    localError.value = '兩次輸入的密碼不一致'
    return
  }
  try {
    await authStore.register({
      email: email.value,
      password: password.value,
      displayName: displayName.value
    })
  } catch (err) {
    // errors already surfaced through store
  }
}
</script>

<template>
  <div class="login-container">
    <div class="decor-circle circle-1"></div>
    <div class="decor-circle circle-2"></div>

    <div class="login-card">
      <div class="logo-area">
        <div class="logo-icon-wrapper">
          <i class="ph logo-icon" :class="config.branding.brand_icon"></i>
        </div>
        <h1>Create Account</h1>
        <p>Set up your {{ config.branding.title }} workspace</p>
      </div>
      
      <form @submit.prevent="handleRegister" class="login-form">
        <div class="form-group">
          <label class="sr-only">Display Name</label>
          <div class="input-icon-wrapper">
            <i class="ph ph-user"></i>
            <input 
              type="text" 
              v-model="displayName" 
              placeholder="Your name" 
              required 
            />
          </div>
        </div>

        <div class="form-group">
          <label class="sr-only">Email</label>
          <div class="input-icon-wrapper">
            <i class="ph ph-envelope"></i>
            <input 
              type="email" 
              v-model="email" 
              placeholder="name@example.com" 
              required 
            />
          </div>
        </div>
        
        <div class="form-group">
          <label class="sr-only">Password</label>
          <div class="input-icon-wrapper">
            <i class="ph ph-lock-key"></i>
            <input 
              type="password" 
              v-model="password" 
              placeholder="至少 8 碼密碼" 
              required 
              minlength="8"
            />
          </div>
        </div>

        <div class="form-group">
          <label class="sr-only">Confirm Password</label>
          <div class="input-icon-wrapper">
            <i class="ph ph-lock-key"></i>
            <input 
              type="password" 
              v-model="confirmPassword" 
              placeholder="再次輸入密碼" 
              required 
              minlength="8"
            />
          </div>
        </div>
        
        <button type="submit" class="btn btn-primary btn-block" :disabled="isLoading">
          <span v-if="!isLoading">Create Account</span>
          <span v-else>Processing...</span>
        </button>

        <p v-if="combinedError" class="error-message">{{ combinedError }}</p>
      </form>
      
      <div class="footer-links">
        <span class="link">已有帳號？</span>
        <RouterLink to="/login" class="link highlight">返回登入</RouterLink>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  min-height: 100vh;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  background: var(--bg-primary);
  overflow: hidden;
}

/* Background Decor */
.decor-circle {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.4;
  z-index: 1;
}
.circle-1 {
  width: 400px;
  height: 400px;
  background: var(--primary);
  top: -100px;
  left: -100px;
}
.circle-2 {
  width: 300px;
  height: 300px;
  background: var(--accent);
  bottom: -50px;
  right: -50px;
}

.login-card {
  width: 100%;
  max-width: 420px;
  padding: var(--space-8) var(--space-6);
  background: var(--glass-bg);
  backdrop-filter: var(--backdrop-blur);
  border: var(--glass-border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  position: relative;
  z-index: 10;
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.logo-area {
  text-align: center;
}

.logo-icon-wrapper {
  width: 64px;
  height: 64px;
  background: var(--gradient-primary);
  border-radius: var(--radius-lg);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--space-4);
  box-shadow: 0 10px 25px rgba(139, 92, 246, 0.4);
}

.logo-icon {
  font-size: 32px;
  color: white;
}

h1 {
  font-size: 1.75rem;
  margin-bottom: var(--space-1);
}

.logo-area p {
  margin-bottom: 0;
  font-size: 0.9rem;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.input-icon-wrapper {
  position: relative;
  width: 100%;
}

.input-icon-wrapper i {
  position: absolute;
  left: var(--space-3);
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-tertiary);
  font-size: 1.25rem;
}

input {
  width: 100%;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid var(--border-subtle);
  padding: var(--space-3);
  padding-left: var(--space-8);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  transition: all var(--transition-fast);
}

input:focus {
  border-color: var(--primary);
  background: rgba(0, 0, 0, 0.4);
  box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.1);
}

.btn-block {
  width: 100%;
  padding: var(--space-3);
  font-size: 1rem;
}

.footer-links {
  display: flex;
  justify-content: center;
  gap: var(--space-2);
  font-size: 0.9rem;
  color: var(--text-secondary);
}

.link {
  color: var(--text-secondary);
  transition: color var(--transition-fast);
}

.link.highlight {
  color: var(--primary);
  font-weight: 600;
}

.link:hover {
  color: var(--primary);
  text-decoration: underline;
}

.error-message {
  color: var(--error);
  text-align: center;
  font-size: 0.9rem;
  margin-top: var(--space-2);
}
</style>
