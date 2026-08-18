import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { evidenceApi } from '../services/api'
import type { Evidence, EvidenceStatus, PaginatedResponse } from '../types'
import {
  formatDateTime, formatBytes, evidenceStatusBadgeClass,
  aiStatusBadgeClass, truncateHash
} from '../utils/helpers'
import { Search, Eye, Trash2, Filter, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'All Statuses' },
  { value: 'VERIFIED', label: 'Verified' },
  { value: 'SUSPICIOUS', label: 'Suspicious' },
  { value: 'REVIEW_REQUIRED', label: 'Review Required' },
  { value: 'PENDING_SYNC', label: 'Pending Sync' },
  { value: 'UPLOADED', label: 'Uploaded' },
  { value: 'REJECTED', label: 'Rejected' },
]

export default function EvidencePage() {
  const navigate = useNavigate()
  const [data, setData] = useState<PaginatedResponse<Evidence> | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)

  const fetchData = useCallback(() => {
    setLoading(true)
    evidenceApi.list({
      page, page_size: 15,
      ...(search && { search }),
      ...(status && { status }),
    }).then(r => setData(r.data))
      .catch(() => toast.error('Failed to load evidence'))
      .finally(() => setLoading(false))
  }, [page, search, status])

  useEffect(() => { fetchData() }, [fetchData])

  const handleDelete = async (id: string, num: string) => {
    if (!confirm(`Delete evidence ${num}? This cannot be undone.`)) return
    try {
      await evidenceApi.delete(id)
      toast.success(`Evidence ${num} deleted`)
      fetchData()
    } catch {
      toast.error('Delete failed')
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Evidence Records</h1>
          <p className="page-subtitle">{data?.total ?? 0} total records</p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={fetchData}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div className="filters-bar">
        <div className="search-input-wrapper">
          <Search size={14} />
          <input
            className="form-input search-input"
            placeholder="Search by evidence number..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
          />
        </div>
        <select className="form-select" style={{ width:180 }}
          value={status} onChange={e => { setStatus(e.target.value); setPage(1) }}>
          {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>

      <div className="card" style={{ padding:0 }}>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Evidence #</th>
                <th>Status</th>
                <th>Officer</th>
                <th>Captured</th>
                <th>Size</th>
                <th>Hash</th>
                <th>AI</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} style={{ textAlign:'center', padding:40, color:'var(--text-muted)' }}>
                  <div style={{ display:'flex', alignItems:'center', justifyContent:'center', gap:8 }}>
                    <div className="spinner" /> Loading...
                  </div>
                </td></tr>
              ) : !data?.items.length ? (
                <tr><td colSpan={8} style={{ textAlign:'center', padding:40, color:'var(--text-muted)' }}>
                  No evidence found
                </td></tr>
              ) : data.items.map(ev => (
                <tr key={ev.id}>
                  <td>
                    <span style={{ fontWeight:600, color:'var(--text-primary)', fontSize:'0.85rem' }}>
                      {ev.evidence_number}
                    </span>
                  </td>
                  <td><span className={evidenceStatusBadgeClass(ev.status)}>{ev.status.replace('_', ' ')}</span></td>
                  <td style={{ color:'var(--text-primary)', fontSize:'0.85rem' }}>{ev.user?.full_name ?? '—'}</td>
                  <td style={{ fontSize:'0.8rem' }}>{formatDateTime(ev.created_at)}</td>
                  <td style={{ fontSize:'0.8rem' }}>{formatBytes(ev.image_size_bytes)}</td>
                  <td>
                    <span className="hash-display">{truncateHash(ev.image_sha256_hash)}</span>
                  </td>
                  <td>
                    {ev.ai_verification ? (
                      <span className={aiStatusBadgeClass(ev.ai_verification.status)}>
                        {ev.ai_verification.status}
                      </span>
                    ) : '—'}
                  </td>
                  <td>
                    <div style={{ display:'flex', gap:6 }}>
                      <button className="btn btn-secondary btn-sm"
                        onClick={() => navigate(`/evidence/${ev.id}`)} title="View">
                        <Eye size={14} />
                      </button>
                      <button className="btn btn-danger btn-sm"
                        onClick={() => handleDelete(ev.id, ev.evidence_number)} title="Delete">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {data && data.pages > 1 && (
          <div className="pagination" style={{ padding:'12px 16px', justifyContent:'space-between' }}>
            <span className="pagination-info">
              Page {page} of {data.pages} ({data.total} total)
            </span>
            <div style={{ display:'flex', gap:6 }}>
              <button className="page-btn" onClick={() => setPage(p => Math.max(1, p-1))} disabled={page === 1}>‹</button>
              {Array.from({ length: Math.min(5, data.pages) }, (_, i) => {
                const p = page <= 3 ? i+1 : page - 2 + i
                if (p < 1 || p > data.pages) return null
                return <button key={p} className={`page-btn${p === page ? ' active' : ''}`} onClick={() => setPage(p)}>{p}</button>
              })}
              <button className="page-btn" onClick={() => setPage(p => Math.min(data.pages, p+1))} disabled={page === data.pages}>›</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
