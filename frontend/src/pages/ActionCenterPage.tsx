import { useState, useEffect } from 'react'
import { farmApi } from '../api/farmApi'
import { AlertTriangle, CheckCircle, Clock } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'

export default function ActionCenterPage() {
  const [alerts, setAlerts] = useState<any[]>([])
  const [anomalies, setAnomalies] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const { user } = useAuth()

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    setLoading(true)
    try {
      const [alertData, anomalyData] = await Promise.all([
        farmApi.getAlerts(),
        farmApi.getAnomalies()
      ])
      setAlerts(alertData)
      setAnomalies(anomalyData)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleAcknowledge = async (id: string) => {
    try {
      await farmApi.acknowledgeAlert(id)
      fetchData()
    } catch (err) {
      console.error(err)
    }
  }

  const handleResolve = async (id: string) => {
    try {
      await farmApi.resolveAlert(id)
      fetchData()
    } catch (err) {
      console.error(err)
    }
  }

  if (loading) return <div className="loading-screen"><div className="spinner"></div></div>

  return (
    <div className="page-with-bg fade-in">
      <div className="page-header">
        <h1 className="page-title">Action Center</h1>
        <p className="page-subtitle">Manage alerts, operational anomalies, and tasks</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: 32 }}>
        
        {/* Alerts Section */}
        <div>
          <h2 style={{ margin: '0 0 16px 0' }}>Active Alerts</h2>
          {alerts.filter(a => a.status !== 'RESOLVED').length === 0 ? (
            <div style={{ padding: 24, background: 'var(--bg-card)', borderRadius: 12, textAlign: 'center', color: 'var(--text-secondary)' }}>
              No active alerts. All good!
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {alerts.filter(a => a.status !== 'RESOLVED').map(alert => (
                <div key={alert.id} style={{ 
                  padding: 16, 
                  background: 'var(--bg-card)', 
                  borderLeft: `4px solid ${alert.type === 'CRITICAL' ? '#EF4444' : '#F59E0B'}`,
                  borderRadius: 8,
                  boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <h4 style={{ margin: '0 0 4px 0', display: 'flex', alignItems: 'center', gap: 8 }}>
                        <AlertTriangle size={18} color={alert.type === 'CRITICAL' ? '#EF4444' : '#F59E0B'} />
                        {alert.title}
                      </h4>
                      <p style={{ margin: 0, fontSize: 14, color: 'var(--text-secondary)' }}>{alert.message}</p>
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 8 }}>
                        <Clock size={12} style={{ display: 'inline', marginRight: 4 }} />
                        {new Date(alert.created_at).toLocaleString()} | Status: {alert.status}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      {alert.status === 'NEW' && (
                        <button className="btn btn-ghost btn-sm" onClick={() => handleAcknowledge(alert.id)}>
                          Acknowledge
                        </button>
                      )}
                      <button className="btn btn-primary btn-sm" onClick={() => handleResolve(alert.id)}>
                        Resolve
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Anomalies Section */}
        <div>
          <h2 style={{ margin: '0 0 16px 0' }}>Operational Anomalies</h2>
          {anomalies.length === 0 ? (
            <div style={{ padding: 24, background: 'var(--bg-card)', borderRadius: 12, textAlign: 'center', color: 'var(--text-secondary)' }}>
              No recent anomalies detected.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {anomalies.map(anomaly => (
                <div key={anomaly.id} style={{ 
                  padding: 16, 
                  background: 'var(--bg-card)', 
                  border: '1px solid var(--border-color)',
                  borderRadius: 8
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <h4 style={{ margin: '0 0 4px 0' }}>{anomaly.type}</h4>
                      <p style={{ margin: 0, fontSize: 14, color: 'var(--text-secondary)' }}>
                        Observed: <span style={{ color: '#EF4444', fontWeight: 600 }}>{anomaly.observed_value}</span> | 
                        Expected: <span>{anomaly.expected_value}</span>
                      </p>
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 8 }}>
                        Severity: {anomaly.severity} | Zone ID: {anomaly.zone_id || 'System'} | Date: {new Date(anomaly.date).toLocaleDateString()}
                      </div>
                    </div>
                    {anomaly.status === 'RESOLVED' ? (
                      <CheckCircle size={20} color="#10B981" />
                    ) : (
                      <span className="badge badge-review">{anomaly.status}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  )
}
