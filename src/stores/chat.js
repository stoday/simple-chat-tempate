import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useChatStore = defineStore('chat', () => {
  // State
  // 1. conversations: meta data list (id, title, active)
  const conversations = ref([
    { id: 1, title: 'Welcome Chat', active: true, date: 'Today' },
  ])
  
  // 2. messagesMap: mapping conversation ID to array of messages
  const messagesMap = ref({
    1: [
      { 
        id: '1', 
        role: 'assistant', 
        content: 'Hello! I am SimpleChat. How can I assist you today?', 
        timestamp: new Date() 
      }
    ]
  })

  // 3. Current active conversation ID
  const activeChatId = ref(1)

  // 4. Current messages (computed or synced ref)
  const currentMessages = ref(messagesMap.value[1])
  
  const isTyping = ref(false)
  // 測試模式：若在開發環境或設定 VITE_TEST_ECHO=true，則回覆固定的回聲訊息
  const testEcho = Boolean(import.meta.env.VITE_TEST_ECHO === 'true' || import.meta.env.DEV)

  // Actions
  const sendMessage = async (text, files = []) => {
    if (!activeChatId.value) return

    // 1. Add User Message
    const userMsg = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date(),
      files: files.length > 0 ? files.map(file => ({
        name: file.name,
        size: file.size,
        type: file.type,
        // In real app, you'd upload to server and get URL
        url: URL.createObjectURL(file)
      })) : null
    }
    
    // Push to map and update current view
    if (!messagesMap.value[activeChatId.value]) {
      messagesMap.value[activeChatId.value] = []
    }
    messagesMap.value[activeChatId.value].push(userMsg)
    
    // 2. Set Typing State
    isTyping.value = true

    // 3. Simulate API/AI Delay
    const delay = Math.min(Math.max(text.length * 20, 1000), 3000)
    await new Promise(resolve => setTimeout(resolve, delay))

    // 4. Add AI Response
    const aiMsg = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: (() => {
        if (!testEcho) return generateMockResponse(text, files)
        // Only wrap in fenced code block if the original message contains a code fence (```)
        if (text && text.includes('```')) {
          // If the original message already contains a fenced code block,
          // echo it unchanged (preserve user's fences) to avoid nesting
          // or creating mismatched fence lengths that confuse the renderer.
          return `received message:\n${text}`
        }
        // Otherwise just echo the raw text (preserve newlines)
        return `received message:\n${text}`
      })(),
      timestamp: new Date()
    }
    messagesMap.value[activeChatId.value].push(aiMsg)
    
    isTyping.value = false
    
    // Auto-rename chat if it's the first exchange and title is default
    const currentChat = conversations.value.find(c => c.id === activeChatId.value)
    if (currentChat && currentChat.title === 'New Chat') {
      currentChat.title = generateTitleFromText(text)
    }
  }

  const selectConversation = (id) => {
    activeChatId.value = id
    
    // Update active flag in list
    conversations.value.forEach(c => c.active = (c.id === id))
    
    // Load messages
    if (!messagesMap.value[id]) {
      messagesMap.value[id] = []
    }
    currentMessages.value = messagesMap.value[id]
  }

  const createNewChat = () => {
    const newId = Date.now()
    const newChat = { id: newId, title: 'New Chat', active: true, date: 'Today' }
    
    // Unshift to top
    conversations.value.unshift(newChat)
    
    // Initialize message array with a welcome message
    messagesMap.value[newId] = [
      { 
        id: Date.now().toString(), // Or a distinct ID
        role: 'assistant', 
        content: 'Hello! I am SimpleChat. How can I assist you today?', 
        timestamp: new Date() 
      }
    ]
    
    // Select it
    selectConversation(newId)
  }

  const deleteConversation = (id) => {
    // Remove from list
    conversations.value = conversations.value.filter(c => c.id !== id)
    // Remove from map
    delete messagesMap.value[id]

    // If we deleted the active chat, select another one
    if (activeChatId.value === id) {
      if (conversations.value.length > 0) {
        selectConversation(conversations.value[0].id)
      } else {
        // No chats left, create a new one automatically
        createNewChat()
      }
    }
  }

  const renameConversation = (id, newTitle) => {
    const chat = conversations.value.find(c => c.id === id)
    if (chat) {
      chat.title = newTitle
    }
  }

  // Helpers
  // 將使用者文字包成安全的 code fence：如果文字內已有多個 backticks，選用更長的 fence
  const fenceText = (text) => {
    if (!text) return '```\n```'
    const matches = text.match(/`+/g)
    const maxBackticks = matches ? Math.max(...matches.map(m => m.length)) : 0
    // 使用最少 3 個反引號，保證為 code block 而非 inline code
    const fenceLen = Math.max(3, maxBackticks + 1)
    const fence = '`'.repeat(fenceLen)
    return `${fence}\n${text}\n${fence}`
  }

  const generateMockResponse = (input, files = []) => {
    if (files.length > 0) {
      const fileList = files.map(f => `**${f.name}**`).join(', ')
      const totalSize = (files.reduce((sum, f) => sum + f.size, 0) / 1024).toFixed(1)
      return `I can see you've uploaded ${files.length} file(s): ${fileList} (Total: ${totalSize} KB). In a real implementation, I would analyze these files and provide relevant insights.`
    }
    
    const responses = [
      "That's an interesting perspective! Tell me more.",
      "I can certainly help with that. Here is a simulated breakdown...",
      "Based on your request, I recommend looking into Vue 3 Composition API.",
      "Could you clarify what you mean by that?",
      "Here is a code snippet:\n```js\nconsole.log('Hello World');\n```"
    ]
    return responses[Math.floor(Math.random() * responses.length)]
  }

  const generateTitleFromText = (text) => {
    return text.slice(0, 30) + (text.length > 30 ? '...' : '')
  }

  return {
    conversations,
    currentMessages,
    activeChatId,
    isTyping,
    sendMessage,
    selectConversation,
    createNewChat,
    deleteConversation,
    renameConversation
  }
})
