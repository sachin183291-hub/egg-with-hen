import { useState, useEffect } from 'react'
import { reportsApi } from '../services/api'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { BarChart2, Download, AlertTriangle, Activity } from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDateTime } from '../utils/helpers'

export default function ReportsPage() {
  const [evidenceReport, setEvidenceReport] = useState<any>(null)
  const [suspiciousReport, setSuspiciousReport] = useState<any>(null)
  const [activityReport, setActivityReport] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      reportsApi.evidence(),
      reportsApi.suspicious(),
      reportsApi.activity(30),
    ]).then(([e, s, a]) => {
      setEvidenceReport(e.data)
      setSuspiciousReport(s.data)
      setActivityReport(a.data)
    }).catch(() => toast.error('Failed to load reports'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="loading-screen"><div className="spinner" style={{ width:32, height:32 }} /></div>

  const summaryData = evidenceReport?.summary ? Object.entries(evidenceReport.summary).map(([k, v]) => ({
    name: k.charAt(0).toUpperCase() + k.slice(1), value: v as number
  })) : []

  const STATUS_COLORS = ['#10b981', '#ef4444', '#f59e0b', '#6366f1', '#3b82f6', '#6b7280']

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Reports</h1>
          <p className="page-subtitle">Evidence and activity reports</p>
        </div>
        <button className="btn btn-secondary btn-sm">
          <Download size={14} /> Export
        </button>
      </div>

      {/* Summary Cards */}
      <div className="stat-grid" style={{ gridTemplateColumns:'repeat(3, 1fr)', marginBottom:24 }}>
        <div className="stat-card" style={{ '--stat-color':'#6366f1' } as React.CSSProperties}>
          <div className="stat-icon"><BarChart2 size={20} color="#6366f1" /></div>
          <div>
            <div className="stat-value">{evidenceReport?.total ?? 0}</div>
            <div className="stat-label">Total Evidence</div>
          </div>
        </div>
        <div className="stat-card" style={{ '--stat-color':'#ef4444' } as React.CSSProperties}>
          <div className="stat-icon"><AlertTriangle size={20} color="#ef4444" /></div>
          <div>
            <div className="stat-value">{suspiciousReport?.total_suspicious ?? 0}</div>
            <div className="stat-label">Suspicious Evidence</div>
          </div>
        </div>
        <div className="stat-card" style={{ '--stat-color':'#10b981' } as React.CSSProperties}>
          <div className="stat-icon"><Activity size={20} color="#10b981" /></div>
          <div>
            <div className="stat-value">{activityReport?.total_actions ?? 0}</div>
            <div className="stat-label">Actions (30 Days)</div>
          </div>
        </div>
      </div>

      <div className="charts-grid">
        {/* Evidence by Status */}
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Evidence by Status</h3>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={summaryData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="name" tick={{ fill:'#64748b', fontSize:11 }} />
              <YAxis tick={{ fill:'#64748b', fontSize:11 }} />
              <Tooltip contentStyle={{ background:'#1a2235', border:'1px solid rgba(255,255,255,0.1)', borderRadius:8, color:'#f1f5f9', fontSize:12 }} />
              <Bar dataKey="value" radius={[4,4,0,0]}>
                {summaryData.map((_, i) => <Cell key={i} fill={STATUS_COLORS[i % STATUS_COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Suspicious Evidence List */}
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">⚠️ Suspicious Evidence</h3>
            <span className="badge badge-suspicious">{suspiciousReport?.total_suspicious ?? 0}</span>
          </div>
          <div style={{ maxHeight:220, overflowY:'auto' }}>
            {suspiciousReport?.records?.length ? suspiciousReport.records.map((r: any) => (
              <div key={r.evidence_id} style={{
                padding:'10px 0', borderBottom:'1px solid var(--border-subtle)',
                display:'flex', alignItems:'center', justifyContent:'space-between'
              }}>
                <div>
                  <div style={{ fontWeight:600, fontSize:'0.85rem', color:'var(--text-primary)' }}>{r.evidence_number}</div>
                  <div style={{ fontSize:'0.72rem', color:'var(--text-muted)' }}>{formatDateTime(r.created_at)}</div>
                </div>
                <div style={{ textAlign:'right' }}>
                  <div style={{ color:'#ef4444', fontWeight:700, fontSize:'0.85rem' }}>
                    {((r.tamper_probability ?? 0) * 100).toFixed(0)}% tamper
                  </div>
                  <div style={{ color:'var(--text-muted)', fontSize:'0.7rem' }}>
                    Conf: {((r.confidence ?? 0) * 100).toFixed(0)}%
                  </div>
                </div>
              </div>
            )) : (
              <p style={{ color:'var(--text-muted)', fontSize:'0.85rem', textAlign:'center', padding:20 }}>
                No suspicious evidence found
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
