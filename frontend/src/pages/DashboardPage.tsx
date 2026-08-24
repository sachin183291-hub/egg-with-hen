import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { dashboardApi } from '../services/api'
import type { DashboardStats } from '../types'
import { formatDate } from '../utils/helpers'
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts'
import {
  Image, CheckCircle, AlertTriangle, Clock, Users,
  Smartphone, Blocks, TrendingUp, Shield, HeartPulse, Camera, Activity
} from 'lucide-react'

interface TrendPoint { date: string; count: number }
interface StatusDist  { status: string; count: number }

const STATUS_COLORS: Record<string, string> = {
  VERIFIED: '#10b981',
  SUSPICIOUS: '#ef4444',
  REVIEW_REQUIRED: '#f59e0b',
  PENDING_SYNC: '#6366f1',
  UPLOADED: '#3b82f6',
  REJECTED: '#6b7280',
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [trend, setTrend] = useState<TrendPoint[]>([])
  const [statusDist, setStatusDist] = useState<StatusDist[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      dashboardApi.stats(),
      dashboardApi.trend(30),
      dashboardApi.statusDist(),
    ]).then(([s, t, d]) => {
      setStats(s.data)
      setTrend(t.data)
      setStatusDist(d.data)
    }).catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="loading-screen">
      <div className="spinner" style={{ width:32, height:32 }} />
      <span>Loading dashboard...</span>
    </div>
  )

  const statCards = stats ? [
    { label:'Total Evidence', value: stats.total_evidence, icon: Image, color:'#6366f1', sub:`${stats.evidence_today} today` },
    { label:'Verified',       value: stats.verified_evidence, icon: CheckCircle, color:'#10b981', sub:`${stats.evidence_this_week} this week` },
    { label:'Suspicious',     value: stats.suspicious_evidence, icon: AlertTriangle, color:'#ef4444', sub:'Requires review' },
    { label:'Pending Sync',   value: stats.pending_sync, icon: Clock, color:'#f59e0b', sub:'Awaiting upload' },
    { label:'Active Users',   value: stats.active_users, icon: Users, color:'#8b5cf6', sub:'Registered users' },
    { label:'Devices',        value: stats.registered_devices, icon: Smartphone, color:'#06b6d4', sub:`${stats.authorized_devices} authorized` },
    { label:'Blockchain Records', value: stats.blockchain_records, icon: Blocks, color:'#ec4899', sub:'Hash registered' },
    { label:'This Week',      value: stats.evidence_this_week, icon: TrendingUp, color:'#14b8a6', sub:'Evidence captured' },
  ] : []

  const healthStats = [
    { label: 'Total Flocks Monitored', value: 1250, icon: Activity, color: '#3b82f6', sub: '+12 this week' },
    { label: 'Healthy Hens', value: 1142, icon: CheckCircle, color: '#10b981', sub: '91.3% of total' },
    { label: 'Attention Required', value: 108, icon: AlertTriangle, color: '#f59e0b', sub: 'Minor issues detected' },
    { label: 'Critical Health', value: 0, icon: HeartPulse, color: '#ef4444', sub: 'Urgent care needed' },
  ]

  return (
    <div className="page-with-bg">
      <div className="page-header">
        <div>
          <h1 className="page-title">Mission Control</h1>
          <p className="page-subtitle">Evidence monitoring dashboard — {formatDate(new Date().toISOString())}</p>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <Shield size={16} color="var(--brand-400)" />
          <span style={{ fontSize:'0.8rem', color:'var(--brand-400)', fontWeight:600 }}>System Secure</span>
        </div>
      </div>

      {/* Stat Cards */}
      <div className="stat-grid">
        {statCards.map((card) => (
          <div key={card.label} className="stat-card" style={{ '--stat-color': card.color } as React.CSSProperties}>
            <div className="stat-icon">
              <card.icon size={20} color={card.color} />
            </div>
            <div>
              <div className="stat-value">{card.value.toLocaleString()}</div>
              <div className="stat-label">{card.label}</div>
              <div className="stat-change" style={{ color: card.color }}>{card.sub}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: '32px', marginBottom: '16px' }}>
        <h2 className="page-title" style={{ fontSize: '1.25rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <HeartPulse size={20} color="#ef4444" />
          Poultry Health Metrics
        </h2>
      </div>

      {/* Health Stat Cards */}
      <div className="stat-grid" style={{ marginBottom: '32px' }}>
        {healthStats.map((card) => (
          <div key={card.label} className="stat-card" style={{ '--stat-color': card.color } as React.CSSProperties}>
            <div className="stat-icon">
              <card.icon size={20} color={card.color} />
            </div>
            <div>
              <div className="stat-value">{card.value.toLocaleString()}</div>
              <div className="stat-label">{card.label}</div>
              <div className="stat-change" style={{ color: card.color }}>{card.sub}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="charts-grid">
        {/* Evidence Trend */}
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Evidence Captured (30 Days)</h3>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={trend}>
              <defs>
                <linearGradient id="countGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="date" tick={{ fill:'#64748b', fontSize:11 }} tickFormatter={(v) => v.slice(5)} />
              <YAxis tick={{ fill:'#64748b', fontSize:11 }} />
              <Tooltip contentStyle={{ background:'#1a2235', border:'1px solid rgba(255,255,255,0.1)', borderRadius:8, color:'#f1f5f9', fontSize:12 }} />
              <Area type="monotone" dataKey="count" stroke="#6366f1" fill="url(#countGrad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Status Distribution */}
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Evidence Status Distribution</h3>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={statusDist} dataKey="count" nameKey="status" cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={3}>
                {statusDist.map((entry) => (
                  <Cell key={entry.status} fill={STATUS_COLORS[entry.status] ?? '#6366f1'} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background:'#1a2235', border:'1px solid rgba(255,255,255,0.1)', borderRadius:8, color:'#f1f5f9', fontSize:12 }} />
              <Legend formatter={(v) => <span style={{ color:'#94a3b8', fontSize:11 }}>{v}</span>} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Quick Actions Section */}
      <div className="card" style={{ marginTop: '24px' }}>
        <div className="card-header">
          <h3 className="card-title">Quick Actions</h3>
        </div>
        <div style={{ padding: '24px', display: 'flex', gap: '16px' }}>
          <Link to="/hen-health" style={{ textDecoration: 'none', flex: 1 }}>
            <div style={{ 
              background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(239, 68, 68, 0.05) 100%)',
              border: '1px solid rgba(239, 68, 68, 0.2)',
              borderRadius: '12px',
              padding: '24px',
              display: 'flex',
              alignItems: 'center',
              gap: '20px',
              transition: 'all 0.2s ease',
              cursor: 'pointer'
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)'
              e.currentTarget.style.boxShadow = '0 8px 24px rgba(239, 68, 68, 0.15)'
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.transform = 'translateY(0)'
              e.currentTarget.style.boxShadow = 'none'
            }}
            >
              <div style={{ 
                width: '64px', height: '64px', borderRadius: '16px', background: '#ef4444', 
                display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 12px rgba(239, 68, 68, 0.4)'
              }}>
                <HeartPulse color="white" size={32} />
              </div>
              <div>
                <h3 style={{ fontSize: '1.25rem', fontWeight: '600', color: 'var(--text-primary)', marginBottom: '4px' }}>Hen Health AI Diagnostics</h3>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}>Upload images of poultry to detect health issues instantly using AI.</p>
              </div>
              <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '8px', color: '#ef4444', fontWeight: '600', fontSize: '0.9rem' }}>
                <Camera size={18} /> Open Scanner
              </div>
            </div>
          </Link>
        </div>
      </div>

      {/* Quick status overview */}
      {stats && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">System Status Overview</h3>
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(180px,1fr))', gap:16 }}>
            {[
              { label:'Evidence Integrity', value:'Monitored', color:'#10b981' },
              { label:'AI Service', value:'Online', color:'#10b981' },
              { label:'Blockchain Ledger', value:'Active', color:'#10b981' },
              { label:'GPS Services', value:'Active', color:'#10b981' },
              { label:'Storage', value:'Available', color:'#10b981' },
              { label:'Authentication', value:'Secured', color:'#10b981' },
            ].map(item => (
              <div key={item.label} style={{ display:'flex', alignItems:'center', gap:8 }}>
                <div style={{ width:8, height:8, borderRadius:'50%', background:item.color, boxShadow:`0 0 6px ${item.color}80` }} />
                <div>
                  <div style={{ fontSize:'0.7rem', color:'var(--text-muted)' }}>{item.label}</div>
                  <div style={{ fontSize:'0.8rem', color:item.color, fontWeight:600 }}>{item.value}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
