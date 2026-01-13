<script setup>
import { computed, onMounted, watch, nextTick, ref } from 'vue'
import MarkdownIt from 'markdown-it'

const props = defineProps({
  message: {
    type: Object,
    required: true,
    // Expected structure: { id: String, role: 'user' | 'assistant', content: String, timestamp: Date }
  }
})

const getUploadBase = () => {
  // 移除可能存在的 /api 後綴，因為 chat_uploads 是掛載在根路徑，不在 /api 下
  let base = window.__API_BASE__ || ''
  base = base.replace(/\/api\/?$/, '') // 移除結尾的 /api 或 /api/
  return (base ? base.replace(/\/$/, '') + '/chat_uploads' : import.meta.env.VITE_UPLOAD_BASE_URL) || 'http://localhost:8000/chat_uploads'
}

const md = new MarkdownIt({
  html: true,
  breaks: true,
  linkify: true
})


const parsedContent = computed(() => {
  let raw = (props.message.content || '').replace(/\\n/g, '\n')
  
  // Extract LAST occurrence of Answer action_input (in case of multiple LLM calls)
  const answerPattern = /"action"\s*:\s*"[^"]*[Aa]nswer[^"]*"[\s\S]*?"action_input"\s*:\s*"([\s\S]*?)(?:"\s*}|$)/g
  
  let matches = []
  let match
  while ((match = answerPattern.exec(raw)) !== null) {
    matches.push(match[1])
  }
  
  if (matches.length > 0) {
    // Take the LAST match (in case of multiple Answer actions)
    let answer = matches[matches.length - 1]
    // Clean up escaped characters  
    answer = answer.replace(/\\n/g, '\n')
    answer = answer.replace(/\\"/g, '"')
    answer = answer.replace(/\\t/g, '\t')
    // Remove trailing JSON artifacts
    answer = answer.replace(/["}]+\s*$/, '')
    return { finalAnswer: answer.trim() }
  }
  
  // Check if this is AI response (contains JSON markers) or user message
  const isAIResponse = /"action"\s*:/.test(raw) || /"thought"\s*:/.test(raw)
  
  if (isAIResponse) {
    // AI is thinking/searching, don't show anything yet
    return { finalAnswer: '' }
  }
  
  // User message or simple response
  return { finalAnswer: raw.trim() }
})

const renderedContent = computed(() => {
  const parsed = parsedContent.value
  // Don't render if empty to avoid empty HTML tags creating visual space
  if (!parsed.finalAnswer) {
    return ''
  }
  
  // 清理所有完整域名的 chat_uploads URL，統一改為相對路徑
  // 這會處理 markdown 渲染前的文字，確保 "uploaded image" 後面的連結正確
  let cleanedContent = parsed.finalAnswer.replace(
    /https?:\/\/[^\s/]+(?::\d+)?\/(?:api\/)?chat_uploads\//gi,
    '/chat_uploads/'
  )
  
  // 渲染 Markdown
  let html = md.render(cleanedContent)
  
  // 移除 Markdown 中的 <img> 標籤，因為圖片會在下方的 inline-images 區域顯示
  html = html.replace(/<img[^>]*>/gi, '')
  
  // 移除可能產生的空段落
  html = html.replace(/<p>\s*<\/p>/gi, '')
  
  return html
})

const isUser = computed(() => props.message.role === 'user')
const isPendingAssistant = computed(() => !isUser.value && props.message.status === 'pending')
const hasVisibleContent = computed(() => {
  const content = (props.message.content || '').trim()
  const hasFiles = Array.isArray(props.message.files) && props.message.files.length > 0
  return content.length > 0 || hasFiles
})
const hidePendingPlaceholder = computed(() => isPendingAssistant.value && !hasVisibleContent.value)

const normalizeUploadUrl = (rawPath) => {
  if (!rawPath) return null
  let safePath = rawPath.replace(/\\/g, '/')
  
  // If the path contains 'chat_uploads', extract the relative part and re-build it.
  // This handles LLM-generated full URLs (like localhost:8000/api/...) and ensures 
  // they use the current environment's correct API base.
  if (safePath.includes('chat_uploads/')) {
    const parts = safePath.split('chat_uploads/')
    const relative = parts[parts.length - 1]
    return `${getUploadBase()}/${relative}`.replace(/([^:]\/)\/+/g, '$1')
  }

  // Fallback for other http links
  if (/^https?:\/\//i.test(safePath)) return safePath
  
  // Standard relative path handling
  let relative = safePath
  relative = relative.replace(/^\.?\/*backend\//i, '')
  return `${getUploadBase()}/${relative}`.replace(/([^:]\/)\/+/g, '$1')
}

const imageUrls = computed(() => {
  // 先清理 content 中的所有 localhost URL
  const rawContent = (props.message.content || '').replace(/\\/g, '/')
  const content = rawContent.replace(
    /https?:\/\/[^\s/]+(?::\d+)?\/(?:api\/)?chat_uploads\//gi,
    '/chat_uploads/'
  )
  
  const attachmentUrls = Array.isArray(props.message.files)
    ? props.message.files
        .map((file) => normalizeUploadUrl(file.url || file.file_path))
        .filter(Boolean)
        .filter((url) => /\.(png|jpe?g|gif|webp)$/i.test(url)) // 只顯示圖片檔案
    : []
  const matches = []
  const addMatches = (regex) => {
    const found = content.match(regex)
    if (found) matches.push(...found)
  }
  addMatches(/(?:\.\/)? backend\/chat_uploads\/[^\s)]+/gi)
  addMatches(/\/chat_uploads\/[^\s)]+/gi)
  addMatches(/https?:\/\/[^\s)]+\/chat_uploads\/[^\s)]+/gi)

  const cleaned = matches
    .map((item) => item.replace(/[)\],.;，。！？、；：]+$/, ''))
    .map((item) => normalizeUploadUrl(item))
    .filter((item) => item && /\.(png|jpe?g|gif|webp)$/i.test(item))
  const deduped = Array.from(new Set(cleaned))
  const all = Array.from(new Set([...deduped, ...attachmentUrls]))
  
  return all
})

const getFileName = (url) => {
  if (!url) return 'image'
  const cleaned = url.split('?')[0].split('#')[0]
  const parts = cleaned.split('/')
  return parts[parts.length - 1] || 'image'
}

// 元件級的 container ref，避免使用 document.querySelector 全域選取
const containerRef = ref(null)

// 將複製按鈕加到每個 code block 的右上角（只在本元件內尋找）
function addCopyButtons() {
  const container = containerRef.value
  if (!container) return

  const pres = container.querySelectorAll('pre')
  pres.forEach(pre => {
    // 確保 pre 相對定位，以便按鈕絕對定位
    if (!pre.style.position) pre.style.position = 'relative'

    // 若已經插入過按鈕則跳過
    if (pre.querySelector('.copy-btn')) return

    const codeEl = pre.querySelector('code')
    if (!codeEl) return

    const btn = document.createElement('button')
    btn.type = 'button'
    btn.className = 'copy-btn'
    btn.title = '複製程式碼'
    btn.setAttribute('aria-label', '複製程式碼')
    // 使用 SVG icon（簡單剪貼簿）以節省空間並好看
    btn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <path d="M16 1H4a2 2 0 0 0-2 2v14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        <rect x="8" y="4" width="13" height="13" rx="2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>`

    btn.addEventListener('click', async (e) => {
      e.stopPropagation()
      try {
        await navigator.clipboard.writeText(codeEl.textContent || '')
        const original = btn.innerHTML
        btn.innerText = '已複製'
        setTimeout(() => { btn.innerHTML = original }, 1400)
      } catch (err) {
        console.error('Copy failed', err)
        btn.innerText = '錯誤'
        setTimeout(() => { btn.innerHTML = original }, 1400)
      }
    })

    pre.appendChild(btn)
  })
}

onMounted(() => {
  // 初次插入按鈕
  nextTick(() => addCopyButtons())
})

// Debug: log content updates
watch(() => props.message.content, (newVal) => {
   console.log('[ChatMessage] Content updated, length:', newVal ? newVal.length : 0);
})

// 當渲染內容變化時（例如新訊息或內容更新），重新插入按鈕
watch(renderedContent, async () => {
  await nextTick()
  addCopyButtons()
})
</script>

<template>
  <div v-if="!hidePendingPlaceholder" class="message-wrapper">
    <div v-if="!isPendingAssistant" class="avatar" :class="isUser ? 'user-avatar' : 'assistant-avatar'">
      <i class="ph" :class="isUser ? 'ph-smiley' : 'ph-robot'"></i>
    </div>
    
    <div class="message-bubble" :class="{ 'user-bubble': isUser, 'assistant-bubble': !isUser }">
      <!-- File Attachments Preview -->
      <div v-if="message.files && message.files.length > 0" class="files-container">
        <div v-for="(file, index) in message.files" :key="index" class="file-attachment">
          <i class="ph ph-file-text"></i>
          <div class="file-info">
            <span class="file-name">{{ file.name }}</span>
            <span class="file-size">{{ (file.size / 1024).toFixed(1) }} KB</span>
          </div>
          <a v-if="file.url" :href="file.url" :download="file.name" 
             class="download-btn" title="Download">
            <i class="ph ph-download-simple"></i>
          </a>
        </div>
      </div>
      
      <div class="message-content markdown-body" v-html="renderedContent" ref="containerRef"></div>
      <div v-if="imageUrls.length" class="inline-images">
        <div v-for="url in imageUrls" :key="url" class="inline-image-card">
          <img
            :src="url"
            :alt="`uploaded image ${url}`"
            class="inline-image"
            loading="lazy"
          />
          <a
            :href="url"
            :download="getFileName(url)"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-image-download"
            title="Download image"
          >
            <i class="ph ph-download-simple"></i>
            Download
          </a>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-wrapper {
  display: flex;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
  width: 100%;
  max-width: 800px;
  margin-left: auto;
  margin-right: auto;
  /* Always left aligned by default flex behavior */
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 1.25rem;
}

.assistant-avatar {
  background: var(--gradient-primary);
  color: white;
}

.user-avatar {
  background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%); /* Lively Warning/Error gradient (Orange->Red) */
  color: white;
}

.message-bubble {
  padding: var(--space-4) var(--space-6);
  border-radius: var(--radius-lg);
  max-width: 85%;
  line-height: 1.6;
  position: relative;
  transition: all var(--transition-normal);
  font-weight: 450; /* Slightly bolder */
}

.user-bubble {
  background: var(--bg-surface);
  color: #ffffff; /* Pure white for max contrast */
  /* Removed border-bottom-right-radius tweak as it's now left aligned */
}

.assistant-bubble {
  background: transparent;
  color: #ffffff; /* Pure white for max contrast */
  padding-left: 0;
  padding-top: var(--space-2);
  padding-bottom: var(--space-2);
}

/* File Attachment Styles */
.files-container {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.file-attachment {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  background: rgba(139, 92, 246, 0.1);
  border: 1px solid rgba(139, 92, 246, 0.3);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  margin-bottom: var(--space-3);
}

.file-attachment i {
  font-size: 1.5rem;
  color: var(--primary);
}

.file-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-info .file-name {
  font-weight: 500;
  color: #ffffff;
  font-size: 0.9rem;
}

.file-info .file-size {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.download-btn {
  background: transparent;
  border: none;
  color: var(--primary);
  cursor: pointer;
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
  text-decoration: none;
  display: flex;
  align-items: center;
  justify-content: center;
}

.download-btn:hover {
  background: rgba(139, 92, 246, 0.2);
}

.inline-images {
  display: grid;
  gap: var(--space-3);
  margin-top: var(--space-3);
}

.inline-image-card {
  display: grid;
  gap: var(--space-2);
  justify-items: start;
}

.inline-image {
  max-width: 100%;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
}

.inline-image-download {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  color: #ffffff;
  text-decoration: none;
  border: 1px solid rgba(255, 255, 255, 0.12);
  transition: all var(--transition-fast);
  font-size: 0.85rem;
}

.inline-image-download:hover {
  background: rgba(255, 255, 255, 0.16);
  transform: translateY(-1px);
}

/* Markdown Styles */
:deep(.markdown-body) {
  color: #ffffff; /* Ensure root is white */
}

:deep(.markdown-body p), 
:deep(.markdown-body ul), 
:deep(.markdown-body li), 
:deep(.markdown-body span),
:deep(.markdown-body strong),
:deep(.markdown-body em) {
  margin-bottom: var(--space-2);
  /* white-space: pre-wrap; Removed to avoid double breaking with markdown-it breaks:true */
  word-wrap: break-word;
  color: #ffffff; /* Force white on children */
}

:deep(.markdown-body h1), 
:deep(.markdown-body h2), 
:deep(.markdown-body h3) {
  color: #ffffff;
  margin-top: var(--space-4);
  margin-bottom: var(--space-3);
}

:deep(.markdown-body p:last-child) {
  margin-bottom: 0;
}
:deep(.markdown-body code) {
  background: rgba(255,255,255,0.1); /* Lighter background for code inline */
  padding: 0.1rem 0.3rem;
  border-radius: var(--radius-sm);
  font-family: monospace;
  color: var(--accent); /* Keep accent color for code or maybe white? Let's keep accent for pop */
}
:deep(.markdown-body pre) {
  background: #000000;
  padding: var(--space-4);
  border-radius: var(--radius-md);
  overflow-x: auto;
  margin: var(--space-4) 0;
}
:deep(.markdown-body pre code) {
  color: #e2e8f0; /* Light grey for code blocks */
  background: transparent;
  padding: 0;
}
:deep(.markdown-body table) {
  width: 100%;
  border-collapse: collapse;
  margin: var(--space-3) 0;
  color: #ffffff;
}
:deep(.markdown-body th),
:deep(.markdown-body td) {
  border: 1px solid rgba(255, 255, 255, 0.25);
  padding: 0.5rem 0.75rem;
  text-align: left;
  vertical-align: top;
}
:deep(.markdown-body thead th) {
  background: rgba(255, 255, 255, 0.08);
}
:deep(.markdown-body tbody tr:nth-child(even)) {
  background: rgba(255, 255, 255, 0.03);
}
:deep(.markdown-body .copy-btn) {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(255,255,255,0.06);
  color: #e6edf3;
  border: 1px solid rgba(255,255,255,0.06);
  padding: 4px 8px;
  font-size: 0.8rem;
  border-radius: 6px;
  cursor: pointer;
  backdrop-filter: blur(4px);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 28px;
  z-index: 5;
}
:deep(.markdown-body .copy-btn:hover) {
  background: rgba(255,255,255,0.12);
}
:deep(.markdown-body .copy-btn svg) {
  display: block;
  width: 14px;
  height: 14px;
  color: #e6edf3;
}

/* Intermediate Steps Styling */
:deep(.thought-section),
:deep(.action-section),
:deep(.observation-section) {
  margin: var(--space-3) 0;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: rgba(139, 92, 246, 0.08);
  border-left: 3px solid rgba(139, 92, 246, 0.5);
}

:deep(.section-header) {
  font-weight: 600;
  font-size: 0.9rem;
  margin-bottom: var(--space-2);
  color: rgba(139, 92, 246, 1);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

:deep(.section-content) {
  font-size: 0.85rem;
  color: rgba(255, 255, 255, 0.8);
  padding-left: var(--space-4);
}

:deep(.tool-call) {
  font-family: monospace;
  background: rgba(0, 0, 0, 0.2);
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  margin-top: var(--space-2);
}
</style>
