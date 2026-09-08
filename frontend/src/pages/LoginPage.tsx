import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import krLogo from '../kr-logo.png'
import toast from 'react-hot-toast'
import { Eye, EyeOff, Lock, Mail, Map, Shield, Zap } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export default function LoginPage() {
  const { login, isAuthenticated, loading } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('admin@giotag.gov')
  const [password, setPassword] = useState('Admin@123!')
  const [showPass, setShowPass] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const { t } = useTranslation()

  if (!loading && isAuthenticated) return <Navigate to="/" replace />

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login(email, password)
      toast.success('Welcome back!')
      navigate('/')
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Login failed. Check your credentials.'
      setError(msg)
      toast.error(msg)
    } finally {
      setSubmitting(false)
    }
  }

  const quickLogin = (preset: { email: string; password: string }) => {
    setEmail(preset.email)
    setPassword(preset.password)
  }

  const demoAccounts = [
    { label: 'Super Admin', email: 'admin@giotag.gov', password: 'Admin@123!' },
    { label: 'Dept Admin', email: 'deptadmin@giotag.gov', password: 'DeptAdmin@123!' },
    { label: 'Field Officer', email: 'officer1@giotag.gov', password: 'Officer@123!' },
    { label: 'Viewer', email: 'viewer@giotag.gov', password: 'Viewer@123!' },
  ]

  return (
    <div className="auth-page">
      {/* Left side: Premium Illustration / Branding */}
      <div className="auth-illustration">
        <div className="auth-shapes">
          <div className="shape shape-1"></div>
          <div className="shape shape-2"></div>
          <div className="shape shape-3"></div>
        </div>
        <div className="auth-illustration-content">
          <div className="auth-brand-badge">
            <img src={krLogo} alt="KR Group Logo" style={{ height: '32px', width: 'auto', objectFit: 'contain', marginRight: '8px' }} />
            <span>KR Group POULTRY</span>
          </div>
          <h1 className="auth-hero-title">
            Smart Poultry <br />
            <span className="text-gradient">Management System</span>
          </h1>
          <p className="auth-hero-subtitle">
            Advanced AI-powered egg counting and monitoring platform for modern poultry farms.
          </p>
          
          <div className="auth-features">
            <div className="feature-item">
              <div className="feature-icon"><Map /></div>
              <div>
                <h4>Automated Egg Counting</h4>
                <p>AI-powered real-time detection</p>
              </div>
            </div>
            <div className="feature-item">
              <div className="feature-icon"><Zap /></div>
              <div>
                <h4>Analytics & Reports</h4>
                <p>Track production efficiency easily</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Right side: Login Form */}
      <div className="auth-content">
        <div className="auth-card">
          <div className="auth-header">
            <h2>{t('login.welcome')}</h2>
            <p>{t('login.subtitle')}</p>
          </div>

          <form className="auth-form" onSubmit={handleSubmit}>
            {error && <div className="error-box slide-down">{error}</div>}

            <div className="form-group">
              <label className="form-label">{t('login.emailLabel')}</label>
              <div className="input-with-icon">
                <Mail className="input-icon" size={18} />
                <input
                  className="form-input glass-input"
                  type="text"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="you@agency.gov"
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">{t('login.passwordLabel')}</label>
              <div className="input-with-icon">
                <Lock className="input-icon" size={18} />
                <input
                  className="form-input glass-input"
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  className="password-toggle"
                  onClick={() => setShowPass(!showPass)}
                >
                  {showPass ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button type="submit" className="btn btn-primary btn-lg auth-submit-btn" disabled={submitting}>
              {submitting ? <><div className="spinner" style={{width:18,height:18}} /> {t('login.authenticating')}</> : t('login.signInBtn')}
            </button>
          </form>

          {/* Demo accounts section */}
          <div className="demo-section">
            <div className="demo-divider">
              <span>{t('login.demoAccounts')}</span>
            </div>
            <div className="demo-grid">
              {demoAccounts.map(acc => (
                <button
                  key={acc.email}
                  type="button"
                  className="btn btn-secondary btn-sm demo-btn"
                  onClick={() => quickLogin(acc)}
                >
                  {acc.label}
                </button>
              ))}
            </div>
          </div>

          <p className="auth-footer-note">
            {t('login.demoNote')}
          </p>
        </div>
      </div>
    </div>
  )
}
