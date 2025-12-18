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

onMounted(() => {
  if (isAdmin.value) {
    loadUsers()
  }
})

watch(isAdmin, (value) => {
  if (value && users.value.length === 0) {
    loadUsers()
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
                {{ user.display_name || user.displayName || '—' }}
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
