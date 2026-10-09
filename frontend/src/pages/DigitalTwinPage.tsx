import { useState, useEffect } from 'react'
import { farmApi } from '../api/farmApi'
import { Layers, Thermometer, Activity, AlertCircle, CheckCircle } from 'lucide-react'

export default function DigitalTwinPage() {
  const [structure, setStructure] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchStructure()
  }, [])

  const fetchStructure = async () => {
    try {
      const data = await farmApi.getStructure()
      setStructure(data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="loading-screen"><div className="spinner"></div></div>

  return (
    <div className="page-with-bg fade-in">
      <div className="page-header">
        <h1 className="page-title">Digital Twin</h1>
        <p className="page-subtitle">Real-time hierarchical farm status</p>
      </div>

      {structure.map(farm => (
        <div key={farm.id} style={{ marginBottom: 32 }}>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '0 0 16px 0' }}>
            <Layers size={24} color="var(--brand-500)" />
            {farm.name} <span style={{ fontSize: 14, color: 'var(--text-secondary)', fontWeight: 'normal' }}>({farm.location})</span>
          </h2>

          {farm.sheds.map((shed: any) => (
            <div key={shed.id} style={{ 
              marginTop: 16, 
              padding: 24, 
              background: 'var(--bg-card)', 
              borderRadius: 12, 
              border: '1px solid var(--border-color)' 
            }}>
              <h3 style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: 12, margin: '0 0 16px 0' }}>
                {shed.name}
              </h3>
              
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 24 }}>
                {shed.zones.map((zone: any) => {
                  const m = zone.metrics
                  const isAlert = m.temperature > 27 || m.temperature < 20
                  
                  return (
                    <div key={zone.id} style={{ 
                      padding: 16, 
                      borderRadius: 8, 
                      background: isAlert ? 'rgba(239, 68, 68, 0.05)' : 'rgba(16, 185, 129, 0.05)',
                      border: `1px solid ${isAlert ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)'}`
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                        <h4 style={{ margin: 0 }}>{zone.name}</h4>
                        {isAlert ? <AlertCircle size={20} color="#EF4444" /> : <CheckCircle size={20} color="#10B981" />}
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 14 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-secondary)' }}><Activity size={14} style={{ display: 'inline', marginRight: 4 }}/> Hens (AI Tracked)</span>
                          <span style={{ fontWeight: 600 }}>{m.total_hens.toLocaleString()}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-secondary)' }}>Eggs Produced</span>
                          <span style={{ fontWeight: 600 }}>{m.eggs_produced.toLocaleString()}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-secondary)' }}><Thermometer size={14} style={{ display: 'inline', marginRight: 4 }}/> Temperature</span>
                          <span style={{ fontWeight: 600, color: isAlert ? '#EF4444' : 'inherit' }}>
                            {m.temperature ? `${m.temperature.toFixed(1)}°C` : 'N/A'}
                          </span>
                        </div>
                      </div>
                      
                      <div style={{ marginTop: 16, fontSize: 12, color: 'var(--text-secondary)' }}>
                        Contains {zone.rows.length} rows, {zone.rows.reduce((acc: number, r: any) => acc + r.cages.length, 0)} cages.
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
