<script setup>
import { ref, computed, nextTick, watch, onMounted } from 'vue'
import { uploadFiles } from '../../services/api.js'

const emit = defineEmits(['send', 'attach'])
const prompt = ref('')
const textareaRef = ref(null)
const fileInputRef = ref(null)
const selectedFiles = ref([])
const pendingFiles = ref([]) // { id, file, progress, status }
const uploadedFiles = ref([])
const isDragging = ref(false)
const uploading = ref(false)
const uploadProgress = ref(0)

const canSend = computed(() => prompt.value.trim().length > 0 || pendingFiles.value.length > 0 || uploadedFiles.value.length > 0)

const updateTextareaHeight = (textarea) => {
  if (!textarea) return
  textarea.style.height = 'auto'
  const computed = window.getComputedStyle(textarea)
  const maxPixels = parseInt(computed.maxHeight, 10)
  const fullHeight = textarea.scrollHeight
  const nextHeight = !Number.isNaN(maxPixels) && maxPixels > 0 ? Math.min(fullHeight, maxPixels) : fullHeight
  textarea.style.height = `${nextHeight}px`
  const hasOverflow = fullHeight > nextHeight + 1
  textarea.style.overflowY = hasOverflow ? 'auto' : 'hidden'
}

const resetHeight = () => {
  if (textareaRef.value) {
    updateTextareaHeight(textareaRef.value)
  }
}

// 在元件掛載時確保 textarea 初始尺寸正確
onMounted(() => {
  if (textareaRef.value) {
    updateTextareaHeight(textareaRef.value)
  }
})

// 監聽 prompt 的變更，確保任何程式碼路徑更新後 textarea 會自動調整高度
watch(() => prompt.value, async () => {
  await nextTick()
  if (textareaRef.value) {
    try {
      autoResize({ target: textareaRef.value })
    } catch (err) {
      updateTextareaHeight(textareaRef.value)
    }
  }
})

const handleSend = async () => {
  if (!canSend.value) return
  let filesToSend = []

  if (uploadedFiles.value.length > 0) {
    // Use already uploaded metadata
    filesToSend = uploadedFiles.value
  } else if (selectedFiles.value.length > 0) {
    // Upload remaining selected files now
    uploading.value = true
    uploadProgress.value = 0
    // per-file progress tracking for overall progress
    const prog = new Array(selectedFiles.value.length).fill(0)
    try {
      const resp = await uploadFiles(selectedFiles.value, (idx, p) => {
        prog[idx] = p
        // average percent across files
        const avg = Math.round(prog.reduce((a, b) => a + b, 0) / prog.length)
        uploadProgress.value = avg
      })
      filesToSend = resp?.data?.files || []
    } catch (err) {
      console.error('Upload failed:', err)
      filesToSend = selectedFiles.value.map((f) => ({ name: f.name, size: f.size }))
    } finally {
      uploading.value = false
      uploadProgress.value = 0
    }
  }

  // Emit with text and files (uploaded metadata or raw files)
  emit('send', {
    text: prompt.value,
    files: filesToSend.length ? filesToSend : []
  })

  prompt.value = ''
  selectedFiles.value = []
  uploadedFiles.value = []
  await nextTick()
  resetHeight()
}

const handleKeydown = (e) => {
  // Enter without Shift -> send
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
    return
  }

  // For Shift+Enter we let the browser insert a newline naturally.
  // The textarea has @input="autoResize" and a prompt watcher that
  // will adjust the height when the value changes, so no manual
  // insertion is necessary here.
}

const autoResize = (e) => {
  updateTextareaHeight(e.target)
}

const openFilePicker = () => {
  fileInputRef.value?.click()
}

const handleFileSelect = (e) => {
  const files = Array.from(e.target.files || [])
  if (files.length > 0) {
    // add to selectedFiles for parity, and create pending entries
    selectedFiles.value.push(...files)
    const entries = files.map((f) => ({ id: `${Date.now()}-${Math.random().toString(36).slice(2,8)}`, file: f, progress: 0, status: 'uploading' }))
    pendingFiles.value.push(...entries)
    // start upload for these entries
    uploadSelectedFiles(files, entries)
  }
  // Reset input value so same file can be selected again
  e.target.value = ''
}

// Upload a set of File objects and replace them with uploaded metadata
async function uploadSelectedFiles(files, entries) {
  if (!files || files.length === 0) return
  uploading.value = true
  uploadProgress.value = 0
  try {
    const resp = await uploadFiles(files, (idx, p) => {
      // update the corresponding entry progress
      if (entries && entries[idx]) entries[idx].progress = p
    })
    const uploaded = resp?.data?.files || files.map((f) => ({ name: f.name, size: f.size }))
    // append uploaded metadata and remove from pending
    uploaded.forEach((meta, i) => {
      uploadedFiles.value.push(meta)
      // find and remove matching pending entry by id (entries[i])
      const entry = entries && entries[i]
      if (entry) {
        const idxInPending = pendingFiles.value.findIndex((p) => p.id === entry.id)
        if (idxInPending >= 0) pendingFiles.value.splice(idxInPending, 1)
      }
      // remove corresponding from selectedFiles too
      const sfIdx = selectedFiles.value.findIndex((s) => s.name === files[i].name && s.size === files[i].size)
      if (sfIdx >= 0) selectedFiles.value.splice(sfIdx, 1)
    })
  } catch (err) {
    console.error('Immediate upload failed:', err)
    // mark entries as error
    if (entries) entries.forEach((en) => (en.status = 'error'))
  } finally {
    uploading.value = false
    uploadProgress.value = 0
  }
}

const removeFile = (index) => {
  selectedFiles.value.splice(index, 1)
}

const removeUploadedFile = (index) => {
  uploadedFiles.value.splice(index, 1)
}

// Drag and Drop handlers
const handleDragOver = (e) => {
  e.preventDefault()
  isDragging.value = true
}

const handleDragLeave = (e) => {
  e.preventDefault()
  isDragging.value = false
}

const handleDrop = (e) => {
  e.preventDefault()
  isDragging.value = false
  
  const files = Array.from(e.dataTransfer?.files || [])
  if (files.length > 0) {
    selectedFiles.value.push(...files)
    const entries = files.map((f) => ({ id: `${Date.now()}-${Math.random().toString(36).slice(2,8)}`, file: f, progress: 0, status: 'uploading' }))
    pendingFiles.value.push(...entries)
    uploadSelectedFiles(files, entries)
  }
}
</script>

<template>
  <div class="chat-input-container">
    <div 
      class="input-wrapper" 
      :class="{ 'is-dragging': isDragging }"
      @dragover="handleDragOver"
      @dragleave="handleDragLeave"
      @drop="handleDrop"
    >
      <!-- Drag overlay -->
      <div v-if="isDragging" class="drag-overlay">
        <i class="ph ph-upload-simple"></i>
        <span>Drop files here</span>
      </div>
      
      <!-- Hidden file input -->
      <input 
        id="attachments"
        name="attachments"
        ref="fileInputRef" 
        type="file" 
        multiple
        style="display: none" 
        @change="handleFileSelect"
        accept="image/*,.pdf,.doc,.docx,.txt"
        aria-label="Attach files"
      />
      
      <button class="icon-btn attach-btn" @click="openFilePicker" title="Attach file">
        <i class="ph ph-paperclip"></i>
      </button>

      <div class="input-content">
        <!-- Multiple file preview chips -->
        <div v-if="uploadedFiles.length > 0 || selectedFiles.length > 0" class="files-preview">
          <!-- Uploaded files (already uploaded metadata) -->
          <div v-for="(file, index) in uploadedFiles" :key="'u-'+index" class="file-chip file-uploaded">
            <i class="ph ph-check"></i>
            <span class="file-name">{{ file.name }}</span>
            <button class="remove-file-btn" @click="removeUploadedFile(index)" type="button" title="Remove">
              <i class="ph ph-x"></i>
            </button>
          </div>

          <!-- Pending files (local File objects) with per-file progress -->
          <div v-for="(entry, index) in pendingFiles" :key="entry.id" class="file-chip file-pending">
            <i class="ph ph-file"></i>
            <div class="file-meta">
              <span class="file-name">{{ entry.file.name }}</span>
              <div class="file-progress">
                <div class="file-progress-bar" :style="{ width: entry.progress + '%' }"></div>
              </div>
            </div>
            <button class="remove-file-btn" @click="() => { const idx = pendingFiles.findIndex(p=>p.id===entry.id); if(idx>=0) pendingFiles.splice(idx,1) }" type="button" title="Remove">
              <i class="ph ph-x"></i>
            </button>
          </div>
        </div>
        <!-- Upload progress bar (overall) -->
        <div v-if="uploading" class="upload-progress">
          <div class="upload-progress-bar" :style="{ width: uploadProgress + '%' }"></div>
          <div class="upload-progress-text">{{ uploadProgress }}%</div>
        </div>
        
        <textarea
          id="prompt-input"
          name="prompt"
          ref="textareaRef"
          v-model="prompt"
          class="prompt-input"
          placeholder="Send a message..."
          rows="1"
          @keydown="handleKeydown"
          @input="autoResize"
          aria-label="Message input"
        ></textarea>
      </div>

      <button 
        class="icon-btn send-btn" 
        :disabled="!canSend"
        @click="handleSend"
        title="Send message"
      >
        <i class="ph ph-paper-plane-right"></i>
      </button>
    </div>
  </div>
</template>

<style scoped>
.chat-input-container {
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
  position: relative;
}

.input-wrapper {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  display: flex;
  align-items: stretch; /* allow inner column to grow when textarea expands */
  /* Ensure prompt input stretches to fill vertical space of input-content */
  .prompt-input {
    align-self: stretch;
    width: 100%;
    box-sizing: border-box;
  }
  /* Keep icon buttons visually bottom-aligned inside the taller wrapper */
  .icon-btn.send-btn,
  .icon-btn.attach-btn {
    align-self: flex-end;
  }
  padding: var(--space-2);
  gap: var(--space-2);
  box-shadow: var(--shadow-md);
  transition: border-color var(--transition-fast);
}

.input-wrapper:focus-within {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.1);
}

.input-wrapper.is-dragging {
  border-color: var(--primary);
  background: rgba(139, 92, 246, 0.05);
}

.drag-overlay {
  position: absolute;
  inset: 0;
  background: rgba(139, 92, 246, 0.1);
  border: 2px dashed var(--primary);
  border-radius: var(--radius-xl);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  color: var(--primary);
  font-size: 1.2rem;
  font-weight: 500;
  pointer-events: none;
  z-index: 10;
}

.drag-overlay i {
  font-size: 2.5rem;
}

.input-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.files-preview {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.file-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  background: var(--bg-surface);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: 0.85rem;
  color: var(--text-secondary);
  align-self: flex-start;
}

.file-chip i {
  color: var(--primary);
}

.file-name {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.file-progress {
  width: 160px;
  height: 6px;
  background: rgba(255,255,255,0.04);
  border-radius: 999px;
  overflow: hidden;
}

.file-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--primary), var(--primary-hover));
  transition: width 0.15s linear;
}

.file-uploaded i {
  color: var(--success);
}

.remove-file-btn {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
}

.remove-file-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: var(--error);
}

.prompt-input {
  flex: 0 0 auto;
  width: 100%;
  box-sizing: border-box;
  background: transparent;
  border: none;
  color: var(--text-primary);
  padding: var(--space-3) var(--space-2);
  resize: none;
  max-height: 200px;
  overflow-y: auto;
  font-family: inherit;
  font-size: 1rem;
  line-height: 1.5;
}

.prompt-input:focus {
  outline: none;
}

.prompt-input::placeholder {
  color: var(--text-tertiary);
}

.icon-btn {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--transition-fast);
  font-size: 1.25rem;
}

.icon-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary);
}

.send-btn {
  background: var(--primary);
  color: white;
}

.send-btn:hover:not(:disabled) {
  background: var(--primary-hover);
}

.send-btn:disabled {
  background: transparent;
  color: var(--text-tertiary);
  cursor: not-allowed;
  opacity: 0.5;
}

.upload-progress {
  position: relative;
  height: 10px;
  background: rgba(255,255,255,0.06);
  border-radius: 999px;
  overflow: hidden;
  margin-top: var(--space-2);
}

.upload-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--primary), var(--primary-hover));
  transition: width 0.2s ease;
}

.upload-progress-text {
  margin-top: 6px;
  font-size: 0.8rem;
  color: var(--text-secondary);
}
</style>
