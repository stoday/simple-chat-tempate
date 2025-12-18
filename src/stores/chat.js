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

export const useChatStore = defineStore('chat', () => {
  const conversations = ref([])
  const activeChatId = ref(null)
  const messagesMap = ref({})
  const isTyping = ref(false)
  const isLoadingHistory = ref(false)
  const isLoadingConversations = ref(false)
  const error = ref(null)

  const currentMessages = computed(() => messagesMap.value[activeChatId.value] || [])

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
      return formatted
    } catch (err) {
      error.value = err?.response?.data?.detail || err.message || 'Failed to load messages'
      throw err
    } finally {
      isLoadingHistory.value = false
    }
  }

  const initialize = async () => {
    await loadConversations()
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

    try {
      isTyping.value = true
      const { data } = await apiClient.post('/messages', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })

      const appended = []
      if (data?.message) appended.push(formatMessageFromApi(data.message))
      if (data?.simulated_reply) appended.push(formatMessageFromApi(data.simulated_reply))
      if (appended.length) {
        const existing = ensureMessageBucket(conversationId)
        setMessagesForConversation(conversationId, [...existing, ...appended])
      }
      bumpConversation(conversationId, { updatedAt: new Date().toISOString() })
    } catch (err) {
      error.value = err?.response?.data?.detail || err.message || 'Failed to send message'
      throw err
    } finally {
      isTyping.value = false
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
    loadConversations,
    loadMessages,
    selectConversation,
    createNewChat,
    deleteConversation,
    renameConversation,
    sendMessage,
    initialize
  }
})
