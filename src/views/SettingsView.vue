<script setup>
import { reactive, ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import apiClient from '../services/api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const isAdmin = computed(() => authStore.user?.role === 'admin')
const canEditDisplayName = computed(() => isAdmin.value)

const accountForm = reactive({
  email: '',
  displayName: '',
  password: '',
})

const accountStatus = ref(null)
const accountSaving = ref(false)

watch(
  () => authStore.user,
  (val) => {
    accountForm.email = val?.email || ''
    accountForm.displayName = val?.displayName || ''
    accountForm.password = ''
  },
  { immediate: true },
)

const submitAccount = async () => {
  if (!authStore.user) return
  const payload = {}
  if (accountForm.email && accountForm.email !== authStore.user.email) {
    payload.email = accountForm.email
  }
  if (canEditDisplayName.value && accountForm.displayName !== (authStore.user.displayName || '')) {
    payload.display_name = accountForm.displayName
  }
  if (accountForm.password) {
    payload.password = accountForm.password
  }
  if (Object.keys(payload).length === 0) {
    accountStatus.value = { type: 'info', text: 'No changes to save.' }
    return
  }
  accountSaving.value = true
  accountStatus.value = null
  try {
    const { data } = await apiClient.patch(`/users/${authStore.user.id}`, payload)
    authStore.syncUserFromApi(data)
    accountStatus.value = { type: 'success', text: 'Account updated successfully.' }
    accountForm.password = ''
  } catch (err) {
    accountStatus.value = {
      type: 'error',
      text: err?.response?.data?.detail || err.message || 'Failed to update account.',
    }
  } finally {
    accountSaving.value = false
  }
}

const users = ref([])
const usersLoading = ref(false)
const adminNotice = ref(null)
const ragFiles = ref([])
const ragLoading = ref(false)
const ragNotice = ref(null)
const ragUploading = ref(false)
const ragDragActive = ref(false)
const mssqlNotice = ref(null)
const mssqlSaving = ref(false)
const mssqlTesting = ref(false)
const mssqlForm = reactive({
  server: '',
  database: '',
  username: '',
  password: '',
  useTrusted: false
})
const editingUserId = ref(null)
const editForm = reactive({
  email: '',
  displayName: '',
  role: 'user',
  password: '',
})

const loadUsers = async () => {
  if (!isAdmin.value) return
  usersLoading.value = true
  adminNotice.value = null
  try {
    const { data } = await apiClient.get('/users')
    users.value = data
  } catch (err) {
    adminNotice.value = { type: 'error', text: err?.response?.data?.detail || 'Failed to load users.' }
  } finally {
    usersLoading.value = false
  }
}

const loadRagFiles = async () => {
  if (!isAdmin.value) return
  ragLoading.value = true
  ragNotice.value = null
  try {
    const { data } = await apiClient.get('/admin/rag-files')
    ragFiles.value = Array.isArray(data) ? data : []
  } catch (err) {
    ragNotice.value = { type: 'error', text: err?.response?.data?.detail || 'Failed to load RAG files.' }
  } finally {
    ragLoading.value = false
  }
}

const loadMssqlConfig = async () => {
  if (!isAdmin.value) return
  mssqlNotice.value = null
  try {
    const { data } = await apiClient.get('/admin/mssql-config')
    mssqlForm.server = data?.server || ''
    mssqlForm.database = data?.database || ''
    mssqlForm.username = data?.username || ''
    mssqlForm.password = data?.password || ''
    mssqlForm.useTrusted = !!data?.use_trusted
  } catch (err) {
    mssqlNotice.value = { type: 'error', text: err?.response?.data?.detail || 'Failed to load MSSQL config.' }
  }
}

onMounted(() => {
  if (isAdmin.value) {
    loadUsers()
    loadRagFiles()
    loadMssqlConfig()
  }
})

watch(isAdmin, (value) => {
  if (value && users.value.length === 0) {
    loadUsers()
  }
  if (value && ragFiles.value.length === 0) {
    loadRagFiles()
    loadMssqlConfig()
  }
})

const startEditUser = (user) => {
  editingUserId.value = user.id
  editForm.email = user.email
  editForm.displayName = user.display_name || user.displayName || ''
  editForm.role = user.role
  editForm.password = ''
}

const cancelEditUser = () => {
  editingUserId.value = null
  editForm.email = ''
  editForm.displayName = ''
  editForm.role = 'user'
  editForm.password = ''
}

const saveUser = async () => {
  if (!editingUserId.value) return
  const original = users.value.find((u) => u.id === editingUserId.value)
  if (!original) return
  const payload = {}
  if (editForm.email !== original.email) payload.email = editForm.email
  if (editForm.displayName !== (original.display_name || original.displayName || '')) {
    payload.display_name = editForm.displayName
  }
  if (editForm.role !== original.role) payload.role = editForm.role
  if (editForm.password) payload.password = editForm.password
  if (Object.keys(payload).length === 0) {
    adminNotice.value = { type: 'info', text: 'No changes for this user.' }
    cancelEditUser()
    return
  }
  adminNotice.value = null
  try {
    const { data } = await apiClient.patch(`/users/${editingUserId.value}`, payload)
    users.value = users.value.map((u) => (u.id === data.id ? data : u))
    if (authStore.user && data.id === authStore.user.id) {
      authStore.syncUserFromApi(data)
      accountForm.email = authStore.user.email
      accountForm.displayName = authStore.user.displayName || ''
    }
    adminNotice.value = { type: 'success', text: 'User updated.' }
  } catch (err) {
    adminNotice.value = { type: 'error', text: err?.response?.data?.detail || 'Failed to update user.' }
  } finally {
    cancelEditUser()
  }
}

const deleteUser = async (user) => {
  if (!window.confirm(`Delete ${user.email}?`)) return
  try {
    await apiClient.delete(`/users/${user.id}`)
    users.value = users.value.filter((u) => u.id !== user.id)
    adminNotice.value = { type: 'success', text: 'User deleted.' }
  } catch (err) {
    adminNotice.value = { type: 'error', text: err?.response?.data?.detail || 'Failed to delete user.' }
  }
}

const formatBytes = (bytes = 0) => {
  if (!bytes || Number.isNaN(bytes)) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let size = bytes
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex += 1
  }
  return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`
}

const uploadRagFiles = async (files) => {
  if (!files.length) return
  ragUploading.value = true
  ragNotice.value = null
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  try {
    await apiClient.post('/admin/rag-files', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    await loadRagFiles()
    ragNotice.value = { type: 'success', text: 'Files uploaded.' }
  } catch (err) {
    ragNotice.value = { type: 'error', text: err?.response?.data?.detail || 'Failed to upload files.' }
  } finally {
    ragUploading.value = false
  }
}

const handleRagUpload = async (event) => {
  const files = Array.from(event.target.files || [])
  await uploadRagFiles(files)
  event.target.value = ''
}

const handleRagDrop = async (event) => {
  event.preventDefault()
  ragDragActive.value = false
  const files = Array.from(event.dataTransfer?.files || [])
  await uploadRagFiles(files)
}

const handleRagDragOver = (event) => {
  event.preventDefault()
  ragDragActive.value = true
}

const handleRagDragLeave = () => {
  ragDragActive.value = false
}

const deleteRagFile = async (file) => {
  if (!window.confirm(`Delete ${file.file_name}?`)) return
  ragNotice.value = null
  try {
    await apiClient.delete(`/admin/rag-files/${file.id}`)
    ragFiles.value = ragFiles.value.filter((item) => item.id !== file.id)
    ragNotice.value = { type: 'success', text: 'File deleted.' }
  } catch (err) {
    ragNotice.value = { type: 'error', text: err?.response?.data?.detail || 'Failed to delete file.' }
  }
}

const downloadRagFile = async (file) => {
  ragNotice.value = null
  try {
    const response = await apiClient.get(`/admin/rag-files/${file.id}/download`, {
      responseType: 'blob'
    })
    const url = window.URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = file.file_name || 'download'
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (err) {
    ragNotice.value = { type: 'error', text: err?.response?.data?.detail || 'Failed to download file.' }
  }
}

const saveMssqlConfig = async () => {
  mssqlSaving.value = true
  mssqlNotice.value = null
  try {
    const payload = {
      server: mssqlForm.server || null,
      database: mssqlForm.database || null,
      username: mssqlForm.username || null,
      password: mssqlForm.password || null,
      use_trusted: mssqlForm.useTrusted
    }
    const { data } = await apiClient.put('/admin/mssql-config', payload)
    mssqlForm.server = data?.server || ''
    mssqlForm.database = data?.database || ''
    mssqlForm.username = data?.username || ''
    mssqlForm.password = data?.password || ''
    mssqlForm.useTrusted = !!data?.use_trusted
    mssqlNotice.value = { type: 'success', text: 'MSSQL config saved.' }
  } catch (err) {
    mssqlNotice.value = { type: 'error', text: err?.response?.data?.detail || 'Failed to save MSSQL config.' }
  } finally {
    mssqlSaving.value = false
  }
}

const testMssqlConfig = async () => {
  mssqlTesting.value = true
  mssqlNotice.value = null
  try {
    const payload = {
      server: mssqlForm.server || null,
      database: mssqlForm.database || null,
      username: mssqlForm.username || null,
      password: mssqlForm.password || null,
      use_trusted: mssqlForm.useTrusted
    }
    const { data } = await apiClient.post('/admin/mssql-config/test', payload)
    if (data?.ok) {
      mssqlNotice.value = { type: 'success', text: data.detail || 'Connection successful.' }
    } else {
      mssqlNotice.value = { type: 'error', text: data?.detail || 'Connection failed.' }
    }
  } catch (err) {
    mssqlNotice.value = { type: 'error', text: err?.response?.data?.detail || 'Connection failed.' }
  } finally {
    mssqlTesting.value = false
  }
}
</script>

<template>
  <div class="settings-page">
    <header class="settings-header">
      <button class="btn btn-ghost" @click="router.push('/')">
        <i class="ph ph-arrow-left"></i>
        Back to Chats
      </button>
      <div>
        <h1>Settings</h1>
        <p>Manage your account preferences and workspace users.</p>
      </div>
    </header>

    <section class="card">
      <h2>My Account</h2>
      <p>Edit your account details here.</p>

      <form class="form-grid" @submit.prevent="submitAccount">
        <label>
          Email
          <input type="email" v-model="accountForm.email" required />
        </label>
        <label v-if="canEditDisplayName">
          Display Name
          <input type="text" v-model="accountForm.displayName" />
        </label>
        <label>
          New Password
          <input type="password" v-model="accountForm.password" placeholder="Leave blank to keep current password" />
        </label>
        <div class="actions">
          <button class="btn btn-primary" type="submit" :disabled="accountSaving">
            <i class="ph ph-floppy-disk"></i>
            Save Changes
          </button>
        </div>
      </form>

      <p v-if="accountStatus" :class="['status', accountStatus.type]">
        {{ accountStatus.text }}
      </p>
    </section>

    <section v-if="isAdmin" class="card">
      <div class="section-header">
        <div>
          <h2>User Management</h2>
          <p>Admins can update roles or remove users from the workspace.</p>
        </div>
        <button class="btn btn-secondary" @click="loadUsers" :disabled="usersLoading">
          <i class="ph ph-arrows-clockwise"></i>
          Refresh
        </button>
      </div>

      <p v-if="adminNotice" :class="['status', adminNotice.type]">
        {{ adminNotice.text }}
      </p>

      <div v-if="usersLoading" class="loading-state">
        Loading users...
      </div>

      <table v-else class="users-table">
        <thead>
          <tr>
            <th>Email</th>
            <th>Name</th>
            <th>Role</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td>
              <div v-if="editingUserId === user.id">
                <input type="email" v-model="editForm.email" />
              </div>
              <div v-else>
                {{ user.email }}
              </div>
            </td>
            <td>
              <div v-if="editingUserId === user.id">
                <input type="text" v-model="editForm.displayName" />
              </div>
              <div v-else>
                {{ user.display_name || user.displayName || 'Unnamed' }}
              </div>
            </td>
            <td>
              <div v-if="editingUserId === user.id">
                <select v-model="editForm.role">
                  <option value="admin">Admin</option>
                  <option value="user">User</option>
                </select>
              </div>
              <div v-else>
                <span class="role-chip" :class="user.role">{{ user.role }}</span>
              </div>
            </td>
            <td class="row-actions">
              <div v-if="editingUserId === user.id" class="edit-actions">
                <input type="password" v-model="editForm.password" placeholder="New password" />
                <button class="btn btn-primary" type="button" @click="saveUser">
                  Save
                </button>
                <button class="btn btn-ghost" type="button" @click="cancelEditUser">
                  Cancel
                </button>
              </div>
              <div v-else>
                <button class="icon-btn" type="button" @click="startEditUser(user)">
                  <i class="ph ph-pencil-simple"></i>
                </button>
                <button class="icon-btn danger" type="button" @click="deleteUser(user)" :disabled="authStore.user?.id === user.id">
                  <i class="ph ph-trash"></i>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="isAdmin" class="card">
      <div class="section-header">
        <div>
          <h2>RAG File Library</h2>
          <p>Upload knowledge files for retrieval and manage existing assets.</p>
        </div>
        <button class="btn btn-secondary" @click="loadRagFiles" :disabled="ragLoading">
          <i class="ph ph-arrows-clockwise"></i>
          Refresh
        </button>
      </div>

      <p v-if="ragNotice" :class="['status', ragNotice.type]">
        {{ ragNotice.text }}
      </p>

      <div
        class="upload-row upload-dropzone"
        :class="{ active: ragDragActive }"
        @dragover="handleRagDragOver"
        @dragleave="handleRagDragLeave"
        @drop="handleRagDrop"
      >
        <label class="upload-pill">
          <input
            type="file"
            class="upload-input"
            multiple
            accept=".pdf,.doc,.docx,.md,.csv,.txt,.xls,.xlsx"
            @change="handleRagUpload"
            :disabled="ragUploading"
          />
          <i class="ph ph-upload-simple"></i>
          {{ ragUploading ? 'Uploading...' : 'Add Files' }}
        </label>
        <span class="hint">Drag & drop files here or click Add Files.</span>
        <span class="hint">Accepted: pdf, doc, docx, md, csv, txt, xls, xlsx.</span>
      </div>

      <div v-if="ragLoading" class="loading-state">
        Loading files...
      </div>

      <table v-else class="users-table">
        <thead>
          <tr>
            <th>File</th>
            <th>Size</th>
            <th>Uploaded</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="file in ragFiles" :key="file.id">
            <td>{{ file.file_name }}</td>
            <td>{{ formatBytes(file.size_bytes) }}</td>
            <td>{{ file.created_at }}</td>
            <td>
              <button class="btn btn-ghost" type="button" @click="downloadRagFile(file)">
                <i class="ph ph-download-simple"></i>
                Download
              </button>
              <button class="btn btn-ghost danger" type="button" @click="deleteRagFile(file)">
                <i class="ph ph-trash"></i>
                Remove
              </button>
            </td>
          </tr>
          <tr v-if="!ragFiles.length">
            <td colspan="4">No files uploaded yet.</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="isAdmin" class="card">
      <div class="section-header">
        <div>
          <h2>MSSQL Connection</h2>
          <p>Configure the database connection used by query tools.</p>
        </div>
      </div>

      <p v-if="mssqlNotice" :class="['status', mssqlNotice.type]">
        {{ mssqlNotice.text }}
      </p>

      <form class="form-grid" @submit.prevent="saveMssqlConfig">
        <label>
          Server (host:port)
          <input type="text" v-model="mssqlForm.server" placeholder="localhost,1433" />
        </label>
        <label>
          Database
          <input type="text" v-model="mssqlForm.database" placeholder="master" />
        </label>
        <label>
          Username
          <input type="text" v-model="mssqlForm.username" />
        </label>
        <label>
          Password
          <input type="password" v-model="mssqlForm.password" />
        </label>
        <label class="checkbox-row">
          <input type="checkbox" v-model="mssqlForm.useTrusted" />
          Use Windows Trusted Authentication
        </label>
        <div class="actions">
          <button class="btn btn-primary" type="submit" :disabled="mssqlSaving">
            <i class="ph ph-floppy-disk"></i>
            Save Connection
          </button>
          <button class="btn btn-ghost" type="button" :disabled="mssqlTesting" @click="testMssqlConfig">
            <i class="ph ph-plug"></i>
            {{ mssqlTesting ? 'Testing...' : 'Test Connection' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>

<style scoped>
.settings-page {
  padding: 2rem;
  color: var(--text-primary);
  min-height: 100vh;
  background: radial-gradient(circle at top right, #1e293b 0%, var(--bg-primary) 100%);
}

.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.settings-header h1 {
  margin: 0;
  font-size: 1.5rem;
}

.card {
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 1rem;
  padding: 1.5rem;
  margin-bottom: 2rem;
  box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.2);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

label {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  font-size: 0.9rem;
  color: var(--text-secondary);
}

input,
select {
  background: rgba(15, 23, 42, 0.8);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 0.5rem;
  padding: 0.6rem 0.75rem;
  color: var(--text-primary);
  font-size: 0.95rem;
}

.actions {
  grid-column: 1 / -1;
  display: flex;
  justify-content: flex-end;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border: none;
  border-radius: 0.5rem;
  padding: 0.5rem 1rem;
  cursor: pointer;
  font-weight: 500;
}

.btn-primary {
  background: var(--primary);
  color: #fff;
}

.btn-secondary {
  background: rgba(148, 163, 184, 0.2);
  color: var(--text-primary);
}

.btn-ghost {
  background: transparent;
  border: 1px solid rgba(148, 163, 184, 0.2);
  color: var(--text-primary);
}

.btn-ghost.danger {
  border-color: rgba(239, 68, 68, 0.4);
  color: #ef4444;
}

.status {
  margin-top: 1rem;
  padding: 0.75rem;
  border-radius: 0.5rem;
}

.status.success {
  background: rgba(34, 197, 94, 0.1);
  color: #22c55e;
}

.status.error {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.status.info {
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}

.section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.users-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.users-table th,
.users-table td {
  padding: 0.75rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
  text-align: left;
}

.role-chip {
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  text-transform: capitalize;
  font-size: 0.8rem;
  background: rgba(148, 163, 184, 0.2);
}

.role-chip.admin {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
}

.row-actions {
  min-width: 160px;
}

.icon-btn {
  border: none;
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  padding: 0.25rem;
  font-size: 1.1rem;
}

.icon-btn.danger {
  color: #ef4444;
}

.edit-actions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.loading-state {
  padding: 1rem 0;
  color: var(--text-secondary);
}

.upload-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.upload-dropzone {
  padding: 0.75rem;
  border-radius: 0.75rem;
  border: 1px dashed rgba(148, 163, 184, 0.35);
  background: rgba(148, 163, 184, 0.06);
}

.upload-dropzone.active {
  border-color: rgba(59, 130, 246, 0.6);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}

.upload-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  border-radius: 999px;
  border: 1px dashed rgba(148, 163, 184, 0.4);
  padding: 0.45rem 0.9rem;
  cursor: pointer;
  color: var(--text-primary);
  background: rgba(148, 163, 184, 0.08);
}

.upload-input {
  display: none;
}

.hint {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.checkbox-row {
  flex-direction: row;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

@media (max-width: 768px) {
  .settings-page {
    padding: 1rem;
  }

  .settings-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .users-table {
    display: block;
    overflow-x: auto;
  }
}
</style>
