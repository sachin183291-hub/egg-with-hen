import { useState, useEffect, useRef } from 'react'
import { gisApi } from '../services/api'
import type { GISMarker, EvidenceStatus } from '../types'
import { evidenceStatusBadgeClass, markerColor, makeMarkerIcon, formatDateTime, formatPercent } from '../utils/helpers'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'

// We load Leaflet from window (CDN in index.html)
declare const L: any

const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'VERIFIED', label: 'Verified' },
  { value: 'SUSPICIOUS', label: 'Suspicious' },
  { value: 'REVIEW_REQUIRED', label: 'Review Required' },
  { value: 'PENDING_SYNC', label: 'Pending' },
]

export default function GISMapPage() {
  const navigate = useNavigate()
  const mapRef = useRef<any>(null)
  const mapDivRef = useRef<HTMLDivElement>(null)
  const [markers, setMarkers] = useState<GISMarker[]>([])
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<GISMarker | null>(null)

  // Initialize Leaflet map
  useEffect(() => {
    if (!mapDivRef.current || mapRef.current) return
    if (typeof L === 'undefined') {
      console.error('Leaflet not loaded')
      return
    }

    const map = L.map(mapDivRef.current, { zoomControl: true }).setView([39.5, -98.35], 4)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
    }).addTo(map)
    mapRef.current = map

    return () => {
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
      }
    }
  }, [])

  // Load and render markers
  useEffect(() => {
    gisApi.evidence(statusFilter ? { status: statusFilter } : {})
      .then(r => {
        setMarkers(r.data)
        renderMarkers(r.data)
      })
      .catch(() => toast.error('Failed to load map data'))
      .finally(() => setLoading(false))
  }, [statusFilter])

  const renderMarkers = (data: GISMarker[]) => {
    if (!mapRef.current || typeof L === 'undefined') return

    // Clear existing markers
    mapRef.current.eachLayer((layer: any) => {
      if (layer._giotag_marker) mapRef.current.removeLayer(layer)
    })

    data.forEach(marker => {
      const color = markerColor(marker.status)
      const svgIcon = L.divIcon({
        html: makeMarkerIcon(color),
        className: '',
        iconSize: [28, 36],
        iconAnchor: [14, 36],
        popupAnchor: [0, -36],
      })

      const lmarker = L.marker([marker.latitude, marker.longitude], { icon: svgIcon })
      lmarker._giotag_marker = true
      lmarker.addTo(mapRef.current)
      lmarker.on('click', () => setSelected(marker))

      const popupContent = `
        <div class="evidence-popup">
          <h4>${marker.evidence_number}</h4>
          <p>👮 ${marker.officer_name}</p>
          <p>📅 ${new Date(marker.capture_timestamp).toLocaleString()}</p>
          <p>📍 ${marker.latitude.toFixed(5)}, ${marker.longitude.toFixed(5)}</p>
          <p>Status: <strong>${marker.status.replace('_', ' ')}</strong></p>
          ${marker.ai_confidence != null ? `<p>AI Confidence: ${(marker.ai_confidence * 100).toFixed(0)}%</p>` : ''}
        </div>
      `
      lmarker.bindPopup(popupContent)
    })
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">GIS Evidence Map</h1>
          <p className="page-subtitle">{markers.length} evidence records plotted</p>
        </div>
        <div style={{ display:'flex', gap:8 }}>
          {STATUS_FILTERS.map(f => (
            <button key={f.value}
              className={`btn btn-sm ${statusFilter === f.value ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setStatusFilter(f.value)}
            >{f.label}</button>
          ))}
        </div>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 300px', gap:20 }}>
        {/* Map */}
        <div>
          <div ref={mapDivRef} style={{ height:600, borderRadius:'var(--radius-lg)', overflow:'hidden', border:'1px solid var(--border-subtle)' }} />
          {loading && (
            <div style={{ position:'absolute', top:'50%', left:'50%', transform:'translate(-50%,-50%)' }}>
              <div className="spinner" />
            </div>
          )}

          {/* Legend */}
          <div className="card" style={{ marginTop:12, padding:'12px 16px' }}>
            <div style={{ display:'flex', gap:20, flexWrap:'wrap' }}>
              {[
                { label:'Verified',       color:'#10b981' },
                { label:'Suspicious',     color:'#ef4444' },
                { label:'Review Required',color:'#f59e0b' },
                { label:'Pending/Other',  color:'#6366f1' },
              ].map(l => (
                <div key={l.label} style={{ display:'flex', alignItems:'center', gap:6 }}>
                  <div style={{ width:12, height:12, borderRadius:'50%', background:l.color }} />
                  <span style={{ fontSize:'0.75rem', color:'var(--text-secondary)' }}>{l.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Selected Evidence Panel */}
        <div>
          {selected ? (
            <div className="card">
              <div className="card-header">
                <h3 className="card-title" style={{ fontSize:'0.85rem' }}>Selected Evidence</h3>
                <button className="btn btn-ghost btn-sm" onClick={() => setSelected(null)}>✕</button>
              </div>
              <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
                <div>
                  <span style={{ fontSize:'1rem', fontWeight:700, color:'var(--text-primary)' }}>
                    {selected.evidence_number}
                  </span>
                </div>
                <span className={evidenceStatusBadgeClass(selected.status)}>
                  {selected.status.replace('_', ' ')}
                </span>

                <div className="detail-item">
                  <span className="detail-label">Officer</span>
                  <span className="detail-value">{selected.officer_name}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Captured</span>
                  <span className="detail-value" style={{ fontSize:'0.8rem' }}>{formatDateTime(selected.capture_timestamp)}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">GPS</span>
                  <span className="detail-value" style={{ fontSize:'0.8rem' }}>
                    {selected.latitude.toFixed(5)}, {selected.longitude.toFixed(5)}
                  </span>
                </div>
                {selected.ai_confidence != null && (
                  <div className="detail-item">
                    <span className="detail-label">AI Confidence</span>
                    <span className="detail-value">{formatPercent(selected.ai_confidence)}</span>
                  </div>
                )}
                {selected.blockchain_status && (
                  <div className="detail-item">
                    <span className="detail-label">Blockchain</span>
                    <span className="detail-value">{selected.blockchain_status.replace('_', ' ')}</span>
                  </div>
                )}
                <button className="btn btn-primary btn-sm"
                  onClick={() => navigate(`/evidence/${selected.evidence_id}`)}>
                  View Full Details →
                </button>
              </div>
            </div>
          ) : (
            <div className="card" style={{ textAlign:'center', padding:40 }}>
              <div style={{ fontSize:32, marginBottom:8 }}>🗺️</div>
              <p style={{ color:'var(--text-muted)', fontSize:'0.85rem' }}>
                Click a marker on the map to see evidence details
              </p>
            </div>
          )}

          {/* Summary */}
          <div className="card" style={{ marginTop:12 }}>
            <h4 className="card-title" style={{ marginBottom:12, fontSize:'0.85rem' }}>Evidence Summary</h4>
            {[
              { label:'Total Plotted', value: markers.length },
              { label:'Verified', value: markers.filter(m => m.status === 'VERIFIED').length, color:'#10b981' },
              { label:'Suspicious', value: markers.filter(m => m.status === 'SUSPICIOUS').length, color:'#ef4444' },
              { label:'Review Required', value: markers.filter(m => m.status === 'REVIEW_REQUIRED').length, color:'#f59e0b' },
            ].map(s => (
              <div key={s.label} style={{ display:'flex', justifyContent:'space-between', padding:'6px 0', borderBottom:'1px solid var(--border-subtle)' }}>
                <span style={{ fontSize:'0.8rem', color:'var(--text-secondary)' }}>{s.label}</span>
                <span style={{ fontSize:'0.8rem', fontWeight:700, color: s.color ?? 'var(--text-primary)' }}>{s.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
