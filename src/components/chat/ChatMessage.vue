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

const UPLOAD_BASE = (import.meta.env.VITE_UPLOAD_BASE_URL || 'http://localhost:8000/chat_uploads').replace(/\/\/$/, '')

const md = new MarkdownIt()

const renderedContent = computed(() => {
  // Some messages may contain escaped newlines like "\\n" (backslash+n).
  // Convert literal "\\n" sequences back to real newlines so Markdown
  // renders them as intended.
  let raw = (props.message.content || '').replace(/\\n/g, '\n')

  // If users included a fenced code block with a language (e.g. ```python),
  // strip the language specifier so the rendered block does not expose the
  // language label but still renders as a code block that can be copied.
  // Replace any opening fence that has a language token with a plain fence.
  raw = raw.replace(/```[^\n]*\n/g, '```\n')

  return md.render(raw)
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
  if (/^https?:\/\//i.test(rawPath)) return rawPath
  let relative = rawPath
  relative = relative.replace(/^\.?\/*backend\/chat_uploads\//i, '')
  relative = relative.replace(/^\/?chat_uploads\//i, '')
  return `${UPLOAD_BASE}/${relative}`.replace(/([^:]\/)\/+/g, '$1')
}

const imageUrls = computed(() => {
  const content = props.message.content || ''
  const matches = []
  const addMatches = (regex) => {
    const found = content.match(regex)
    if (found) matches.push(...found)
  }
  addMatches(/(?:\.\/)?backend\/chat_uploads\/[^\s)]+/gi)
  addMatches(/\/chat_uploads\/[^\s)]+/gi)
  addMatches(/https?:\/\/[^\s)]+\/chat_uploads\/[^\s)]+/gi)

  const cleaned = matches
    .map((item) => item.replace(/[),.;]+$/, ''))
    .map((item) => normalizeUploadUrl(item))
    .filter((item) => item && /\.(png|jpe?g|gif|webp)$/i.test(item))
  return Array.from(new Set(cleaned))
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
  white-space: pre-wrap; /* Preserve newlines */
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
</style>
