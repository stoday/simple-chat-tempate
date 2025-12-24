<script setup>
import { ref, watch, nextTick, onMounted, onUnmounted, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useChatStore } from '../stores/chat'
import { useAuthStore } from '../stores/auth'
import { useAppConfigStore } from '../stores/appConfig'
import ChatMessage from '../components/chat/ChatMessage.vue'
import ChatInput from '../components/chat/ChatInput.vue'
import SidebarItem from '../components/layout/SidebarItem.vue'

// Stores
const chatStore = useChatStore()
const authStore = useAuthStore()
const appConfigStore = useAppConfigStore()

const { conversations, currentMessages, isTyping, hasPendingAssistant, isUploading, uploadProgress, activeChatId } = storeToRefs(chatStore)
const { user } = storeToRefs(authStore)
const { config } = storeToRefs(appConfigStore)

const messagesContainer = ref(null)
const isSidebarCollapsed = ref(false) // false = expanded (default open)
const chatInputRef = ref(null)
const showEmptyState = computed(() => {
  return !currentMessages.value.length && !isTyping.value && !hasPendingAssistant.value
})

const scrollToBottom = async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// Watch for new messages or typing status changes
watch([currentMessages, isTyping], () => {
  scrollToBottom()
}, { deep: true })

const handleSend = async (payload) => {
  try {
    await chatStore.sendMessage(payload.text, payload.files)
    chatInputRef.value?.resetInput()
  } catch (error) {
    if (error?.code === 'ERR_CANCELED' || error?.message === 'canceled') {
      return
    }
    console.error('Failed to send message', error)
    showInPageAlert(error?.response?.data?.detail || error.message || 'Failed to send message.')
  }
}

const handleStopGeneration = async () => {
  try {
    await chatStore.stopGenerating()
  } catch (error) {
    console.error('Failed to stop generation', error)
    showInPageAlert(error?.response?.data?.detail || error.message || 'Failed to stop response.')
  }
}

const handleNewChat = async () => {
  try {
    await chatStore.createNewChat()
  } catch (error) {
    console.error('Failed to create chat', error)
    showInPageAlert(error?.response?.data?.detail || error.message || 'Failed to create chat.')
  }
}

const handleLogout = () => {
  authStore.logout()
}

const handleCancelUpload = () => {
  chatStore.cancelUpload()
}

const handleSelectConversation = async (conversationId) => {
  try {
    await chatStore.selectConversation(conversationId)
  } catch (error) {
    console.error('Failed to load conversation', error)
    showInPageAlert(error?.response?.data?.detail || error.message || 'Failed to open conversation.')
  }
}

const testAlert = () => {
  console.log('TEST BUTTON CLICKED!')
  alert('This is a test alert!')
  console.log('Alert should have appeared')
}

// Modal system to replace browser dialogs
const showModal = ref(false)
const modalType = ref('alert') // 'alert', 'confirm', 'prompt'
const modalMessage = ref('')
const modalInput = ref('')
const modalCallback = ref(null)

const showInPageAlert = (message) => {
  modalType.value = 'alert'
  modalMessage.value = message
  showModal.value = true
}

const showInPageConfirm = (message, callback) => {
  modalType.value = 'confirm'
  modalMessage.value = message
  modalCallback.value = callback
  showModal.value = true
}

const showInPagePrompt = (message, defaultValue, callback) => {
  modalType.value = 'prompt'
  modalMessage.value = message
  modalInput.value = defaultValue || ''
  modalCallback.value = callback
  showModal.value = true
}

const handleModalOk = async () => {
  try {
    if (modalType.value === 'confirm' && modalCallback.value) {
      await Promise.resolve(modalCallback.value(true))
    } else if (modalType.value === 'prompt' && modalCallback.value) {
      await Promise.resolve(modalCallback.value(modalInput.value))
    }
  } finally {
    showModal.value = false
    modalCallback.value = null
  }
}

const handleModalCancel = async () => {
  if (modalCallback.value) {
    await Promise.resolve(modalCallback.value(false))
  }
  showModal.value = false
  modalCallback.value = null
}

const handleDeleteChat = (id) => {
  console.log('Parent received delete for:', id)
  showInPageConfirm('Are you sure you want to delete this chat?', async (confirmed) => {
    if (!confirmed) return
    try {
      await chatStore.deleteConversation(id)
    } catch (error) {
      console.error('Failed to delete chat', error)
      showInPageAlert(error?.response?.data?.detail || error.message || 'Failed to delete chat.')
    }
  })
}

const handleRenameChat = (id) => {
  console.log('Parent received rename for:', id)
  const currentTitle = conversations.value.find(c => c.id === id)?.title
  showInPagePrompt('Rename Chat:', currentTitle, async (newTitle) => {
    if (newTitle && newTitle.trim()) {
      try {
        await chatStore.renameConversation(id, newTitle.trim())
      } catch (error) {
        console.error('Failed to rename chat', error)
        showInPageAlert(error?.response?.data?.detail || error.message || 'Failed to rename chat.')
      }
    }
  })
}

onMounted(async () => {
  try {
    await chatStore.initialize()
  } catch (error) {
    if (error?.response?.status === 401) {
      return
    }
    console.error('Failed to initialize chat state', error)
    showInPageAlert(error?.response?.data?.detail || error.message || 'Failed to load conversations.')
  }
  scrollToBottom()

  if (typeof window !== 'undefined') {
    window.addEventListener('online', handleReconnect)
  }
})

onUnmounted(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('online', handleReconnect)
  }
})

const handleReconnect = async () => {
  try {
    await chatStore.loadConversations()
    if (activeChatId.value) {
      await chatStore.loadMessages(activeChatId.value, { includeAssistant: true })
    }
  } catch (error) {
    console.error('Failed to refresh after reconnect', error)
  }
}
</script>

<template>
  <div class="chat-layout">
    <!-- Sidebar -->
    <aside class="sidebar" :class="{ 'is-collapsed': isSidebarCollapsed }">
      <div class="sidebar-header">
        <div class="brand">
          <i class="ph" :class="config.branding.brand_icon"></i>
          <span v-if="!isSidebarCollapsed">{{ config.branding.title }}</span>
        </div>
        <div style="display:flex; gap:8px; align-items:center">
          <button class="icon-btn new-chat-btn" @click="handleNewChat" title="New Chat">
            <i class="ph ph-plus"></i>
          </button>
          <button class="icon-btn collapse-btn" @click="isSidebarCollapsed = !isSidebarCollapsed" :title="isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'">
            <i :class="isSidebarCollapsed ? 'ph ph-caret-right' : 'ph ph-caret-left'"></i>
          </button>
        </div>
      </div>
      <div class="history-list">
        <SidebarItem 
          v-for="item in conversations" 
          :key="item.id" 
          :title="item.title" 
          :active="item.active"
          :disabled="item.offline"
          :collapsed="isSidebarCollapsed"
          @select="() => handleSelectConversation(item.id)"
          :on-delete="() => handleDeleteChat(item.id)"
          :on-rename="() => handleRenameChat(item.id)" 
        />
      </div>

      <div class="user-profile" v-if="user">
        <div class="avatar user-avatar-small">
          <i class="ph ph-user"></i>
        </div>
        <div class="user-info" v-if="!isSidebarCollapsed">
          <span class="name">{{ user.displayName || user.email }}</span>
          <span class="email">{{ user.email }} · {{ user.role }}</span>
        </div>
        <div class="user-actions">
          <RouterLink class="icon-btn settings-btn" to="/settings" title="Settings">
            <i class="ph ph-gear-six"></i>
            <span v-if="!isSidebarCollapsed">Settings</span>
          </RouterLink>
          <button class="icon-btn logout-btn" @click="handleLogout" title="Sign Out">
            <i class="ph ph-sign-out"></i>
            <span v-if="!isSidebarCollapsed">Logout</span>
          </button>
        </div>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="main-content">
      <div class="messages-container" ref="messagesContainer">
        <div v-if="showEmptyState" class="empty-state">
          <div class="empty-icon">
            <i class="ph" :class="config.branding.empty_state_icon"></i>
          </div>
        </div>
        <ChatMessage 
          v-for="msg in currentMessages" 
          :key="msg.id" 
          :message="msg" 
        />
        
        <!-- Typing Indicator (Simple) -->
        <!-- Typing Indicator (Animated) -->
        <div v-if="isTyping || hasPendingAssistant" class="typing-indicator-wrapper">
          <div class="avatar assistant-avatar">
            <i class="ph ph-robot"></i>
          </div>
          <div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
          </div>
        </div>
      </div>

      <div class="input-area">
        <ChatInput 
          ref="chatInputRef"
          @send="handleSend" 
          :can-stop="hasPendingAssistant"
          :is-uploading="isUploading"
          :upload-progress="uploadProgress"
          @cancel-upload="handleCancelUpload"
          @stop="handleStopGeneration"
        />
        <p class="disclaimer">AI can make mistakes. Please verify important information.</p>
        <p class="version-tag">Version {{ config.app.version }}</p>
      </div>
    </main>

    <!-- Custom Modal Dialog -->
    <div v-if="showModal" class="modal-overlay" @click="handleModalCancel">
      <div class="modal-dialog" @click.stop>
        <div class="modal-header">
          <h3>{{ modalType === 'confirm' ? 'Confirm' : modalType === 'prompt' ? 'Input Required' : 'Alert' }}</h3>
        </div>
        <div class="modal-body">
          <p>{{ modalMessage }}</p>
          <input v-if="modalType === 'prompt'" v-model="modalInput" 
                 type="text" class="modal-input" 
                 @keyup.enter="handleModalOk" />
        </div>
        <div class="modal-footer">
          <button v-if="modalType !== 'alert'" @click="handleModalCancel" class="btn btn-ghost">
            Cancel
          </button>
          <button @click="handleModalOk" class="btn btn-primary">
            {{ modalType === 'alert' ? 'OK' : 'Confirm' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-layout {
  display: flex;
  height: 100vh;
  width: 100vw;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  overflow: hidden;
}

/* Sidebar */
.sidebar {
  width: 280px;
  background-color: var(--bg-secondary);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  transition: transform var(--transition-normal);
  z-index: 20;
}

/* Collapsed sidebar (mini) */
.sidebar.is-collapsed {
  width: 72px;
}

.collapse-btn i {
  transform: rotate(0deg);
}

.sidebar.is-collapsed .brand span,
.sidebar.is-collapsed .user-info,
.sidebar.is-collapsed .sidebar-item .title {
  display: none !important;
}

.sidebar.is-collapsed .sidebar-item {
  justify-content: center;
}

.sidebar.is-collapsed .sidebar-header {
  padding-left: 12px;
  padding-right: 8px;
}

.sidebar-header {
  padding: var(--space-4);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-weight: 600;
  font-size: 1.1rem;
}

.brand i {
  color: var(--primary);
  font-size: 1.5rem;
}

.new-chat-btn {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.new-chat-btn:hover {
  background: var(--bg-surface);
  color: var(--text-primary);
}

.history-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-2) 0;
}

.user-profile {
  padding: var(--space-4);
  border-top: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-3);
  background: rgba(0,0,0,0.1);
}

.user-avatar-small {
  width: 32px;
  height: 32px;
  background: var(--bg-surface);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
}

.user-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  font-size: 0.85rem;
}

.user-info .name {
  font-weight: 500;
  color: var(--text-primary);
}

.user-info .email {
  color: var(--text-tertiary);
  font-size: 0.75rem;
}

.user-actions {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  align-items: stretch;
}

.sidebar.is-collapsed .user-actions {
  align-items: center;
}

.user-actions .icon-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  padding: 0.35rem 0.5rem;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  text-decoration: none;
  font-size: 0.85rem;
  width: 100%;
  justify-content: center;
}

.user-actions .settings-btn {
  border-color: var(--border-subtle);
}

.user-actions .logout-btn {
  border-color: transparent;
}

.sidebar.is-collapsed .user-actions {
  gap: 0.25rem;
}

.sidebar.is-collapsed .user-actions .icon-btn {
  width: auto;
  justify-content: center;
}

.user-actions .logout-btn:hover,
.user-actions .settings-btn:hover {
  color: var(--text-primary);
  border-color: var(--text-secondary);
}

/* Main Content */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: radial-gradient(circle at top right, #1e293b 0%, var(--bg-primary) 100%);
  position: relative;
}

.messages-container {
  flex: 1;
  padding: 4rem var(--space-6) var(--space-4) var(--space-6); /* Increased top padding */
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  position: relative;
}

.empty-state {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  pointer-events: none;
  opacity: 0.75;
}

.empty-icon {
  display: grid;
  place-items: center;
}

.empty-icon i {
  font-size: min(16vw, 104px);
  color: rgba(226, 232, 240, 0.5);
}

.input-area {
  padding: 0 var(--space-6) var(--space-6) var(--space-6);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}

.disclaimer {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin-bottom: 0;
  margin-top: var(--space-2);
}

.version-tag {
  font-size: 0.7rem;
  color: var(--text-tertiary);
  margin-bottom: 0;
  margin-top: 0;
  letter-spacing: 0.02em;
}

/* Message Container Alignment Wrapper */
.typing-indicator-wrapper {
  width: 100%;
  max-width: 800px;
  margin-left: auto;
  margin-right: auto;
  display: flex;
  gap: var(--space-4);
  padding: 0 var(--space-2); /* Match ChatMessage padding if any, or just consistent alignment */
}

.typing-indicator {
  padding: var(--space-3) var(--space-4);
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.9rem;
  font-style: italic;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.typing-dot {
  width: 6px;
  height: 6px;
  background: var(--text-secondary);
  border-radius: 50%;
  animation: typing 1.4s infinite ease-in-out both;
}

.typing-dot:nth-child(1) { animation-delay: -0.32s; }
.typing-dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes typing {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

/* Responsive */
@media (max-width: 768px) {
  .sidebar {
    position: absolute;
    height: 100%;
    transform: translateX(-100%);
  }
  .sidebar.is-open {
    transform: translateX(0);
  }
}

/* Custom Modal Styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  backdrop-filter: blur(4px);
}

.modal-dialog {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  min-width: 400px;
  max-width: 500px;
  animation: modalSlideIn 0.2s ease-out;
}

@keyframes modalSlideIn {
  from {
    opacity: 0;
    transform: scale(0.9);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.modal-header {
  padding: var(--space-6);
  border-bottom: 1px solid var(--border-subtle);
}

.modal-header h3 {
  margin: 0;
  font-size: 1.25rem;
  color: var(--text-primary);
}

.modal-body {
  padding: var(--space-6);
}

.modal-body p {
  margin: 0 0 var(--space-4) 0;
  color: var(--text-secondary);
}

.modal-input {
  width: 100%;
  padding: var(--space-3);
  background: var(--bg-input);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: 1rem;
}

.modal-input:focus {
  border-color: var(--primary);
  outline: none;
}

.modal-footer {
  padding: var(--space-4) var(--space-6);
  border-top: 1px solid var(--border-subtle);
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
}
</style>
