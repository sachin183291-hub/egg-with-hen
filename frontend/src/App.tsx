import { Suspense, lazy } from 'react'
import { Routes, Route } from 'react-router-dom'
import { AuthProvider } from './hooks/useAuth'
import DashboardLayout from './layouts/DashboardLayout'

// Lazy load pages for better performance
const LoginPage = lazy(() => import('./pages/LoginPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const EvidencePage = lazy(() => import('./pages/EvidencePage'))
const EvidenceDetailPage = lazy(() => import('./pages/EvidenceDetailPage'))
const GISMapPage = lazy(() => import('./pages/GISMapPage'))
const UsersPage = lazy(() => import('./pages/UsersPage'))
const DevicesPage = lazy(() => import('./pages/DevicesPage'))
const AIVerificationPage = lazy(() => import('./pages/AIVerificationPage'))
const BlockchainPage = lazy(() => import('./pages/BlockchainPage'))
const AuditLogsPage = lazy(() => import('./pages/AuditLogsPage'))
const ReportsPage = lazy(() => import('./pages/ReportsPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const EggCounterPage = lazy(() => import('./pages/EggCounterPage'))
const EggAIChatPage = lazy(() => import('./pages/EggAIChatPage'))
const HenHealthPage = lazy(() => import('./pages/HenHealthPage'))
const ThermalCameraPage = lazy(() => import('./pages/ThermalCameraPage'))
const DronePage = lazy(() => import('./pages/DronePage'))

const PageLoader = () => (
  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', width: '100vw', backgroundColor: 'var(--bg-main)' }}>
    <div className="spinner" style={{ width: 40, height: 40, border: '3px solid rgba(255,255,255,0.1)', borderTopColor: 'var(--brand-500)', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
  </div>
)

export default function App() {
  return (
    <AuthProvider>
      <Suspense fallback={<PageLoader />}>
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
            <Route path="/thermal-camera"  element={<ThermalCameraPage />} />
            <Route path="/drone"           element={<DronePage />} />
            <Route path="/blockchain"      element={<BlockchainPage />} />
            <Route path="/audit-logs"      element={<AuditLogsPage />} />
            <Route path="/reports"         element={<ReportsPage />} />
            <Route path="/settings"        element={<SettingsPage />} />
          </Route>
        </Routes>
      </Suspense>
    </AuthProvider>
  )
}
