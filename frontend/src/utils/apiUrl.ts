/**
 * Dynamic API and Backend URL Resolver for GioTag Dashboard.
 * 
 * Works seamlessly across:
 * 1. Localhost (empty string -> Vite dev proxy forwards /api to 127.0.0.1:8000)
 * 2. Mobile LAN / Hotspot testing (e.g. 192.168.x.x / 10.x.x.x)
 * 3. Render cloud hosting (automatically detects *.onrender.com backend,
 *    or uses VITE_API_URL, or user custom backend URL stored in localStorage).
 */

export function getApiBaseUrl(): string {
  // 1. User manual override (stored in localStorage via UI settings)
  if (typeof window !== 'undefined') {
    const custom = localStorage.getItem('giotag_backend_url') || localStorage.getItem('API_URL')
    if (custom && custom.trim()) {
      return custom.trim().replace(/\/$/, '')
    }
  }

  // 2. Vite Build-time Environment Variable (if populated during deploy)
  const envUrl = (import.meta.env.VITE_API_URL || '').trim().replace(/\/$/, '')
  if (envUrl) {
    return envUrl
  }

  // 3. Smart Cloud Auto-Resolution for Render (e.g. my-app-frontend.onrender.com -> my-app-backend.onrender.com)
  if (typeof window !== 'undefined') {
    const host = window.location.hostname
    if (host.includes('.onrender.com')) {
      if (host.includes('-frontend.')) {
        return `https://${host.replace('-frontend.', '-backend.')}`
      }
      if (host.includes('frontend.')) {
        return `https://${host.replace('frontend.', 'backend.')}`
      }
      // Standard default blueprint service name
      return 'https://giotag-backend.onrender.com'
    }
    if (host.includes('.vercel.app') || host.includes('.netlify.app')) {
      return 'https://giotag-backend.onrender.com'
    }
  }

  // 4. Localhost / same-origin fallback
  return ''
}

export function getTrackerBaseUrl(): string {
  const base = getApiBaseUrl()
  return `${base}/api/tracker`
}

export function setCustomBackendUrl(url: string | null): void {
  if (typeof window !== 'undefined') {
    if (url && url.trim()) {
      const clean = url.trim().replace(/\/$/, '')
      localStorage.setItem('giotag_backend_url', clean)
    } else {
      localStorage.removeItem('giotag_backend_url')
    }
  }
}
