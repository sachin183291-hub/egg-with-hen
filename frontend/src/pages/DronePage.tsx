import React, { useState, useEffect } from 'react'
import { Plane, Battery, Wifi, Save, Activity, Signal, ArrowUp, Wind, Camera, MapPin, Video, Zap, Compass } from 'lucide-react'

export default function DronePage() {
  const [batteryLevel, setBatteryLevel] = useState(85)
  const [ipAddress, setIpAddress] = useState('192.168.1.100')
  const [savedIp, setSavedIp] = useState('192.168.1.100')
  const [isSaving, setIsSaving] = useState(false)
  
  // Drone status metrics
  const [isConnected, setIsConnected] = useState(true)
  const [altitude, setAltitude] = useState(15.2)
  const [speed, setSpeed] = useState(5.4)
  const [flightMode, setFlightMode] = useState('Patrol Mode')
  const [heading, setHeading] = useState(45)

  // Simulate battery drain and status fluctuation over time
  useEffect(() => {
    const interval = setInterval(() => {
      setBatteryLevel(prev => (prev > 0 ? prev - 1 : 0))
      
      if (isConnected) {
        setAltitude(prev => Number((prev + (Math.random() - 0.5) * 0.5).toFixed(1)))
        setSpeed(prev => Number((Math.max(0, prev + (Math.random() - 0.5) * 1.5)).toFixed(1)))
        setHeading(prev => (prev + (Math.random() - 0.5) * 5) % 360)
      }
    }, 3000)
    return () => clearInterval(interval)
  }, [isConnected])

  const handleSaveIp = () => {
    setIsSaving(true)
    setTimeout(() => {
      setSavedIp(ipAddress)
      setIsSaving(false)
      alert(`Drone IP Address successfully set to: ${ipAddress}`)
    }, 800)
  }

  return (
    <div className="page-container">
      <div className="page-header" style={{ marginBottom: '24px', background: 'linear-gradient(135deg, rgba(99,102,241,0.1), rgba(16,185,129,0.05))', border: '1px solid var(--border-subtle)' }}>
        <div>
          <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ padding: '10px', background: 'var(--brand-600)', borderRadius: '12px', display: 'flex', color: 'white', boxShadow: '0 4px 15px rgba(99,102,241,0.4)' }}>
              <Plane size={24} />
            </div>
            Tactical Drone Control
          </h1>
          <p className="page-subtitle" style={{ marginTop: '8px' }}>Advanced telemetry, live feed, and hardware configuration.</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div className={`badge ${isConnected ? 'badge-verified' : 'badge-rejected'}`} style={{ padding: '8px 16px', fontSize: '0.85rem' }}>
            <Signal size={16} />
            {isConnected ? 'Uplink Established' : 'Signal Lost'}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 350px', gap: '24px' }}>
        
        {/* Main Left Column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          {/* Live Video Feed Placeholder */}
          <div className="card" style={{ padding: '0', overflow: 'hidden', position: 'relative', border: '1px solid var(--border-strong)', boxShadow: '0 12px 40px rgba(0,0,0,0.15)' }}>
            <div style={{ position: 'absolute', top: '16px', left: '16px', zIndex: 10, display: 'flex', gap: '8px' }}>
              <span className="badge badge-suspicious" style={{ background: 'rgba(239,68,68,0.9)', color: 'white', animation: 'pulse 2s infinite' }}>
                <Video size={14} /> LIVE REC
              </span>
              <span className="badge badge-verified" style={{ background: 'rgba(0,0,0,0.6)', color: '#10b981', border: '1px solid rgba(255,255,255,0.2)' }}>
                1080p 60FPS
              </span>
            </div>
            
            {/* Crosshair Overlay */}
            <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', zIndex: 5, opacity: 0.5, pointerEvents: 'none' }}>
              <div style={{ width: '100px', height: '100px', border: '2px solid rgba(255,255,255,0.8)', borderRadius: '50%', position: 'relative' }}>
                <div style={{ position: 'absolute', top: '50%', left: '-20px', width: '15px', height: '2px', background: 'rgba(255,255,255,0.8)', transform: 'translateY(-50%)' }} />
                <div style={{ position: 'absolute', top: '50%', right: '-20px', width: '15px', height: '2px', background: 'rgba(255,255,255,0.8)', transform: 'translateY(-50%)' }} />
                <div style={{ position: 'absolute', left: '50%', top: '-20px', height: '15px', width: '2px', background: 'rgba(255,255,255,0.8)', transform: 'translateX(-50%)' }} />
                <div style={{ position: 'absolute', left: '50%', bottom: '-20px', height: '15px', width: '2px', background: 'rgba(255,255,255,0.8)', transform: 'translateX(-50%)' }} />
              </div>
            </div>

            <img 
              src="https://images.unsplash.com/photo-1508614589041-895b88991e3e?q=80&w=2000&auto=format&fit=crop" 
              alt="Drone View" 
              style={{ width: '100%', height: '450px', objectFit: 'cover', filter: 'contrast(1.1) saturate(1.2)' }} 
            />
            
            <div style={{ position: 'absolute', bottom: '0', left: '0', right: '0', background: 'linear-gradient(to top, rgba(0,0,0,0.8), transparent)', padding: '40px 20px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', color: 'white' }}>
              <div>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ArrowUp size={24} color="#3b82f6" /> {altitude}m
                </div>
                <div style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.7)', textTransform: 'uppercase', letterSpacing: '2px' }}>ALTITUDE (AGL)</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '1.2rem', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'center' }}>
                  <Compass size={20} style={{ transform: `rotate(${heading}deg)`, transition: 'transform 1s ease' }} color="#10b981" /> 
                  {Math.round(heading)}°
                </div>
                <div style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.7)', textTransform: 'uppercase', letterSpacing: '2px' }}>HEADING</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'flex-end' }}>
                  {speed} m/s <Wind size={24} color="#f59e0b" />
                </div>
                <div style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.7)', textTransform: 'uppercase', letterSpacing: '2px' }}>AIRSPEED</div>
              </div>
            </div>
          </div>

          {/* Configuration Section */}
          <div className="card" style={{ padding: '24px' }}>
            <h2 style={{ fontSize: '1.1rem', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Wifi size={20} color="var(--brand-400)" />
              Hardware Connection Settings
            </h2>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', alignItems: 'flex-end' }}>
              <div className="form-group">
                <label style={{ display: 'block', marginBottom: '8px', color: 'var(--text-secondary)' }}>
                  Current Telemetry Link
                </label>
                <div style={{ padding: '12px', backgroundColor: 'rgba(16,185,129,0.1)', borderRadius: '8px', border: '1px solid rgba(16,185,129,0.3)', color: '#10b981', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Activity size={16} /> tcp://{savedIp}:14550
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="droneIp" style={{ display: 'block', marginBottom: '8px', color: 'var(--text-secondary)' }}>
                  Override Drone IP Address
                </label>
                <div style={{ display: 'flex', gap: '12px' }}>
                  <input 
                    id="droneIp"
                    type="text" 
                    className="form-input" 
                    value={ipAddress}
                    onChange={(e) => setIpAddress(e.target.value)}
                    placeholder="192.168.1.10"
                    style={{ flex: 1, border: '1px solid var(--border-strong)', background: 'var(--bg-elevated)' }}
                  />
                  <button 
                    className="btn btn-primary" 
                    onClick={handleSaveIp}
                    disabled={isSaving || !ipAddress}
                    style={{ whiteSpace: 'nowrap' }}
                  >
                    {isSaving ? 'Linking...' : <><Save size={16} /> Bind IP</>}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Sidebar Columns */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          {/* Battery Status */}
          <div className="card" style={{ padding: '24px', position: 'relative', overflow: 'hidden' }}>
            <div style={{ position: 'absolute', right: '-20px', top: '-20px', opacity: 0.05, transform: 'rotate(15deg)' }}>
              <Battery size={150} />
            </div>
            <h2 style={{ fontSize: '1.1rem', marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Zap size={20} color={batteryLevel > 20 ? '#10b981' : '#ef4444'} />
              Power Core
            </h2>
            
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', margin: '10px 0 20px' }}>
              <div style={{ fontSize: '4rem', fontWeight: '800', color: batteryLevel > 20 ? 'var(--text-primary)' : '#ef4444', lineHeight: 1 }}>
                {batteryLevel}%
              </div>
              <p style={{ color: 'var(--text-muted)', marginTop: '8px', fontSize: '0.9rem' }}>
                Est. Flight Time: {Math.floor((batteryLevel / 100) * 35)} mins
              </p>
            </div>
            
            <div style={{ width: '100%', backgroundColor: 'var(--bg-elevated)', borderRadius: '12px', height: '24px', overflow: 'hidden', border: '1px solid var(--border-subtle)', boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.1)' }}>
              <div 
                style={{ 
                  height: '100%', 
                  width: `${batteryLevel}%`, 
                  background: batteryLevel > 20 ? 'linear-gradient(90deg, #34d399, #10b981)' : 'linear-gradient(90deg, #f87171, #ef4444)',
                  transition: 'width 1s ease-in-out',
                  position: 'relative'
                }} 
              >
                <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, background: 'linear-gradient(45deg, rgba(255,255,255,0.2) 25%, transparent 25%, transparent 50%, rgba(255,255,255,0.2) 50%, rgba(255,255,255,0.2) 75%, transparent 75%, transparent)', backgroundSize: '20px 20px', animation: 'move 1s linear infinite' }} />
              </div>
            </div>
          </div>

          {/* Telemetry Panel */}
          <div className="card" style={{ padding: '24px' }}>
            <h2 style={{ fontSize: '1.1rem', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Activity size={20} color="#3b82f6" />
              Flight Telemetry
            </h2>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ padding: '16px', background: 'var(--bg-elevated)', borderRadius: '12px', border: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-secondary)' }}>
                  <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: 'rgba(59,130,246,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Plane size={16} color="#3b82f6" />
                  </div>
                  <span style={{ fontWeight: '500' }}>Mode</span>
                </div>
                <div style={{ fontWeight: '700', color: 'var(--text-primary)' }}>{flightMode}</div>
              </div>

              <div style={{ padding: '16px', background: 'var(--bg-elevated)', borderRadius: '12px', border: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-secondary)' }}>
                  <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: 'rgba(16,185,129,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <MapPin size={16} color="#10b981" />
                  </div>
                  <span style={{ fontWeight: '500' }}>GPS Status</span>
                </div>
                <div style={{ fontWeight: '700', color: '#10b981' }}>3D Fix (12 Sats)</div>
              </div>
              
              <div style={{ padding: '16px', background: 'var(--bg-elevated)', borderRadius: '12px', border: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-secondary)' }}>
                  <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: 'rgba(245,158,11,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Camera size={16} color="#f59e0b" />
                  </div>
                  <span style={{ fontWeight: '500' }}>Gimbal</span>
                </div>
                <div style={{ fontWeight: '700', color: 'var(--text-primary)' }}>Stabilized (-15°)</div>
              </div>
            </div>
          </div>
          
        </div>
        
      </div>
      
      <style>{`
        @keyframes move {
          0% { background-position: 0 0; }
          100% { background-position: 20px 20px; }
        }
      `}</style>
    </div>
  )
}
