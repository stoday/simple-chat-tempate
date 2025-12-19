<script setup>
import { ref, computed, nextTick, watch, onMounted } from 'vue'

const props = defineProps({
  canStop: {
    type: Boolean,
    default: false
  },
  isUploading: {
    type: Boolean,
    default: false
  },
  uploadProgress: {
    type: Number,
    default: 0
  }
})
const emit = defineEmits(['send', 'attach', 'stop', 'cancel-upload'])
const prompt = ref('')
const textareaRef = ref(null)
const fileInputRef = ref(null)
const selectedFiles = ref([])
const isDragging = ref(false)

const showStopButton = computed(() => !!props.canStop)
const isUploading = computed(() => !!props.isUploading)
const canSend = computed(
  () => !showStopButton.value && !isUploading.value && (prompt.value.trim().length > 0 || selectedFiles.value.length > 0)
)
const roundedUploadProgress = computed(() => Math.min(100, Math.max(0, Math.round(props.uploadProgress))))

const updateTextareaHeight = (textarea) => {
  if (!textarea) return
  textarea.style.height = 'auto'
  const computedStyle = window.getComputedStyle(textarea)
  const maxPixels = parseInt(computedStyle.maxHeight, 10)
  const fullHeight = textarea.scrollHeight
  const nextHeight = !Number.isNaN(maxPixels) && maxPixels > 0 ? Math.min(fullHeight, maxPixels) : fullHeight
  textarea.style.height = `${nextHeight}px`
  const hasOverflow = fullHeight > nextHeight + 1
  textarea.style.overflowY = hasOverflow ? 'auto' : 'hidden'
}

const autoResize = (e) => {
  updateTextareaHeight(e.target)
}

const resetHeight = () => {
  if (textareaRef.value) {
    updateTextareaHeight(textareaRef.value)
  }
}

onMounted(() => {
  if (textareaRef.value) {
    updateTextareaHeight(textareaRef.value)
  }
})

watch(() => prompt.value, async () => {
  await nextTick()
  resetHeight()
})

const handleSend = async () => {
  if (!canSend.value) return
  const filesToSend = [...selectedFiles.value]

  emit('send', {
    text: prompt.value,
    files: filesToSend
  })
}

const handleStop = () => {
  emit('stop')
}

const handleKeydown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

const openFilePicker = () => {
  fileInputRef.value?.click()
}

const handleFileSelect = (e) => {
  const files = Array.from(e.target.files || [])
  if (files.length > 0) {
    selectedFiles.value.push(...files)
  }
  e.target.value = ''
}

const removeFile = (index) => {
  selectedFiles.value.splice(index, 1)
}

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
  }
}

const handleCancelUpload = () => {
  emit('cancel-upload')
}

const resetInput = async () => {
  prompt.value = ''
  selectedFiles.value = []
  await nextTick()
  resetHeight()
}

defineExpose({
  resetInput
})
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
        <!-- File preview chips -->
        <div v-if="selectedFiles.length > 0" class="files-preview">
          <div 
            v-for="(file, index) in selectedFiles" 
            :key="`${file.name}-${file.size}-${index}`" 
            class="file-chip"
          >
            <i class="ph ph-file"></i>
            <div class="file-meta">
              <span class="file-name">{{ file.name }}</span>
              <span class="file-size">{{ (file.size / 1024).toFixed(1) }} KB · {{ file.type || 'unknown type' }}</span>
            </div>
            <button class="remove-file-btn" @click="removeFile(index)" type="button" title="Remove">
              <i class="ph ph-x"></i>
            </button>
          </div>
        </div>
        <div v-if="isUploading" class="upload-progress">
          <div class="upload-progress__label">
            <i class="ph ph-arrow-up"></i>
            <span>Uploading files… {{ roundedUploadProgress }}%</span>
            <button type="button" class="cancel-upload-btn" @click="handleCancelUpload">
              Cancel
            </button>
          </div>
          <div class="upload-progress__track">
            <div class="upload-progress__bar" :style="{ width: `${roundedUploadProgress}%` }"></div>
          </div>
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
        v-if="showStopButton"
        class="icon-btn stop-btn"
        type="button"
        @click="handleStop"
        title="Stop response"
      >
        <i class="ph ph-hand-palm"></i>
      </button>

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
  align-items: stretch;
  .prompt-input {
    align-self: stretch;
    width: 100%;
    box-sizing: border-box;
  }
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
  background: rgba(255, 255, 255, 0.08);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: 0.9rem;
  color: var(--text-primary);
  align-self: flex-start;
  border: 1px solid rgba(255, 255, 255, 0.12);
}

.file-chip i {
  color: var(--primary);
  font-size: 1.1rem;
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

.file-size {
  font-size: 0.78rem;
  color: var(--text-secondary);
}

.remove-file-btn {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  transition: all var(--transition-fast);
  font-size: 1rem;
}

.remove-file-btn:hover {
  background: rgba(255, 255, 255, 0.15);
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

.stop-btn {
  background: var(--error);
  color: white;
}

.stop-btn:hover {
  background: #ff4d4f;
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
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-md);
  padding: var(--space-2);
}

.upload-progress__label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.upload-progress__track {
  width: 100%;
  height: 6px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-pill);
  overflow: hidden;
}

.upload-progress__bar {
  height: 100%;
  background: var(--primary);
  border-radius: var(--radius-pill);
  transition: width var(--transition-fast) ease;
}

.cancel-upload-btn {
  margin-left: auto;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.8rem;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  transition: color var(--transition-fast), background var(--transition-fast);
}

.cancel-upload-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--error);
}
</style>
