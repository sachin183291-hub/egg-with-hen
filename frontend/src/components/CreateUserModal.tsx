import React, { useState } from 'react';
import { X, UserPlus, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { usersApi } from '../services/api';

interface CreateUserModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

export default function CreateUserModal({ onClose, onSuccess }: CreateUserModalProps) {
  const [formData, setFormData] = useState({
    email: '',
    username: '',
    full_name: '',
    phone: '',
    password: '',
    role: 'FIELD_OFFICER',
  });
  const [loading, setLoading] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await usersApi.create(formData);
      toast.success('User created successfully!');
      onSuccess();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || err.message || 'Failed to create user');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ position:'fixed', top:0, left:0, right:0, bottom:0, background:'rgba(0,0,0,0.6)', zIndex:999, display:'flex', alignItems:'center', justifyContent:'center' }}>
      <div className="card" style={{ width: 450, maxWidth: '90%', position:'relative', padding: 24, maxHeight: '90vh', overflowY: 'auto' }}>
        <button onClick={onClose} style={{ position:'absolute', top:16, right:16, background:'none', border:'none', cursor:'pointer', color:'var(--text-muted)' }}>
          <X size={20} />
        </button>
        <h2 style={{ marginTop:0, marginBottom:20, fontSize:20 }}>Add New User</h2>
        <form onSubmit={handleSubmit} style={{ display:'flex', flexDirection:'column', gap:16 }}>
          
          <div>
            <label style={{ display:'block', marginBottom:8, fontSize:14, fontWeight:500 }}>Full Name</label>
            <input type="text" name="full_name" className="form-input" required
              value={formData.full_name} onChange={handleChange} placeholder="John Doe" />
          </div>

          <div>
            <label style={{ display:'block', marginBottom:8, fontSize:14, fontWeight:500 }}>Username</label>
            <input type="text" name="username" className="form-input" required
              value={formData.username} onChange={handleChange} placeholder="johndoe" />
          </div>

          <div>
            <label style={{ display:'block', marginBottom:8, fontSize:14, fontWeight:500 }}>Email Address</label>
            <input type="email" name="email" className="form-input" required
              value={formData.email} onChange={handleChange} placeholder="john@example.com" />
          </div>

          <div>
            <label style={{ display:'block', marginBottom:8, fontSize:14, fontWeight:500 }}>Phone (Optional)</label>
            <input type="text" name="phone" className="form-input"
              value={formData.phone} onChange={handleChange} placeholder="+1234567890" />
          </div>

          <div>
            <label style={{ display:'block', marginBottom:8, fontSize:14, fontWeight:500 }}>Role</label>
            <select name="role" className="form-input" value={formData.role} onChange={handleChange}>
              <option value="VIEWER">Viewer</option>
              <option value="FIELD_OFFICER">Field Officer</option>
              <option value="DEPT_ADMIN">Department Admin</option>
              <option value="SUPER_ADMIN">Super Admin</option>
            </select>
          </div>

          <div>
            <label style={{ display:'block', marginBottom:8, fontSize:14, fontWeight:500 }}>Password</label>
            <input type="password" name="password" className="form-input" required
              value={formData.password} onChange={handleChange} placeholder="StrongPassword123" />
            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
              Must be at least 8 characters, with 1 uppercase and 1 number.
            </p>
          </div>

          <div style={{ marginTop: 8 }}>
            <button type="submit" className="btn btn-primary" disabled={loading} style={{ width:'100%', justifyContent:'center' }}>
              {loading ? <Loader2 size={16} className="spin" /> : <UserPlus size={16} />}
              Create User
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
