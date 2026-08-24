import { Routes, Route } from 'react-router-dom'
import { AuthProvider } from './hooks/useAuth'
import DashboardLayout from './layouts/DashboardLayout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import EvidencePage from './pages/EvidencePage'
import EvidenceDetailPage from './pages/EvidenceDetailPage'
import GISMapPage from './pages/GISMapPage'
import UsersPage from './pages/UsersPage'
import DevicesPage from './pages/DevicesPage'
import AIVerificationPage from './pages/AIVerificationPage'
import BlockchainPage from './pages/BlockchainPage'
import AuditLogsPage from './pages/AuditLogsPage'
import ReportsPage from './pages/ReportsPage'
import SettingsPage from './pages/SettingsPage'
import EggCounterPage from './pages/EggCounterPage'
import EggAIChatPage from './pages/EggAIChatPage'
import HenHealthPage from './pages/HenHealthPage'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<DashboardLayout />}>
          <Route path="/"                element={<DashboardPage />} />
          <Route path="/evidence"        element={<EvidencePage />} />
          <Route path="/evidence/:id"    element={<EvidenceDetailPage />} />
          <Route path="/map"             element={<GISMapPage />} />
          <Route path="/users"           element={<UsersPage />} />
          <Route path="/devices"         element={<DevicesPage />} />
          <Route path="/ai-verification" element={<AIVerificationPage />} />
          <Route path="/egg-counter"     element={<EggCounterPage />} />
          <Route path="/egg-ai-chat"    element={<EggAIChatPage />} />
          <Route path="/hen-health"     element={<HenHealthPage />} />
          <Route path="/blockchain"      element={<BlockchainPage />} />
          <Route path="/audit-logs"      element={<AuditLogsPage />} />
          <Route path="/reports"         element={<ReportsPage />} />
          <Route path="/settings"        element={<SettingsPage />} />
        </Route>
      </Routes>
    </AuthProvider>
  )
}
