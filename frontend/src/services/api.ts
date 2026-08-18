/**
 * Axios API client with JWT interceptor and auth refresh.
 */
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || ''

export const api = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
})

// ─── Request interceptor: attach JWT ─────────────────────────────────────────
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type']
  }
  return config
})

// ─── Response interceptor: handle 401 / refresh ──────────────────────────────
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          const res = await axios.post(`${API_URL}/api/auth/refresh`, { refresh_token: refreshToken })
          const { access_token, refresh_token } = res.data
          localStorage.setItem('access_token', access_token)
          localStorage.setItem('refresh_token', refresh_token)
          original.headers.Authorization = `Bearer ${access_token}`
          return api(original)
        } catch {
          localStorage.clear()
          window.location.href = '/login'
        }
      } else {
        localStorage.clear()
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// ─── Auth endpoints ───────────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    api.post('/api/auth/login', { email, password }),
  register: (data: Record<string, unknown>) =>
    api.post('/api/auth/register', data),
  me: () => api.get('/api/auth/me'),
  logout: () => api.post('/api/auth/logout'),
}

// ─── Dashboard ────────────────────────────────────────────────────────────────
export const dashboardApi = {
  stats: () => api.get('/api/dashboard/statistics'),
  trend: (days = 30) => api.get(`/api/dashboard/evidence-trend?days=${days}`),
  statusDist: () => api.get('/api/dashboard/status-distribution'),
  deptStats: () => api.get('/api/dashboard/department-stats'),
}

// ─── Evidence ─────────────────────────────────────────────────────────────────
export const evidenceApi = {
  list: (params?: Record<string, unknown>) => api.get('/api/evidence', { params }),
  get: (id: string) => api.get(`/api/evidence/${id}`),
  update: (id: string, data: Record<string, unknown>) => api.put(`/api/evidence/${id}`, data),
  delete: (id: string) => api.delete(`/api/evidence/${id}`),
  upload: (formData: FormData) =>
    api.post('/api/evidence', formData),
}

// ─── Users ────────────────────────────────────────────────────────────────────
export const usersApi = {
  list: (params?: Record<string, unknown>) => api.get('/api/users', { params }),
  get: (id: string) => api.get(`/api/users/${id}`),
  create: (data: Record<string, unknown>) => api.post('/api/users', data),
  update: (id: string, data: Record<string, unknown>) => api.put(`/api/users/${id}`, data),
  delete: (id: string) => api.delete(`/api/users/${id}`),
}

// ─── Devices ──────────────────────────────────────────────────────────────────
export const devicesApi = {
  list: (params?: Record<string, unknown>) => api.get('/api/devices', { params }),
  updateStatus: (id: string, status: string) => api.put(`/api/devices/${id}/status`, { status }),
}

// ─── GIS ──────────────────────────────────────────────────────────────────────
export const gisApi = {
  evidence: (params?: Record<string, unknown>) => api.get('/api/gis/evidence', { params }),
}

// ─── AI ───────────────────────────────────────────────────────────────────────
export const aiApi = {
  verify: (evidenceId: string) => api.post(`/api/ai/verify/${evidenceId}`),
  result: (evidenceId: string) => api.get(`/api/ai/result/${evidenceId}`),
  countTrays: (formData: FormData) => api.post('/api/ai/count-trays', formData),
  /** Dual OpenAI/Gemini Vision: POST /api/ai/analyze-dual-egg-images */
  analyzeDualEggImage: (formData: FormData) => api.post('/api/ai/analyze-dual-egg-images', formData),
  /** OpenAI Vision: POST /api/ai/analyze-egg-image */
  analyzeEggImage: (formData: FormData) => api.post('/api/ai/analyze-egg-image', formData),
  /** OpenAI Chat: POST /api/ai/chat-analyze */
  chatAnalyze: (formData: FormData) => api.post('/api/ai/chat-analyze', formData),
}

// ─── Blockchain ───────────────────────────────────────────────────────────────
export const blockchainApi = {
  register: (evidenceId: string) => api.post(`/api/blockchain/register/${evidenceId}`),
  verify: (evidenceId: string) => api.get(`/api/blockchain/verify/${evidenceId}`),
}

// ─── Audit ────────────────────────────────────────────────────────────────────
export const auditApi = {
  list: (params?: Record<string, unknown>) => api.get('/api/audit-logs', { params }),
}

// ─── Reports ──────────────────────────────────────────────────────────────────
export const reportsApi = {
  evidence: (params?: Record<string, unknown>) => api.get('/api/reports/evidence', { params }),
  suspicious: () => api.get('/api/reports/suspicious'),
  activity: (days = 30) => api.get(`/api/reports/activity?days=${days}`),
}
