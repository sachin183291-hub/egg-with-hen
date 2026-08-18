import { useState, useEffect } from 'react'
import { auditApi } from '../services/api'
import type { AuditLog, PaginatedResponse } from '../types'
import { formatDateTime } from '../utils/helpers'
import { Shield, Search } from 'lucide-react'
import toast from 'react-hot-toast'

const RESULT_COLORS: Record<string, string> = {
  SUCCESS: '#10b981',
  FAILED:  '#ef4444',
  DENIED:  '#f59e0b',
}

export default function AuditLogsPage() {
  const [data, setData] = useState<PaginatedResponse<AuditLog> | null>(null)
  const [loading, setLoading] = useState(true)
  const [action, setAction] = useState('')
  const [result, setResult] = useState('')
  const [page, setPage] = useState(1)

  useEffect(() => {
    setLoading(true)
    auditApi.list({
      page, page_size:50,
      ...(action && { action }),
      ...(result && { result }),
    }).then(r => setData(r.data))
      .catch(() => toast.error('Failed to load audit logs'))
      .finally(() => setLoading(false))
  }, [page, action, result])

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Audit Trail</h1>
          <p className="page-subtitle">Immutable activity log — {data?.total ?? 0} records</p>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:6 }}>
          <Shield size={16} color="var(--brand-400)" />
          <span style={{ fontSize:'0.75rem', color:'var(--text-muted)' }}>Read-only</span>
        </div>
      </div>

      <div className="filters-bar">
        <select className="form-select" style={{ width:220 }}
          value={action} onChange={e => { setAction(e.target.value); setPage(1) }}>
          <option value="">All Actions</option>
          <option value="LOGIN">Login</option>
          <option value="LOGOUT">Logout</option>
          <option value="PHOTO_CAPTURED">Photo Captured</option>
          <option value="PHOTO_UPLOADED">Photo Uploaded</option>
          <option value="AI_VERIFIED">AI Verified</option>
          <option value="BLOCKCHAIN_REGISTERED">Blockchain Registered</option>
          <option value="EVIDENCE_ACCESSED">Evidence Accessed</option>
          <option value="DEVICE_REGISTERED">Device Registered</option>
          <option value="UNAUTHORIZED_ACCESS">Unauthorized Access</option>
        </select>
        <select className="form-select" style={{ width:140 }}
          value={result} onChange={e => { setResult(e.target.value); setPage(1) }}>
          <option value="">All Results</option>
          <option value="SUCCESS">Success</option>
          <option value="FAILED">Failed</option>
          <option value="DENIED">Denied</option>
        </select>
      </div>

      <div className="card" style={{ padding:0 }}>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th><th>User</th><th>Action</th>
                <th>Resource</th><th>Description</th><th>IP</th><th>Result</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} style={{ textAlign:'center', padding:32 }}>Loading...</td></tr>
              ) : data?.items.map(log => (
                <tr key={log.id}>
                  <td style={{ fontSize:'0.75rem', whiteSpace:'nowrap' }}>{formatDateTime(log.created_at)}</td>
                  <td style={{ fontSize:'0.8rem' }}>
                    {log.user?.full_name ?? (log.user_id ? log.user_id.slice(0,8)+'...' : 'System')}
                  </td>
                  <td>
                    <span style={{
                      fontFamily:'monospace', fontSize:'0.72rem',
                      background:'var(--bg-elevated)', borderRadius:4,
                      padding:'2px 6px', color:'var(--brand-300)'
                    }}>{log.action}</span>
                  </td>
                  <td style={{ fontSize:'0.75rem' }}>
                    {log.resource_type ? `${log.resource_type}` : '—'}
                  </td>
                  <td style={{ fontSize:'0.78rem', maxWidth:280, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                    {log.description ?? '—'}
                  </td>
                  <td style={{ fontSize:'0.72rem', fontFamily:'monospace' }}>{log.ip_address ?? '—'}</td>
                  <td>
                    <span style={{
                      fontSize:'0.7rem', fontWeight:700,
                      color: RESULT_COLORS[log.result ?? ''] ?? 'var(--text-muted)'
                    }}>{log.result ?? '—'}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data && data.pages > 1 && (
          <div style={{ display:'flex', justifyContent:'center', gap:8, padding:16 }}>
            <button className="page-btn" onClick={() => setPage(p => Math.max(1, p-1))} disabled={page===1}>‹</button>
            <span style={{ fontSize:'0.8rem', color:'var(--text-muted)', alignSelf:'center' }}>
              Page {page} / {data.pages}
            </span>
            <button className="page-btn" onClick={() => setPage(p => Math.min(data.pages, p+1))} disabled={page===data.pages}>›</button>
          </div>
        )}
      </div>
    </div>
  )
}
