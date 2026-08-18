import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { evidenceApi, aiApi, blockchainApi } from '../services/api'
import type { Evidence } from '../types'
import {
  formatDateTime, formatBytes, evidenceStatusBadgeClass,
  aiStatusBadgeClass, blockchainStatusBadgeClass, formatPercent
} from '../utils/helpers'
import { ArrowLeft, Shield, Cpu, Blocks, MapPin, Clock, Hash, User, Smartphone } from 'lucide-react'
import toast from 'react-hot-toast'

export default function EvidenceDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [evidence, setEvidence] = useState<Evidence | null>(null)
  const [loading, setLoading] = useState(true)
  const [aiLoading, setAiLoading] = useState(false)
  const [bcLoading, setBcLoading] = useState(false)

  useEffect(() => {
    if (!id) return
    evidenceApi.get(id)
      .then(r => setEvidence(r.data))
      .catch(() => toast.error('Evidence not found'))
      .finally(() => setLoading(false))
  }, [id])

  const runAIVerify = async () => {
    if (!id) return
    setAiLoading(true)
    try {
      await aiApi.verify(id)
      const r = await evidenceApi.get(id)
      setEvidence(r.data)
      toast.success('AI verification completed')
    } catch {
      toast.error('AI verification failed')
    } finally {
      setAiLoading(false)
    }
  }

  const registerBlockchain = async () => {
    if (!id) return
    setBcLoading(true)
    try {
      await blockchainApi.register(id)
      const r = await evidenceApi.get(id)
      setEvidence(r.data)
      toast.success('Hash registered on blockchain')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Blockchain registration failed')
    } finally {
      setBcLoading(false)
    }
  }

  const verifyBlockchain = async () => {
    if (!id) return
    setBcLoading(true)
    try {
      const r = await blockchainApi.verify(id)
      if (r.data.is_valid) {
        toast.success('✅ Hash verified — evidence integrity confirmed')
      } else {
        toast.error('❌ Hash MISMATCH — possible tampering detected!')
      }
      const ev = await evidenceApi.get(id)
      setEvidence(ev.data)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Blockchain verification failed')
    } finally {
      setBcLoading(false)
    }
  }

  if (loading) return (
    <div className="loading-screen"><div className="spinner" style={{ width:32, height:32 }} /></div>
  )

  if (!evidence) return (
    <div className="loading-screen"><p>Evidence not found</p></div>
  )

  const ai = evidence.ai_verification
  const bc = evidence.blockchain_record
  const meta = evidence.metadata_
  const imgUrl = evidence.storage_url
    ? `${import.meta.env.VITE_API_URL || ''}${evidence.storage_url}`
    : null

  return (
    <div>
      <div className="page-header">
        <div style={{ display:'flex', alignItems:'center', gap:12 }}>
          <button className="btn btn-ghost btn-sm" onClick={() => navigate(-1)}>
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 className="page-title">{evidence.evidence_number}</h1>
            <p className="page-subtitle">Evidence Detail</p>
          </div>
        </div>
        <span className={evidenceStatusBadgeClass(evidence.status)} style={{ fontSize:'0.85rem', padding:'5px 14px' }}>
          {evidence.status.replace('_', ' ')}
        </span>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'340px 1fr', gap:20 }}>
        {/* Image Preview */}
        <div>
          <div className="card" style={{ padding:0, overflow:'hidden' }}>
            {imgUrl ? (
              <img src={imgUrl} alt={evidence.image_filename}
                style={{ width:'100%', height:300, objectFit:'cover', display:'block' }} />
            ) : (
              <div style={{
                width:'100%', height:300, display:'flex', alignItems:'center',
                justifyContent:'center', background:'var(--bg-elevated)', color:'var(--text-muted)',
                flexDirection:'column', gap:8
              }}>
                <span style={{ fontSize:48 }}>📷</span>
                <span style={{ fontSize:'0.8rem' }}>Image not available in demo</span>
              </div>
            )}
            <div style={{ padding:16 }}>
              <div className="detail-item" style={{ marginBottom:8 }}>
                <span className="detail-label">Filename</span>
                <span className="detail-value" style={{ fontSize:'0.8rem' }}>{evidence.image_filename}</span>
              </div>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
                <div className="detail-item">
                  <span className="detail-label">Size</span>
                  <span className="detail-value">{formatBytes(evidence.image_size_bytes)}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Type</span>
                  <span className="detail-value" style={{ fontSize:'0.8rem' }}>{evidence.image_mime_type}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div style={{ display:'flex', flexDirection:'column', gap:8, marginTop:12 }}>
            <button className="btn btn-secondary" onClick={runAIVerify} disabled={aiLoading}>
              <Cpu size={15} />
              {aiLoading ? 'Running AI Analysis...' : 'Run AI Verification'}
            </button>
            {(!bc || bc.status === 'NOT_REGISTERED') ? (
              <button className="btn btn-primary" onClick={registerBlockchain} disabled={bcLoading}>
                <Blocks size={15} />
                {bcLoading ? 'Registering...' : 'Register on Blockchain'}
              </button>
            ) : (
              <button className="btn btn-secondary" onClick={verifyBlockchain} disabled={bcLoading}>
                <Shield size={15} />
                {bcLoading ? 'Verifying...' : 'Verify Blockchain Hash'}
              </button>
            )}
          </div>
        </div>

        {/* Details */}
        <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
          {/* Core Info */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">📋 Evidence Information</h3>
            </div>
            <div className="detail-grid">
              <div className="detail-item">
                <span className="detail-label">Evidence ID</span>
                <span className="detail-value" style={{ fontSize:'0.75rem' }}>{evidence.id}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Captured</span>
                <span className="detail-value">{meta ? formatDateTime(meta.capture_timestamp) : formatDateTime(evidence.created_at)}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Officer</span>
                <span className="detail-value">{evidence.user?.full_name ?? '—'}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Timezone</span>
                <span className="detail-value">{meta?.timezone ?? '—'}</span>
              </div>
            </div>
          </div>

          {/* GPS */}
          {meta && (
            <div className="card">
              <div className="card-header">
                <h3 className="card-title"><MapPin size={16} style={{ verticalAlign:'middle', marginRight:6 }} />GPS Location</h3>
              </div>
              <div className="detail-grid">
                <div className="detail-item">
                  <span className="detail-label">Latitude</span>
                  <span className="detail-value">{meta.latitude.toFixed(6)}°</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Longitude</span>
                  <span className="detail-value">{meta.longitude.toFixed(6)}°</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">GPS Accuracy</span>
                  <span className="detail-value">{meta.gps_accuracy_meters?.toFixed(1) ?? '—'} m</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Altitude</span>
                  <span className="detail-value">{meta.altitude_meters?.toFixed(1) ?? '—'} m</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Device</span>
                  <span className="detail-value">{meta.device_model ?? '—'}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">OS</span>
                  <span className="detail-value">{meta.os_type} {meta.os_version}</span>
                </div>
              </div>
            </div>
          )}

          {/* Hash */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title"><Hash size={16} style={{ verticalAlign:'middle', marginRight:6 }} />Image Hash</h3>
            </div>
            <div className="detail-item">
              <span className="detail-label">SHA-256 Hash</span>
              <div className="hash-display">{evidence.image_sha256_hash}</div>
            </div>
          </div>

          {/* AI Verification */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title"><Cpu size={16} style={{ verticalAlign:'middle', marginRight:6 }} />AI Verification</h3>
              {ai && <span className={aiStatusBadgeClass(ai.status)}>{ai.status}</span>}
            </div>
            {ai ? (
              <div>
                <div className="detail-grid" style={{ marginBottom:12 }}>
                  <div className="detail-item">
                    <span className="detail-label">Tamper Probability</span>
                    <span className="detail-value" style={{ color: (ai.tamper_probability ?? 0) > 0.3 ? '#ef4444' : '#10b981' }}>
                      {formatPercent(ai.tamper_probability)}
                    </span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Confidence</span>
                    <span className="detail-value">{formatPercent(ai.confidence_score)}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">ELA Score</span>
                    <span className="detail-value">{ai.ela_score?.toFixed(4) ?? '—'}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Noise Score</span>
                    <span className="detail-value">{ai.noise_score?.toFixed(4) ?? '—'}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Model</span>
                    <span className="detail-value">{ai.model_version}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Verified At</span>
                    <span className="detail-value">{ai.verified_at ? formatDateTime(ai.verified_at) : '—'}</span>
                  </div>
                </div>
                {ai.verification_message && (
                  <div style={{
                    background:'var(--bg-elevated)', borderRadius:'var(--radius-md)',
                    padding:'12px', fontSize:'0.8rem', color:'var(--text-secondary)',
                    fontStyle:'italic', borderLeft:`3px solid ${ai.status === 'VERIFIED' ? '#10b981' : ai.status === 'SUSPICIOUS' ? '#ef4444' : '#f59e0b'}`
                  }}>
                    {ai.verification_message}
                  </div>
                )}
              </div>
            ) : (
              <p style={{ color:'var(--text-muted)', fontSize:'0.85rem' }}>
                No AI verification yet. Click "Run AI Verification" to analyze.
              </p>
            )}
          </div>

          {/* Blockchain */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title"><Blocks size={16} style={{ verticalAlign:'middle', marginRight:6 }} />Blockchain Record</h3>
              {bc && <span className={blockchainStatusBadgeClass(bc.status)}>{bc.status.replace('_', ' ')}</span>}
            </div>
            {bc && bc.status !== 'NOT_REGISTERED' ? (
              <div className="detail-grid">
                <div className="detail-item">
                  <span className="detail-label">Transaction ID</span>
                  <div className="hash-display">{bc.transaction_id ?? '—'}</div>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Block Number</span>
                  <span className="detail-value">#{bc.block_number}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Provider</span>
                  <span className="detail-value">{bc.provider}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Registered At</span>
                  <span className="detail-value">{bc.registered_at ? formatDateTime(bc.registered_at) : '—'}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Block Hash</span>
                  <div className="hash-display">{bc.block_hash}</div>
                </div>
              </div>
            ) : (
              <p style={{ color:'var(--text-muted)', fontSize:'0.85rem' }}>
                Evidence hash not yet registered on blockchain.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
