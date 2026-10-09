import { useState, useEffect } from 'react'
import { farmApi } from '../api/farmApi'
import {
  TrendingUp, Activity, DollarSign, AlertTriangle, 
  Thermometer, Users, Egg
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

export default function FarmIntelligenceDashboard() {
  const [kpi, setKpi] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)
  const { t } = useTranslation()

  useEffect(() => {
    fetchKpi()
  }, [days])

  const fetchKpi = async () => {
    setLoading(true)
    try {
      const data = await farmApi.getBiKpi(days)
      setKpi(data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  if (loading || !kpi) {
    return <div className="page-container"><div className="spinner"></div></div>
  }

  const statCards = [
    { label: 'Total Birds', value: kpi.total_hens.toLocaleString(), icon: Activity, color: '#3b82f6', sub: `Unique Tracked: ${kpi.unique_hens.toLocaleString()}` },
    { label: 'Total Eggs', value: kpi.total_eggs.toLocaleString(), icon: Egg, color: '#f59e0b', sub: `Daily Avg: ${kpi.avg_daily_eggs.toLocaleString()}` },
    { label: 'Active Alerts', value: kpi.active_alerts.toLocaleString(), icon: AlertTriangle, color: '#ef4444', sub: `${kpi.critical_alerts} Critical` },
    { label: 'Avg Temperature', value: `${kpi.avg_temp.toFixed(1)}°C`, icon: Thermometer, color: '#10b981', sub: 'Optimal Range' },
    { label: 'Total Revenue', value: `$${kpi.total_revenue.toLocaleString()}`, icon: DollarSign, color: '#10b981', sub: 'From egg sales' },
    { label: 'Total Expenses', value: `$${kpi.total_expenses.toLocaleString()}`, icon: TrendingUp, color: '#ef4444', sub: 'Feed, Medical, etc' },
    { label: 'Net Profit', value: `$${kpi.net_profit.toLocaleString()}`, icon: DollarSign, color: kpi.net_profit >= 0 ? '#10b981' : '#ef4444', sub: kpi.net_profit >= 0 ? 'Profitable' : 'Loss' },
    { label: 'Cost Per Egg', value: `$${kpi.cost_per_egg.toFixed(2)}`, icon: Activity, color: '#8b5cf6', sub: 'Calculated' },
  ]

  return (
    <div className="page-with-bg fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">Business Intelligence</h1>
          <p className="page-subtitle">Poultry Farm Operational Metrics</p>
        </div>
        <select className="form-select" style={{ width: '150px' }} value={days} onChange={e => setDays(Number(e.target.value))}>
          <option value={7}>Last 7 Days</option>
          <option value={30}>Last 30 Days</option>
          <option value={90}>Last 90 Days</option>
          <option value={365}>Last Year</option>
        </select>
      </div>

      <div className="stat-grid">
        {statCards.map((card) => (
          <div key={card.label} className="stat-card" style={{ '--stat-color': card.color } as React.CSSProperties}>
            <div className="stat-icon">
              <card.icon size={20} color={card.color} />
            </div>
            <div>
              <div className="stat-value">{card.value}</div>
              <div className="stat-label">{card.label}</div>
              <div className="stat-change" style={{ color: card.color }}>{card.sub}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
