import { useState, useEffect } from 'react'
import { farmApi } from '../api/farmApi'
import { PlusCircle, TrendingUp } from 'lucide-react'

export default function FinancialAnalyticsPage() {
  const [breakdown, setBreakdown] = useState<{ expenses: any[], revenue: any[] }>({ expenses: [], revenue: [] })
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  
  const [formData, setFormData] = useState({ type: 'EXPENSE', category: 'Feed', amount: 0, description: '' })

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    setLoading(true)
    try {
      const data = await farmApi.getFinanceBreakdown(30)
      setBreakdown(data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await farmApi.addFinanceRecord(formData)
      setShowForm(false)
      setFormData({ type: 'EXPENSE', category: 'Feed', amount: 0, description: '' })
      fetchData()
    } catch (err) {
      console.error(err)
    }
  }

  if (loading) return <div className="loading-screen"><div className="spinner"></div></div>

  return (
    <div className="page-with-bg fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">Financial Analytics</h1>
          <p className="page-subtitle">Track revenue and expenses</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          <PlusCircle size={16} style={{ marginRight: 8 }} />
          Add Record
        </button>
      </div>

      {showForm && (
        <div style={{ marginBottom: 24, padding: 24, background: 'var(--bg-card)', borderRadius: 12, border: '1px solid var(--border-color)' }}>
          <h3 style={{ margin: '0 0 16px 0' }}>Add Financial Record</h3>
          <form onSubmit={handleSubmit} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Type</label>
              <select className="form-select" value={formData.type} onChange={e => setFormData({ ...formData, type: e.target.value })}>
                <option value="EXPENSE">Expense</option>
                <option value="REVENUE">Revenue</option>
              </select>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Category</label>
              <input type="text" className="form-input" required value={formData.category} onChange={e => setFormData({ ...formData, category: e.target.value })} placeholder="e.g. Feed, Medicine, Egg Sales" />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Amount ($)</label>
              <input type="number" step="0.01" className="form-input" required value={formData.amount} onChange={e => setFormData({ ...formData, amount: Number(e.target.value) })} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Description</label>
              <input type="text" className="form-input" value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} />
            </div>
            <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
              <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
              <button type="submit" className="btn btn-primary">Save Record</button>
            </div>
          </form>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 32 }}>
        <div>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '0 0 16px 0' }}>
            <TrendingUp size={24} color="#10B981" />
            Revenue Breakdown (30 Days)
          </h2>
          {!breakdown?.revenue?.length ? <p style={{ color: 'var(--text-secondary)' }}>No revenue data.</p> : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {breakdown.revenue.map((r, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: 16, background: 'var(--bg-card)', borderRadius: 8, border: '1px solid var(--border-color)' }}>
                  <span>{r?.category || 'Unknown'}</span>
                  <span style={{ fontWeight: 600, color: '#10B981' }}>${Number(r?.amount || 0).toFixed(2)}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '0 0 16px 0' }}>
            <TrendingUp size={24} color="#EF4444" style={{ transform: 'rotate(180deg)' }} />
            Expense Breakdown (30 Days)
          </h2>
          {!breakdown?.expenses?.length ? <p style={{ color: 'var(--text-secondary)' }}>No expense data.</p> : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {breakdown.expenses.map((e, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: 16, background: 'var(--bg-card)', borderRadius: 8, border: '1px solid var(--border-color)' }}>
                  <span>{e?.category || 'Unknown'}</span>
                  <span style={{ fontWeight: 600, color: '#EF4444' }}>${Number(e?.amount || 0).toFixed(2)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
