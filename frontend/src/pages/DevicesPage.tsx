import { useState, useEffect, useCallback } from 'react'
import { devicesApi } from '../services/api'
import type { Device, PaginatedResponse } from '../types'
import { formatDateTime, deviceStatusBadgeClass } from '../utils/helpers'
import { CheckCircle, XCircle, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'

export default function DevicesPage() {
  const [data, setData] = useState<PaginatedResponse<Device> | null>(null)
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)

  const fetchData = useCallback(() => {
    setLoading(true)
    devicesApi.list({ page, page_size:15, ...(status && { status }) })
      .then(r => setData(r.data))
      .catch(() => toast.error('Failed to load devices'))
      .finally(() => setLoading(false))
  }, [page, status])

  useEffect(() => { fetchData() }, [fetchData])

  const updateStatus = async (id: string, newStatus: string) => {
    await devicesApi.updateStatus(id, newStatus)
    toast.success(`Device ${newStatus.toLowerCase()}`)
    fetchData()
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Device Management</h1>
          <p className="page-subtitle">{data?.total ?? 0} registered devices</p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={fetchData}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div className="filters-bar">
        <select className="form-select" style={{ width:180 }}
          value={status} onChange={e => { setStatus(e.target.value); setPage(1) }}>
          <option value="">All Statuses</option>
          <option value="PENDING">Pending</option>
          <option value="AUTHORIZED">Authorized</option>
          <option value="REVOKED">Revoked</option>
        </select>
      </div>

      <div className="card" style={{ padding:0 }}>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Device</th><th>Identifier</th><th>OS</th>
                <th>Status</th><th>Last Seen</th><th>Registered</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} style={{ textAlign:'center', padding:32, color:'var(--text-muted)' }}>Loading...</td></tr>
              ) : data?.items.map(dev => (
                <tr key={dev.id}>
                  <td>
                    <div>
                      <div style={{ fontWeight:600, color:'var(--text-primary)', fontSize:'0.875rem' }}>
                        {dev.device_name ?? dev.device_model ?? 'Unknown Device'}
                      </div>
                      <div style={{ fontSize:'0.72rem', color:'var(--text-muted)' }}>
                        {dev.device_model}
                      </div>
                    </div>
                  </td>
                  <td><span className="hash-display" style={{ fontSize:'0.7rem' }}>{dev.device_identifier.slice(0,20)}...</span></td>
                  <td style={{ fontSize:'0.8rem' }}>{dev.os_type} {dev.os_version}</td>
                  <td><span className={deviceStatusBadgeClass(dev.status)}>{dev.status}</span></td>
                  <td style={{ fontSize:'0.75rem' }}>{dev.last_seen ? formatDateTime(dev.last_seen) : '—'}</td>
                  <td style={{ fontSize:'0.75rem' }}>{formatDateTime(dev.created_at)}</td>
                  <td>
                    <div style={{ display:'flex', gap:6 }}>
                      {dev.status === 'PENDING' && (
                        <button className="btn btn-primary btn-sm" onClick={() => updateStatus(dev.id, 'AUTHORIZED')}>
                          <CheckCircle size={13} /> Authorize
                        </button>
                      )}
                      {dev.status === 'AUTHORIZED' && (
                        <button className="btn btn-danger btn-sm" onClick={() => updateStatus(dev.id, 'REVOKED')}>
                          <XCircle size={13} /> Revoke
                        </button>
                      )}
                      {dev.status === 'REVOKED' && (
                        <button className="btn btn-secondary btn-sm" onClick={() => updateStatus(dev.id, 'AUTHORIZED')}>
                          Re-authorize
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
