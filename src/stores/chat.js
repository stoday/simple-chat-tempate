import { defineStore } from 'pinia'
import { ref } from 'vue'
import apiClient from '../services/api'

const DEFAULT_CHAT_ID = 'default'
const UPLOAD_BASE = (import.meta.env.VITE_UPLOAD_BASE_URL || 'http://localhost:8000/chat_uploads').replace(/\/$/, '')

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
  role: message.sender_type === 'assistant' ? 'assistant' : 'user',
  content: message.content,
  timestamp: message.created_at,
  files: Array.isArray(message.files) ? message.files.map(formatFileFromApi) : []
})

export const useChatStore = defineStore('chat', () => {
  const conversations = ref([
    { id: DEFAULT_CHAT_ID, title: 'Default Chat', active: true, date: 'Today' }
  ])
  const messagesMap = ref({
    [DEFAULT_CHAT_ID]: []
  })
  const activeChatId = ref(DEFAULT_CHAT_ID)
  const currentMessages = ref(messagesMap.value[DEFAULT_CHAT_ID])
  const isTyping = ref(false)
  const isLoadingHistory = ref(false)

  const ensureConversationArray = (chatId) => {
    if (!messagesMap.value[chatId]) {
      messagesMap.value[chatId] = []
    }
    return messagesMap.value[chatId]
  }

  const appendMessageToActive = (message) => {
    const bucket = ensureConversationArray(activeChatId.value)
    bucket.push(message)
    currentMessages.value = bucket
  }

  const loadMessages = async () => {
    isLoadingHistory.value = true
    try {
      const { data } = await apiClient.get('/messages', {
        params: { include_assistant: true }
      })
      const formatted = Array.isArray(data) ? data.map(formatMessageFromApi) : []
      messagesMap.value[DEFAULT_CHAT_ID] = formatted
      if (activeChatId.value === DEFAULT_CHAT_ID) {
        currentMessages.value = formatted
      }
    } finally {
      isLoadingHistory.value = false
    }
  }

  const sendMessage = async (text, files = []) => {
    const trimmed = text?.trim()
    const outgoingFiles = Array.isArray(files) ? files : []

    if (!trimmed && outgoingFiles.length === 0) {
      return
    }

    const formData = new FormData()
    formData.append('content', trimmed || '')

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

      if (data?.message) {
        appendMessageToActive(formatMessageFromApi(data.message))
      }
      if (data?.simulated_reply) {
        appendMessageToActive(formatMessageFromApi(data.simulated_reply))
      }
    } catch (error) {
      console.error('Failed to send message', error)
      throw error
    } finally {
      isTyping.value = false
    }
  }

  const selectConversation = (id) => {
    activeChatId.value = id
    conversations.value.forEach((c) => {
      c.active = c.id === id
    })
    currentMessages.value = ensureConversationArray(id)
  }

  const createNewChat = () => {
    const newId = Date.now().toString()
    conversations.value.forEach((c) => {
      c.active = false
    })
    const newChat = { id: newId, title: 'New Chat', active: true, date: 'Today' }
    conversations.value.unshift(newChat)
    messagesMap.value[newId] = []
    activeChatId.value = newId
    currentMessages.value = messagesMap.value[newId]
  }

  const deleteConversation = (id) => {
    conversations.value = conversations.value.filter((c) => c.id !== id)
    delete messagesMap.value[id]

    if (activeChatId.value === id) {
      if (conversations.value.length > 0) {
        selectConversation(conversations.value[0].id)
      } else {
        const fallbackId = Date.now().toString()
        const fallbackChat = { id: fallbackId, title: 'New Chat', active: true, date: 'Today' }
        conversations.value = [fallbackChat]
        messagesMap.value[fallbackId] = []
        activeChatId.value = fallbackId
        currentMessages.value = messagesMap.value[fallbackId]
      }
    }
  }

  const renameConversation = (id, newTitle) => {
    const chat = conversations.value.find((c) => c.id === id)
    if (chat) {
      chat.title = newTitle
    }
  }

  return {
    conversations,
    currentMessages,
    activeChatId,
    isTyping,
    isLoadingHistory,
    sendMessage,
    loadMessages,
    selectConversation,
    createNewChat,
    deleteConversation,
    renameConversation
  }
})
