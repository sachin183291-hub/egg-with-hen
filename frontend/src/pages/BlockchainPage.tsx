import { useState, useEffect } from 'react'
import { evidenceApi, blockchainApi } from '../services/api'
import type { Evidence, PaginatedResponse } from '../types'
import { formatDateTime, blockchainStatusBadgeClass, truncateHash } from '../utils/helpers'
import { Blocks, CheckCircle, XCircle, Link } from 'lucide-react'
import toast from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'

export default function BlockchainPage() {
  const navigate = useNavigate()
  const [data, setData] = useState<PaginatedResponse<Evidence> | null>(null)
  const [loading, setLoading] = useState(true)
  const [processing, setProcessing] = useState<string | null>(null)

  useEffect(() => {
    evidenceApi.list({ page:1, page_size:30 })
      .then(r => setData(r.data))
      .catch(() => toast.error('Failed to load'))
      .finally(() => setLoading(false))
  }, [])

  const register = async (id: string) => {
    setProcessing(id)
    try {
      const r = await blockchainApi.register(id)
      toast.success(`✅ Registered! TX: ${r.data.transaction_id.slice(0,16)}...`)
      const updated = await evidenceApi.list({ page:1, page_size:30 })
      setData(updated.data)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Registration failed')
    } finally {
      setProcessing(null)
    }
  }

  const verify = async (id: string) => {
    setProcessing(id)
    try {
      const r = await blockchainApi.verify(id)
      if (r.data.is_valid) {
        toast.success('✅ Hash verified — integrity confirmed!')
      } else {
        toast.error('❌ Hash MISMATCH — evidence may be tampered!')
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Verification failed')
    } finally {
      setProcessing(null)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Blockchain Registry</h1>
          <p className="page-subtitle">Evidence hash registration and integrity verification</p>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:6 }}>
          <Blocks size={16} color="var(--brand-400)" />
          <span style={{ fontSize:'0.75rem', color:'var(--brand-400)', fontWeight:600 }}>Local Test Ledger</span>
        </div>
      </div>

      <div className="card" style={{ marginBottom:20, background:'rgba(16,185,129,0.05)', borderColor:'rgba(16,185,129,0.2)' }}>
        <div style={{ display:'flex', gap:12 }}>
          <Blocks size={24} color="#10b981" />
          <div>
            <h4 style={{ color:'var(--text-primary)', marginBottom:4 }}>About the Test Blockchain</h4>
            <p style={{ fontSize:'0.82rem', color:'var(--text-secondary)', lineHeight:1.6 }}>
              This system uses a <strong>local test ledger</strong> — SHA-256 hash-chained blocks stored locally. 
              Only the <em>evidence ID and image hash</em> are registered — never the actual image. 
              Each block references the previous block hash ensuring append-only immutability. 
              The provider is configurable (ENV: <code>BLOCKCHAIN_MODE</code>) and can be swapped for Ethereum/Polygon.
            </p>
          </div>
        </div>
      </div>

      <div className="card" style={{ padding:0 }}>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Evidence #</th><th>SHA-256 Hash</th><th>Blockchain Status</th>
                <th>Transaction ID</th><th>Block #</th><th>Registered</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} style={{ textAlign:'center', padding:32 }}>Loading...</td></tr>
              ) : data?.items.map(ev => {
                const bc = ev.blockchain_record
                const isRegistered = bc && bc.status !== 'NOT_REGISTERED'
                return (
                  <tr key={ev.id}>
                    <td style={{ fontWeight:600, color:'var(--text-primary)' }}>{ev.evidence_number}</td>
                    <td><span className="hash-display">{truncateHash(ev.image_sha256_hash, 12)}</span></td>
                    <td>
                      <span className={blockchainStatusBadgeClass(bc?.status)}>
                        {bc?.status?.replace('_', ' ') ?? 'NOT REGISTERED'}
                      </span>
                    </td>
                    <td style={{ fontSize:'0.75rem' }}>
                      {bc?.transaction_id ? (
                        <span className="hash-display" style={{ fontSize:'0.65rem' }}>
                          {bc.transaction_id.slice(0,18)}...
                        </span>
                      ) : '—'}
                    </td>
                    <td style={{ fontSize:'0.8rem' }}>{bc?.block_number != null ? `#${bc.block_number}` : '—'}</td>
                    <td style={{ fontSize:'0.75rem' }}>
                      {bc?.registered_at ? formatDateTime(bc.registered_at) : '—'}
                    </td>
                    <td>
                      <div style={{ display:'flex', gap:6 }}>
                        {!isRegistered ? (
                          <button className="btn btn-primary btn-sm"
                            disabled={processing === ev.id}
                            onClick={() => register(ev.id)}>
                            {processing === ev.id ? <div className="spinner" style={{ width:12, height:12 }} /> : <Link size={13} />}
                            Register
                          </button>
                        ) : (
                          <button className="btn btn-secondary btn-sm"
                            disabled={processing === ev.id}
                            onClick={() => verify(ev.id)}>
                            {processing === ev.id ? <div className="spinner" style={{ width:12, height:12 }} /> : <CheckCircle size={13} />}
                            Verify
                          </button>
                        )}
                        <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/evidence/${ev.id}`)}>
                          View
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
