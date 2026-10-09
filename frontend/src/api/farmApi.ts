import { api } from '../services/api'

export const farmApi = {
  getStructure: async () => { const res = await api.get('/api/farm/structure'); return res.data; },
  getBiKpi: async (days = 30) => { const res = await api.get(`/api/farm/bi/kpi?days=${days}`); return res.data; },
  getProductionTrend: async (days = 30) => { const res = await api.get(`/api/farm/bi/production-trend?days=${days}`); return res.data; },
  getFinanceBreakdown: async (days = 30) => { const res = await api.get(`/api/farm/bi/finance-breakdown?days=${days}`); return res.data; },
  addFinanceRecord: async (data: { type: string, category: string, amount: number, description?: string, farm_id?: string }) => {
    const res = await api.post(`/api/farm/finance?type=${data.type}&category=${data.category}&amount=${data.amount}&description=${data.description||''}&farm_id=${data.farm_id||''}`);
    return res.data;
  },
  getAlerts: async (status?: string) => { const res = await api.get(`/api/farm/alerts${status ? `?status=${status}` : ''}`); return res.data; },
  acknowledgeAlert: async (id: string, note?: string) => { const res = await api.post(`/api/farm/alerts/${id}/acknowledge?note=${note||''}`); return res.data; },
  resolveAlert: async (id: string, note?: string) => { const res = await api.post(`/api/farm/alerts/${id}/resolve?note=${note||''}`); return res.data; },
  getAnomalies: async () => { const res = await api.get('/api/farm/anomalies'); return res.data; },
  getForecast: async () => { const res = await api.get('/api/farm/forecast'); return res.data; }
}
