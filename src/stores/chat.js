import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import apiClient from '../services/api'

const UPLOAD_BASE = (import.meta.env.VITE_UPLOAD_BASE_URL || 'http://localhost:8000/chat_uploads').replace(/\/\/$/, '')

const buildUploadUrl = (relativePath) => {
  if (!relativePath) return null
  return `${UPLOAD_BASE}/${relativePath}`.replace(/([^:]\/)\/+/g, '$1')
}

const formatFileFromApi = (file) => ({
  id: file.id,
  name: file.file_name,
  size: file.size_bytes ?? 0,
  type: file.mime_type || 'application/octet-stream',
  url: buildUploadUrl(file.file_path)
})

const formatMessageFromApi = (message) => ({
  id: String(message.id),
  conversationId: message.conversation_id ? String(message.conversation_id) : null,
  role: message.sender_type === 'assistant' ? 'assistant' : 'user',
  content: message.content,
  status: message.status || 'completed',
  parentMessageId: message.parent_message_id ? String(message.parent_message_id) : null,
  stoppedAt: message.stopped_at || null,
  timestamp: message.created_at,
  files: Array.isArray(message.files) ? message.files.map(formatFileFromApi) : []
})

const formatConversationFromApi = (conversation) => ({
  id: String(conversation.id),
  title: conversation.title || 'New Chat',
  createdAt: conversation.created_at,
  updatedAt: conversation.updated_at,
  messageCount: conversation.message_count ?? 0,
  active: false
})

const FORCE_NEW_CHAT_KEY = 'force_new_chat_on_login'

export const useChatStore = defineStore('chat', () => {
  let activeUploadController = null
  const conversations = ref([])
  const activeChatId = ref(null)
  const messagesMap = ref({})
  const isTyping = ref(false)
  const isUploading = ref(false)
  const uploadProgress = ref(0)
  const isLoadingHistory = ref(false)
  const isLoadingConversations = ref(false)
  const error = ref(null)
  const pendingRefreshTimers = new Map()

  const currentMessages = computed(() => messagesMap.value[activeChatId.value] || [])
  const pendingAssistantMessage = computed(() => {
    const convId = activeChatId.value
    if (!convId) return null
    return (messagesMap.value[convId] || []).find((msg) => msg.role === 'assistant' && msg.status === 'pending') || null
  })
  const hasPendingAssistant = computed(() => !!pendingAssistantMessage.value)

  const schedulePendingRefresh = (conversationId, delay = 1500) => {
    if (typeof window === 'undefined') return
    const handle = pendingRefreshTimers.get(conversationId)
    if (handle) clearTimeout(handle)
    const timeout = window.setTimeout(async () => {
      pendingRefreshTimers.delete(conversationId)
      try {
        await loadMessages(conversationId, { includeAssistant: true })
      } catch (err) {
        console.error('Failed to refresh pending messages', err)
      }
    }, delay)
    pendingRefreshTimers.set(conversationId, timeout)
  }

  const clearPendingRefresh = (conversationId) => {
    const handle = pendingRefreshTimers.get(conversationId)
    if (handle) {
      clearTimeout(handle)
      pendingRefreshTimers.delete(conversationId)
    }
  }

  const setMessagesForConversation = (conversationId, messages) => {
    messagesMap.value = {
      ...messagesMap.value,
      [conversationId]: messages
    }
  }

  const ensureMessageBucket = (conversationId) => {
    if (!messagesMap.value[conversationId]) {
      setMessagesForConversation(conversationId, [])
    }
    return messagesMap.value[conversationId]
  }

  const removeMessagesForConversation = (conversationId) => {
    const { [conversationId]: _removed, ...rest } = messagesMap.value
    messagesMap.value = rest
  }

  const setActiveConversation = (conversationId) => {
    if (!conversationId) {
      activeChatId.value = null
      conversations.value.forEach((conv) => {
        conv.active = false
      })
      pendingRefreshTimers.forEach((handle) => clearTimeout(handle))
      pendingRefreshTimers.clear()
      return
    }
    activeChatId.value = conversationId
    conversations.value.forEach((conv) => {
      conv.active = conv.id === conversationId
    })
    ensureMessageBucket(conversationId)
  }

  const bumpConversation = (conversationId, updates = {}) => {
    const idx = conversations.value.findIndex((conv) => conv.id === conversationId)
    if (idx === -1) return
    const conv = { ...conversations.value[idx], ...updates }
    conversations.value.splice(idx, 1)
    conversations.value.unshift(conv)
    setActiveConversation(conversationId)
  }

  const loadConversations = async () => {
    isLoadingConversations.value = true
    error.value = null
    try {
      let list = []
      const { data } = await apiClient.get('/conversations')
      list = Array.isArray(data) ? data : []
      if (!list.length) {
        const created = await apiClient.post('/conversations', { title: 'New Chat' })
        list = [created.data]
      }
      const formatted = list.map((item) => formatConversationFromApi(item))
    const desiredActive = activeChatId.value && formatted.some((c) => c.id === activeChatId.value)
        ? activeChatId.value
        : formatted[0]?.id || null
      formatted.forEach((conv) => {
        conv.active = conv.id === desiredActive
      })
      conversations.value = formatted
      if (desiredActive) {
        setActiveConversation(desiredActive)
      } else {
        activeChatId.value = null
      }
      return formatted
    } catch (err) {
      error.value = err?.response?.data?.detail || err.message || 'Failed to load conversations'
      throw err
    } finally {
      isLoadingConversations.value = false
    }
  }

  const loadMessages = async (conversationId = activeChatId.value, { includeAssistant = true } = {}) => {
    if (!conversationId) {
      return []
    }
    isLoadingHistory.value = true
    error.value = null
    try {
      const { data } = await apiClient.get('/messages', {
        params: {
          conversation_id: conversationId,
          include_assistant: includeAssistant
        }
      })
      const formatted = Array.isArray(data) ? data.map(formatMessageFromApi) : []
      setMessagesForConversation(conversationId, formatted)
      const hasPending = formatted.some((msg) => msg.role === 'assistant' && msg.status === 'pending')
      if (hasPending) {
        schedulePendingRefresh(conversationId)
      } else {
        clearPendingRefresh(conversationId)
      }
      return formatted
    } catch (err) {
      error.value = err?.response?.data?.detail || err.message || 'Failed to load messages'
      throw err
    } finally {
      isLoadingHistory.value = false
    }
  }

  const initialize = async () => {
    const forceNewChat = typeof window !== 'undefined' && localStorage.getItem(FORCE_NEW_CHAT_KEY) === '1'
    if (forceNewChat) {
      localStorage.removeItem(FORCE_NEW_CHAT_KEY)
      await createNewChat()
      await loadConversations()
    } else {
      await loadConversations()
    }
    if (activeChatId.value) {
      await loadMessages(activeChatId.value, { includeAssistant: true })
    }
  }

  const selectConversation = async (conversationId) => {
    if (!conversationId) return
    setActiveConversation(conversationId)
    await loadMessages(conversationId, { includeAssistant: true })
  }

  const createNewChat = async (title = 'New Chat') => {
    error.value = null
    try {
      const { data } = await apiClient.post('/conversations', { title })
      const formatted = formatConversationFromApi(data)
      conversations.value.forEach((conv) => {
        conv.active = false
      })
      formatted.active = true
      conversations.value.unshift(formatted)
      setActiveConversation(formatted.id)
      setMessagesForConversation(formatted.id, [])
      return formatted
    } catch (err) {
      error.value = err?.response?.data?.detail || err.message || 'Failed to create chat'
      throw err
    }
  }

  const deleteConversation = async (conversationId) => {
    error.value = null
    try {
      await apiClient.delete(`/conversations/${conversationId}`)
      conversations.value = conversations.value.filter((conv) => conv.id !== conversationId)
      removeMessagesForConversation(conversationId)
      clearPendingRefresh(conversationId)
      if (activeChatId.value === conversationId) {
        const fallback = conversations.value[0]
        if (fallback) {
          setActiveConversation(fallback.id)
          await loadMessages(fallback.id, { includeAssistant: true })
        } else {
          await initialize()
        }
      }
    } catch (err) {
      error.value = err?.response?.data?.detail || err.message || 'Failed to delete chat'
      throw err
    }
  }

  const renameConversation = async (conversationId, newTitle) => {
    error.value = null
    try {
      const { data } = await apiClient.patch(`/conversations/${conversationId}`, { title: newTitle })
      const formatted = formatConversationFromApi(data)
      const idx = conversations.value.findIndex((conv) => conv.id === conversationId)
      if (idx !== -1) {
        const wasActive = conversations.value[idx].active
        conversations.value[idx] = { ...formatted, active: wasActive }
        if (wasActive) {
          setActiveConversation(conversationId)
        }
      }
      return formatted
    } catch (err) {
      error.value = err?.response?.data?.detail || err.message || 'Failed to rename chat'
      throw err
    }
  }

  const sendMessage = async (text, files = []) => {
    const conversationId = activeChatId.value
    if (!conversationId) {
      throw new Error('No conversation selected')
    }
    const trimmed = text?.trim() ?? ''
    const outgoingFiles = Array.isArray(files) ? files : []
    const hasFiles = outgoingFiles.length > 0

    if (!trimmed && outgoingFiles.length === 0) {
      return
    }

    const formData = new FormData()
    formData.append('conversation_id', conversationId)
    formData.append('content', trimmed)

    outgoingFiles.forEach((file) => {
      if (file instanceof File || (typeof Blob !== 'undefined' && file instanceof Blob)) {
        formData.append('files', file)
      }
    })

    const controller = hasFiles ? new AbortController() : null
    if (controller) {
      activeUploadController = controller
    }

    try {
      isTyping.value = true
      if (hasFiles) {
        uploadProgress.value = 0
        isUploading.value = true
      }
      const { data } = await apiClient.post('/messages', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: hasFiles ? 0 : undefined,
        signal: controller?.signal,
        onUploadProgress: hasFiles
          ? (progressEvent) => {
              const total = progressEvent.total || progressEvent.target?.getResponseHeader?.('content-length') || 0
              if (total) {
                uploadProgress.value = Math.min(100, Math.round((progressEvent.loaded * 100) / total))
              } else if (uploadProgress.value < 95) {
                uploadProgress.value = Math.min(95, uploadProgress.value + 5)
              }
            }
          : undefined
      })

      const appended = []
      if (data?.message) appended.push(formatMessageFromApi(data.message))
      if (data?.simulated_reply) appended.push(formatMessageFromApi(data.simulated_reply))
      if (appended.length) {
        const existing = ensureMessageBucket(conversationId)
        setMessagesForConversation(conversationId, [...existing, ...appended])
      }
      if (data?.simulated_reply?.status === 'pending') {
        schedulePendingRefresh(conversationId)
      }
      bumpConversation(conversationId, { updatedAt: new Date().toISOString() })
    } catch (err) {
      const isCanceled = err?.code === 'ERR_CANCELED' || err?.message === 'canceled'
      if (!isCanceled) {
        error.value = err?.response?.data?.detail || err.message || 'Failed to send message'
      }
      throw err
    } finally {
      isTyping.value = false
      if (controller && activeUploadController === controller) {
        activeUploadController = null
      }
      if (hasFiles) {
        uploadProgress.value = 100
        setTimeout(() => {
          isUploading.value = false
          uploadProgress.value = 0
        }, 300)
      } else {
        isUploading.value = false
        uploadProgress.value = 0
      }
    }
  }

  const cancelUpload = () => {
    if (activeUploadController) {
      activeUploadController.abort()
      activeUploadController = null
    }
  }

  const stopGenerating = async () => {
    const conversationId = activeChatId.value
    const pending = pendingAssistantMessage.value
    if (!conversationId || !pending) return
    try {
      await apiClient.post(`/messages/${pending.id}/stop`)
      clearPendingRefresh(conversationId)
      await loadMessages(conversationId, { includeAssistant: true })
    } catch (err) {
      error.value = err?.response?.data?.detail || err.message || 'Failed to stop response'
      throw err
    }
  }

  return {
    conversations,
    currentMessages,
    activeChatId,
    isTyping,
    isLoadingHistory,
    isLoadingConversations,
    error,
    isUploading,
    uploadProgress,
    hasPendingAssistant,
    pendingAssistantMessage,
    loadConversations,
    loadMessages,
    selectConversation,
    createNewChat,
    deleteConversation,
    renameConversation,
    sendMessage,
    cancelUpload,
    stopGenerating,
    initialize
  }
})
