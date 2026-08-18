import { useState, useEffect, useCallback } from 'react'
import { usersApi } from '../services/api'
import type { User, PaginatedResponse } from '../types'
import { formatDateTime, getInitials } from '../utils/helpers'
import { Search, UserPlus, Edit2, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'

const ROLE_COLORS: Record<string, string> = {
  SUPER_ADMIN: 'badge badge-suspicious',
  DEPT_ADMIN:  'badge badge-review',
  FIELD_OFFICER:'badge badge-verified',
  VIEWER:      'badge badge-pending',
}

export default function UsersPage() {
  const [data, setData] = useState<PaginatedResponse<User> | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [showCreate, setShowCreate] = useState(false)

  const fetchData = useCallback(() => {
    setLoading(true)
    usersApi.list({ page, page_size:15, ...(search && { search }) })
      .then(r => setData(r.data))
      .catch(() => toast.error('Failed to load users'))
      .finally(() => setLoading(false))
  }, [page, search])

  useEffect(() => { fetchData() }, [fetchData])

  const toggleActive = async (user: User) => {
    await usersApi.update(user.id, { is_active: !user.is_active })
    toast.success(`User ${user.is_active ? 'deactivated' : 'activated'}`)
    fetchData()
  }

  const deleteUser = async (user: User) => {
    if (!confirm(`Delete user ${user.full_name}?`)) return
    await usersApi.delete(user.id)
    toast.success('User deleted')
    fetchData()
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">User Management</h1>
          <p className="page-subtitle">{data?.total ?? 0} registered users</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          <UserPlus size={15} /> Add User
        </button>
      </div>

      <div className="filters-bar">
        <div className="search-input-wrapper">
          <Search size={14} />
          <input className="form-input search-input"
            placeholder="Search users..."
            value={search} onChange={e => { setSearch(e.target.value); setPage(1) }} />
        </div>
      </div>

      <div className="card" style={{ padding:0 }}>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>User</th><th>Email</th><th>Role</th><th>Department</th>
                <th>Status</th><th>Last Login</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} style={{ textAlign:'center', padding:32, color:'var(--text-muted)' }}>Loading...</td></tr>
              ) : data?.items.map(user => (
                <tr key={user.id}>
                  <td>
                    <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                      <div className="avatar" style={{ width:32, height:32, fontSize:'0.75rem' }}>
                        {getInitials(user.full_name)}
                      </div>
                      <span style={{ color:'var(--text-primary)', fontWeight:500, fontSize:'0.875rem' }}>
                        {user.full_name}
                      </span>
                    </div>
                  </td>
                  <td style={{ fontSize:'0.8rem' }}>{user.email}</td>
                  <td><span className={ROLE_COLORS[user.role] ?? 'badge badge-pending'} style={{ fontSize:'0.65rem' }}>
                    {user.role.replace('_', ' ')}
                  </span></td>
                  <td style={{ fontSize:'0.8rem' }}>{user.department?.name ?? '—'}</td>
                  <td>
                    <span className={user.is_active ? 'badge badge-verified' : 'badge badge-rejected'}>
                      {user.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td style={{ fontSize:'0.75rem' }}>{user.last_login ? formatDateTime(user.last_login) : 'Never'}</td>
                  <td>
                    <div style={{ display:'flex', gap:6 }}>
                      <button className={`btn btn-sm ${user.is_active ? 'btn-secondary' : 'btn-primary'}`}
                        onClick={() => toggleActive(user)} style={{ fontSize:'0.7rem' }}>
                        {user.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                      <button className="btn btn-danger btn-sm" onClick={() => deleteUser(user)}>
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
