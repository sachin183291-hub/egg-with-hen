import React, { useState, useRef } from 'react'
import { Camera, Upload, RefreshCw, FileVideo } from 'lucide-react'

export default function HenCombTrackingPage() {
  const [streamUrl, setStreamUrl] = useState<string | null>(null)
  const [streamMode, setStreamMode] = useState<'camera' | 'video' | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  
  const fileInputRef = useRef<HTMLInputElement>(null)
  const backendUrl = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '') + '/api/tracker'

  const handleVideoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    
    setIsProcessing(true)
    setErrorMsg(null)
    const formData = new FormData()
    formData.append('file', file)
    
    try {
      // 1. Upload video
      const uploadResp = await fetch(`${backendUrl}/upload`, { method: 'POST', body: formData })
      const uploadData = await uploadResp.json()
      
      if (uploadData.success) {
        // Instantly stream the uploaded video LIVE with AI detections
        setStreamUrl(`${backendUrl}/stream_video/${uploadData.filename}?t=${Date.now()}`)
        setStreamMode('camera') // Uses <img> tag for MJPEG streaming
      } else {
        setErrorMsg('Upload failed: ' + uploadData.error)
      }
    } catch (err: any) {
      setErrorMsg('Error: ' + err.message)
    } finally {
      setIsProcessing(false)
    }
  }

  const startLiveCamera = async () => {
    try {
      const resp = await fetch(`${backendUrl}/start_stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_source: 'camera' })
      })
      const data = await resp.json()
      if (data.success) {
        setStreamUrl(`${backendUrl}/stream_video?t=${Date.now()}`)
        setStreamMode('camera')
      } else {
        setErrorMsg('Failed to start camera: ' + data.error)
      }
    } catch (err: any) {
      setErrorMsg('Error starting camera: ' + err.message)
    }
  }

  const stopStream = async () => {
    setStreamUrl(null)
    setStreamMode(null)
    try {
      await fetch(`${backendUrl}/stop_stream`, { method: 'POST' })
    } catch (e) {}
  }

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '20px' }}>
      <h2 style={{ fontSize: '2rem', fontWeight: 800, marginBottom: 8, color: '#f8fafc', textAlign: 'center' }}>
        Live AI Streaming
      </h2>
      <p style={{ color: '#94a3b8', textAlign: 'center', marginBottom: 40, fontSize: '1.05rem' }}>
        Upload a video for ultra-smooth AI tracking at normal speed
      </p>

      {errorMsg && (
        <div style={{ padding: '16px 20px', background: 'rgba(239,68,68,0.1)', borderLeft: '4px solid #ef4444', borderRadius: 8, color: '#fca5a5', marginBottom: 20 }}>
          {errorMsg}
        </div>
      )}

      {!streamUrl ? (
        <div className="card" style={{ padding: '40px 20px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: 30, color: '#f8fafc' }}>Select Stream Source</h3>
          
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, width: '100%', maxWidth: 700 }}>
            <div 
              className="ref-mode-btn"
              onClick={() => { if(!isProcessing) fileInputRef.current?.click() }}
              style={{ padding: '36px 20px', borderRadius: 16, border: '2px dashed rgba(16,185,129,0.4)', background: 'rgba(16,185,129,0.05)', cursor: isProcessing ? 'wait' : 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, transition: 'all 0.3s' }}
            >
              <div style={{ width: 64, height: 64, borderRadius: '50%', background: 'linear-gradient(135deg,#10b981,#059669)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 8px 20px rgba(16,185,129,0.4)' }}>
                {isProcessing ? <RefreshCw className="animate-spin" size={30} color="white" /> : <Upload size={30} color="white" />}
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '1.15rem', fontWeight: 700, color: '#f8fafc' }}>
                  {isProcessing ? 'Upload Complete! AI is Processing...' : 'Upload Video'}
                </div>
                <div style={{ fontSize: '0.9rem', color: '#94a3b8', marginTop: 6 }}>
                  {isProcessing ? 'Please wait 1-2 minutes while AI tracks hens frame-by-frame' : 'Processes and plays at perfect normal speed'}
                </div>
              </div>
            </div>
            <input type="file" ref={fileInputRef} onChange={handleVideoUpload} accept="video/mp4,video/x-m4v,video/*" style={{ display: 'none' }} />

            <div 
              className="ref-mode-btn"
              onClick={startLiveCamera}
              style={{ padding: '36px 20px', borderRadius: 16, border: '2px solid rgba(59,130,246,0.4)', background: 'rgba(59,130,246,0.08)', cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, transition: 'all 0.3s' }}
            >
              <div style={{ width: 64, height: 64, borderRadius: '50%', background: 'linear-gradient(135deg,#3b82f6,#1d4ed8)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 8px 20px rgba(59,130,246,0.4)' }}>
                <Camera size={30} color="white" />
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '1.15rem', fontWeight: 700, color: '#f8fafc' }}>Live Camera</div>
                <div style={{ fontSize: '0.9rem', color: '#94a3b8', marginTop: 6 }}>Real-time streaming via webcam</div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 14, height: 14, borderRadius: '50%', background: streamMode === 'camera' ? '#ef4444' : '#10b981', animation: streamMode === 'camera' ? 'live-pulse 1.2s infinite' : 'none', boxShadow: streamMode === 'video' ? '0 0 10px #10b981' : 'none' }} />
              <h3 style={{ fontSize: '1.3rem', fontWeight: 700, color: streamMode === 'camera' ? '#ef4444' : '#10b981', margin: 0 }}>
                {streamMode === 'camera' ? 'LIVE CAMERA STREAM' : 'AI PROCESSED VIDEO'}
              </h3>
            </div>
            <button onClick={stopStream} style={{ padding: '10px 24px', background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.4)', borderRadius: 10, color: '#ef4444', cursor: 'pointer', fontWeight: 600 }}>
              Close
            </button>
          </div>
          
          <div style={{ borderRadius: 16, overflow: 'hidden', border: '2px solid rgba(16,185,129,0.25)', background: '#000', display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
            {streamMode === 'camera' ? (
              <img src={streamUrl} style={{ maxWidth: '100%', maxHeight: '75vh', objectFit: 'contain' }} alt="AI Stream" />
            ) : (
              <video src={streamUrl} controls autoPlay loop style={{ width: '100%', maxHeight: '75vh', objectFit: 'contain' }} />
            )}
          </div>
        </div>
      )}

      <style>{`
        @keyframes live-pulse { 0%,100% { opacity:1; box-shadow: 0 0 8px #ef4444; } 50% { opacity:0.5; box-shadow: 0 0 18px #ef4444; } }
        .ref-mode-btn:hover { transform: translateY(-4px); box-shadow: 0 12px 30px rgba(0,0,0,0.3) !important; }
        .animate-spin { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}