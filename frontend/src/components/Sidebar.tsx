import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { getInitials } from '../utils/helpers'
import { useTranslation } from 'react-i18next'
import {
  LayoutDashboard, Map, Image, Users, Cpu, Blocks,
  ClipboardList, BarChart2, Settings, Shield, Smartphone, LogOut, CheckSquare, MessageCircle, Globe, HeartPulse
} from 'lucide-react'

const navItems = [
  { group: 'Main', items: [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/map', label: 'GIS Map', icon: Map },
    { to: '/evidence', label: 'Evidence', icon: Image },
  ]},
  { group: 'Management', items: [
    { to: '/users', label: 'Users', icon: Users },
    { to: '/devices', label: 'Devices', icon: Smartphone },
  ]},
  { group: 'Verification', items: [
    { to: '/ai-verification', label: 'AI Verification', icon: Cpu },
    { to: '/egg-counter', label: 'Egg Counter', icon: CheckSquare },
    { to: '/egg-ai-chat', label: 'AI Vision Chat', icon: MessageCircle },
    { to: '/hen-health', label: 'Hen Health', icon: HeartPulse },
    { to: '/blockchain', label: 'Blockchain', icon: Blocks },
  ]},
  { group: 'Records', items: [
    { to: '/audit-logs', label: 'Audit Logs', icon: ClipboardList },
    { to: '/reports', label: 'Reports', icon: BarChart2 },
    { to: '/settings', label: 'Settings', icon: Settings },
  ]},
]

export default function Sidebar({ isOpen, onClose }: { isOpen?: boolean, onClose?: () => void }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const toggleLanguage = () => {
    const newLang = i18n.language === 'en' ? 'ta' : 'en'
    i18n.changeLanguage(newLang)
  }

  return (
    <>
      <div 
        className={`sidebar-overlay ${isOpen ? 'open' : ''}`} 
        onClick={onClose}
      />
      <aside className={`sidebar ${isOpen ? 'open' : ''}`}>
        <div className="sidebar-logo">
          <div className="sidebar-logo-mark">
            <img src="https://img.sanishtech.com/u/e4981fe5381a1990b40fb04b81c7173d.png" alt="KR Group Logo" style={{ height: '40px', width: 'auto', objectFit: 'contain' }} />
            <div className="sidebar-logo-text" style={{ marginLeft: '10px' }}>
              <span className="sidebar-logo-name">KR Group</span>
              <span className="sidebar-logo-sub">POULTRY</span>
            </div>
          </div>
        </div>

        <nav className="sidebar-nav">
          {navItems.map(group => (
            <div key={group.group}>
              <div className="sidebar-section-label">{t(`sidebar.groups.${group.group}`)}</div>
              {group.items.map(item => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  onClick={onClose}
                  className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
                >
                  <item.icon size={16} className="nav-icon" />
                  {t(`sidebar.items.${item.label}`)}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-user">
          <div className="sidebar-user-info">
            <div className="avatar">{user ? getInitials(user.full_name) : '?'}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="user-name" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user?.full_name}
              </div>
              <div className="user-role">{user?.role?.replace('_', ' ')}</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={toggleLanguage} title="Toggle Language" style={{ marginRight: 4 }}>
              <Globe size={15} /> {t('sidebar.language')}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={handleLogout} title="Logout">
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}

