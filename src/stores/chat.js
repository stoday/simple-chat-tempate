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

const CONVERSATION_CACHE_KEY = 'chat_conversations_cache'
const OFFLINE_PLACEHOLDER_ID = 'offline-new-chat'

const loadCachedConversations = () => {
  if (typeof window === 'undefined') return []
  try {
    const raw = localStorage.getItem(CONVERSATION_CACHE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch (err) {
    console.warn('Failed to parse cached conversations', err)
    return []
  }
}

const saveCachedConversations = (list) => {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(CONVERSATION_CACHE_KEY, JSON.stringify(list))
  } catch (err) {
    console.warn('Failed to cache conversations', err)
  }
}

const applyActiveToConversations = (list, desiredActive) => {
  const fallbackActive = desiredActive || list[0]?.id || null
  list.forEach((conv) => {
    conv.active = conv.id === fallbackActive
  })
  return fallbackActive
}

const buildOfflinePlaceholder = () => ({
  id: OFFLINE_PLACEHOLDER_ID,
  title: 'New Chat (offline)',
  createdAt: null,
  updatedAt: null,
  messageCount: 0,
  active: false,
  offline: true
})

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
      } finally {
        if (pendingRefreshTimers.has(conversationId)) return
        const bucket = messagesMap.value[conversationId] || []
        const stillPending = bucket.some((msg) => msg.role === 'assistant' && msg.status === 'pending')
        if (stillPending) {
          schedulePendingRefresh(conversationId, delay)
        }
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
      applyActiveToConversations(formatted, desiredActive)
      conversations.value = formatted
      saveCachedConversations(formatted)
      if (desiredActive) {
        setActiveConversation(desiredActive)
      } else {
        activeChatId.value = null
      }
      return formatted
    } catch (err) {
      error.value = err?.response?.data?.detail || err.message || 'Failed to load conversations'
      if (!conversations.value.length) {
        const cached = loadCachedConversations()
        if (cached.length) {
          const desiredActive = activeChatId.value && cached.some((c) => c.id === activeChatId.value)
            ? activeChatId.value
            : cached[0]?.id || null
          applyActiveToConversations(cached, desiredActive)
          conversations.value = cached
          if (desiredActive) {
            setActiveConversation(desiredActive)
          }
        } else {
          conversations.value = [buildOfflinePlaceholder()]
          activeChatId.value = null
        }
      }
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
      
      // Handle potential new object format: { messages, conversation_title }
      let rawMessages = []
      let newTitle = null
      
      if (data && typeof data === 'object' && !Array.isArray(data)) {
        rawMessages = data.messages || []
        newTitle = data.conversation_title
      } else {
        rawMessages = Array.isArray(data) ? data : []
      }

      const formatted = rawMessages.map(formatMessageFromApi)
      setMessagesForConversation(conversationId, formatted)
      
      // Update local conversation title if it changed from "New Chat" or shifted on backend
      if (newTitle) {
        const idx = conversations.value.findIndex(c => c.id === String(conversationId))
        if (idx !== -1 && conversations.value[idx].title !== newTitle) {
          conversations.value[idx].title = newTitle
          saveCachedConversations(conversations.value)
        }
      }

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
    await loadConversations()
    const latest = conversations.value[0]
    if (latest && latest.messageCount > 0) {
      await createNewChat()
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
      saveCachedConversations(conversations.value)
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
      saveCachedConversations(conversations.value)
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
        saveCachedConversations(conversations.value)
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
      if (data?.reply) appended.push(formatMessageFromApi(data.reply))
      if (appended.length) {
        const existing = ensureMessageBucket(conversationId)
        setMessagesForConversation(conversationId, [...existing, ...appended])
      }

      // 如果有回覆且狀態是 pending，開啟串流連線
      if (data?.reply?.status === 'pending') {
        connectToStream(data.reply.id, conversationId)
      } else if (data?.reply?.status === 'completed') {
        // 如果已經完成（極端快速的情況），也要更新一下
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
    const existing = ensureMessageBucket(conversationId)
    const cancellationText = pending.content || 'Response cancelled by user.'
    const updatedMessages = existing.map((msg) => {
      if (msg.id !== pending.id) return msg
      return {
        ...msg,
        status: 'cancelled',
        content: cancellationText,
        stoppedAt: new Date().toISOString()
      }
    })
    setMessagesForConversation(conversationId, updatedMessages)
    clearPendingRefresh(conversationId)
    try {
      await apiClient.post(`/messages/${pending.id}/stop`)
      await loadMessages(conversationId, { includeAssistant: true })
    } catch (err) {
      error.value = err?.response?.data?.detail || err.message || 'Failed to stop response'
      await loadMessages(conversationId, { includeAssistant: true })
      throw err
    }
  }

  const connectToStream = (messageId, conversationId) => {
    const token = localStorage.getItem('auth_token')
    const baseUrl = apiClient.defaults.baseURL
    const streamUrl = `${baseUrl}/messages/${messageId}/stream?token=${token}`
    
    const eventSource = new EventSource(streamUrl)
    let currentText = ''

    eventSource.onmessage = (event) => {
      if (event.data === '[DONE]') {
        eventSource.close()
        // 串流結束，更新訊息狀態為 completed
        refreshMessageStatus(messageId, conversationId)
        return
      }

      try {
        console.log('[Stream Raw]:', event.data);
        const data = JSON.parse(event.data)
        if (data.token) {
          console.log('[Stream Token]:', data.token);
          currentText += data.token
          console.log('[Stream CurrentText]:', currentText);
          updateMessageContent(messageId, conversationId, currentText)
        }
        if (data.error) {
          console.error('Stream error:', data.error)
          eventSource.close()
          schedulePendingRefresh(conversationId)
        }
      } catch (err) {
        // Ignore parse errors
      }
    }

    eventSource.onerror = (err) => {
      console.error('EventSource failed:', err)
      eventSource.close()
      // 如果串流失敗，退回原本的輪詢機制
      schedulePendingRefresh(conversationId)
    }
  }

  const updateMessageContent = (messageId, conversationId, content) => {
    const bucket = messagesMap.value[conversationId]
    if (!bucket) return
    
    const idx = bucket.findIndex((m) => m.id === String(messageId))
    if (idx !== -1) {
      // Directly mutate the content to trigger fine-grained reactivity
      bucket[idx].content = content
      // Force trigger if needed, but deep ref should handle it.
      // If bucket is large, replacing it might be glitchy.
      // But we are in a Store.
    }
  }

  const refreshMessageStatus = async (messageId, conversationId) => {
    await loadMessages(conversationId)
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
    connectToStream,
    initialize
  }
})
