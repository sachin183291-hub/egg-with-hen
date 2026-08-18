import { useAuth } from '../hooks/useAuth'
import { Settings, Shield, Database, Cpu, Blocks } from 'lucide-react'

export default function SettingsPage() {
  const { user } = useAuth()

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">System configuration and environment info</p>
        </div>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:20 }}>
        <div className="card">
          <div className="card-header">
            <h3 className="card-title"><Shield size={16} style={{ verticalAlign:'middle', marginRight:6 }} />Security Config</h3>
          </div>
          <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
            {[
              { key:'Authentication', val:'JWT (RS256)' },
              { key:'Password Hashing', val:'bcrypt' },
              { key:'Access Token TTL', val:'30 minutes' },
              { key:'Refresh Token TTL', val:'7 days' },
              { key:'CORS', val:'Configured per ENV' },
            ].map(item => (
              <div key={item.key} style={{ display:'flex', justifyContent:'space-between', padding:'8px 0', borderBottom:'1px solid var(--border-subtle)' }}>
                <span style={{ fontSize:'0.82rem', color:'var(--text-secondary)' }}>{item.key}</span>
                <span style={{ fontSize:'0.82rem', color:'var(--text-primary)', fontWeight:600 }}>{item.val}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title"><Database size={16} style={{ verticalAlign:'middle', marginRight:6 }} />Storage Config</h3>
          </div>
          <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
            {[
              { key:'Storage Backend', val:'Local / Supabase' },
              { key:'Max File Size', val:'15 MB' },
              { key:'Allowed Types', val:'JPEG, PNG, WebP' },
              { key:'Hash Algorithm', val:'SHA-256' },
              { key:'Encryption', val:'AES-256 (at-rest)' },
            ].map(item => (
              <div key={item.key} style={{ display:'flex', justifyContent:'space-between', padding:'8px 0', borderBottom:'1px solid var(--border-subtle)' }}>
                <span style={{ fontSize:'0.82rem', color:'var(--text-secondary)' }}>{item.key}</span>
                <span style={{ fontSize:'0.82rem', color:'var(--text-primary)', fontWeight:600 }}>{item.val}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title"><Cpu size={16} style={{ verticalAlign:'middle', marginRight:6 }} />AI Configuration</h3>
          </div>
          <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
            {[
              { key:'AI Model', val:'OpenCV ELA + Noise' },
              { key:'Model Version', val:'opencv-v1.0' },
              { key:'Pipeline', val:'Extensible (pluggable)' },
              { key:'ELA Threshold', val:'0.35 (suspicious)' },
              { key:'Noise Threshold', val:'0.45 (suspicious)' },
            ].map(item => (
              <div key={item.key} style={{ display:'flex', justifyContent:'space-between', padding:'8px 0', borderBottom:'1px solid var(--border-subtle)' }}>
                <span style={{ fontSize:'0.82rem', color:'var(--text-secondary)' }}>{item.key}</span>
                <span style={{ fontSize:'0.82rem', color:'var(--text-primary)', fontWeight:600 }}>{item.val}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title"><Blocks size={16} style={{ verticalAlign:'middle', marginRight:6 }} />Blockchain Config</h3>
          </div>
          <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
            {[
              { key:'Mode', val:'Local Test Ledger' },
              { key:'Hash Algorithm', val:'SHA-256' },
              { key:'Chain Type', val:'Append-only' },
              { key:'Image on Chain', val:'NEVER (hash only)' },
              { key:'Configurable via', val:'BLOCKCHAIN_MODE env' },
            ].map(item => (
              <div key={item.key} style={{ display:'flex', justifyContent:'space-between', padding:'8px 0', borderBottom:'1px solid var(--border-subtle)' }}>
                <span style={{ fontSize:'0.82rem', color:'var(--text-secondary)' }}>{item.key}</span>
                <span style={{ fontSize:'0.82rem', color: item.val === 'NEVER (hash only)' ? '#10b981' : 'var(--text-primary)', fontWeight:600 }}>{item.val}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop:20 }}>
        <h3 className="card-title" style={{ marginBottom:12 }}>Current Session</h3>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:16 }}>
          <div className="detail-item">
            <span className="detail-label">User</span>
            <span className="detail-value">{user?.full_name}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Role</span>
            <span className="detail-value">{user?.role}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Email</span>
            <span className="detail-value">{user?.email}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
