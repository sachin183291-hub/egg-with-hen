import { useState, useEffect } from 'react'
import { evidenceApi, aiApi } from '../services/api'
import type { Evidence, PaginatedResponse } from '../types'
import { formatDateTime, formatPercent, aiStatusBadgeClass, evidenceStatusBadgeClass } from '../utils/helpers'
import { Cpu, Play } from 'lucide-react'
import toast from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'

export default function AIVerificationPage() {
  const navigate = useNavigate()
  const [data, setData] = useState<PaginatedResponse<Evidence> | null>(null)
  const [loading, setLoading] = useState(true)
  const [verifying, setVerifying] = useState<string | null>(null)

  useEffect(() => {
    evidenceApi.list({ page:1, page_size:30, status:'UPLOADED' })
      .then(r => setData(r.data))
      .catch(() => toast.error('Failed to load'))
      .finally(() => setLoading(false))
  }, [])

  const runVerify = async (ev: Evidence) => {
    setVerifying(ev.id)
    try {
      const r = await aiApi.verify(ev.id)
      toast.success(`AI: ${r.data.status} (${formatPercent(r.data.confidence)})`)
      // Refresh the list
      const updated = await evidenceApi.list({ page:1, page_size:30 })
      setData(updated.data)
    } catch {
      toast.error('AI verification failed')
    } finally {
      setVerifying(null)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">AI Verification Center</h1>
          <p className="page-subtitle">AI-assisted tamper detection using ELA + noise analysis</p>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:6 }}>
          <Cpu size={16} color="var(--brand-400)" />
          <span style={{ fontSize:'0.75rem', color:'var(--brand-400)', fontWeight:600 }}>OpenCV Pipeline Active</span>
        </div>
      </div>

      <div className="card" style={{ marginBottom:20, background:'rgba(99,102,241,0.08)', borderColor:'rgba(99,102,241,0.2)' }}>
        <div style={{ display:'flex', gap:12, alignItems:'flex-start' }}>
          <span style={{ fontSize:24 }}>🤖</span>
          <div>
            <h4 style={{ color:'var(--text-primary)', marginBottom:4 }}>About AI-Assisted Verification</h4>
            <p style={{ fontSize:'0.82rem', color:'var(--text-secondary)', lineHeight:1.6 }}>
              This system uses OpenCV-based <strong>Error Level Analysis (ELA)</strong> and <strong>statistical noise analysis</strong> to detect 
              potential image manipulation. Results are labeled as <em>"AI-assisted verification"</em> — not cryptographic proof. 
              The pipeline is designed to be extensible: a trained PyTorch model can be plugged in later.
              Always combine AI analysis with human expert review for critical decisions.
            </p>
          </div>
        </div>
      </div>

      <div className="card" style={{ padding:0 }}>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Evidence #</th><th>Status</th><th>AI Status</th>
                <th>Tamper Prob.</th><th>Confidence</th><th>ELA Score</th>
                <th>Captured</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} style={{ textAlign:'center', padding:32 }}>Loading...</td></tr>
              ) : !data?.items.length ? (
                <tr><td colSpan={8} style={{ textAlign:'center', padding:32, color:'var(--text-muted)' }}>
                  No evidence pending verification
                </td></tr>
              ) : data.items.map(ev => {
                const ai = ev.ai_verification
                return (
                  <tr key={ev.id}>
                    <td style={{ fontWeight:600, color:'var(--text-primary)' }}>{ev.evidence_number}</td>
                    <td><span className={evidenceStatusBadgeClass(ev.status)}>{ev.status.replace('_',' ')}</span></td>
                    <td>{ai ? <span className={aiStatusBadgeClass(ai.status)}>{ai.status}</span> : <span style={{ color:'var(--text-muted)', fontSize:'0.8rem' }}>Not run</span>}</td>
                    <td style={{ color: ai?.tamper_probability && ai.tamper_probability > 0.3 ? '#ef4444' : '#10b981' }}>
                      {ai ? formatPercent(ai.tamper_probability) : '—'}
                    </td>
                    <td>{ai ? formatPercent(ai.confidence_score) : '—'}</td>
                    <td>{ai?.ela_score?.toFixed(4) ?? '—'}</td>
                    <td style={{ fontSize:'0.78rem' }}>{formatDateTime(ev.created_at)}</td>
                    <td>
                      <div style={{ display:'flex', gap:6 }}>
                        <button className="btn btn-primary btn-sm"
                          disabled={verifying === ev.id}
                          onClick={() => runVerify(ev)}>
                          {verifying === ev.id ? <div className="spinner" style={{ width:12, height:12 }} /> : <Play size={13} />}
                          {verifying === ev.id ? 'Running...' : 'Run AI'}
                        </button>
                        <button className="btn btn-secondary btn-sm" onClick={() => navigate(`/evidence/${ev.id}`)}>
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
