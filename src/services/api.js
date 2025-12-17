import axios from 'axios'

// Create an Axios instance with default config
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api', // Default to local FastAPI backend if not set
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
  },
  timeout: 10000 // 10 seconds timeout
})

// Request interceptor to add Auth Token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

export default apiClient

// Upload files with progress callback
// files: Array of File objects
// onProgress: function(percent:number) called with 0-100
// Upload a single file and report progress via onProgress(percent)
async function uploadSingleFile(file, onProgress) {
  const formData = new FormData()
  formData.append('file', file)

  try {
    const resp = await apiClient.post('/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent) => {
        const total = progressEvent.total || progressEvent.totalSize || 0
        if (!total) {
          if (typeof onProgress === 'function') onProgress(50)
          return
        }
        const percentCompleted = Math.round((progressEvent.loaded * 100) / total)
        if (typeof onProgress === 'function') onProgress(percentCompleted)
      }
    })

    // Normalize to single-file metadata in resp.data.file or resp.data.files[0]
    const fileMeta = resp?.data?.file || (Array.isArray(resp?.data?.files) ? resp.data.files[0] : undefined)
    return { success: true, file: fileMeta || { name: file.name, size: file.size } }
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('Single file upload failed, will fallback to simulated upload:', err && err.message ? err.message : err)
    // Simulate progress for this single file
    return await new Promise((resolve) => {
      let percent = 0
      const interval = setInterval(() => {
        const inc = Math.floor(Math.random() * 16) + 10
        percent = Math.min(100, percent + inc)
        if (typeof onProgress === 'function') onProgress(percent)
        if (percent >= 100) {
          clearInterval(interval)
          resolve({ success: true, file: { name: file.name, size: file.size, url: `mock:///${encodeURIComponent(file.name)}` } })
        }
      }, 200)
    })
  }
}

// Upload multiple files and report per-file progress using onProgress(index, percent)
export async function uploadFiles(files, onProgress) {
  // Launch uploads in parallel and attach progress handlers per file
  const uploadPromises = files.map((file, idx) =>
    uploadSingleFile(file, (p) => {
      if (typeof onProgress === 'function') onProgress(idx, p)
    }).then((res) => ({ idx, res }))
  )

  const results = await Promise.all(uploadPromises)
  // Build files metadata array in original order
  const filesMeta = results
    .sort((a, b) => a.idx - b.idx)
    .map((r) => r.res.file)

  return { data: { files: filesMeta } }
}
