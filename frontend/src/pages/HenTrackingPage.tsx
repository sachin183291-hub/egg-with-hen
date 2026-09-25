import { useState, useEffect, useRef } from 'react'
import { Activity, UploadCloud, Video, RefreshCw, Layers, CheckCircle2 } from 'lucide-react'
import { trackerApi } from '../services/api'
import toast from 'react-hot-toast'

export default function HenTrackingPage() {
  const [jobId, setJobId]                   = useState<string | null>(null)
  const [isProcessing, setIsProcessing]     = useState(false)
  const [isDone, setIsDone]                 = useState(false)
  const [wsFrameBase64, setWsFrameBase64]   = useState<string | null>(null)
  const [visibleHens, setVisibleHens]       = useState(0)
  const [totalHens, setTotalHens]           = useState(0)
  const [finalTotal, setFinalTotal]         = useState<number | null>(null)
  const [progress, setProgress]             = useState(0)
  const [error, setError]                   = useState<string | null>(null)
  
  const [isLiveMode, setIsLiveMode]         = useState(false)
  const [cameraError, setCameraError]       = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const latestTotalRef = useRef<number>(0)
  const latestVisibleRef = useRef<number>(0)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const liveIntervalRef = useRef<number | null>(null)

  useEffect(() => { return () => { wsRef.current?.close() } }, [])

  const reset = () => {
    if (liveIntervalRef.current) clearInterval(liveIntervalRef.current)
    if (videoRef.current && videoRef.current.srcObject) {
      const stream = videoRef.current.srcObject as MediaStream
      stream.getTracks().forEach(t => t.stop())
      videoRef.current.srcObject = null
    }
    wsRef.current?.close()
    wsRef.current = null
    latestTotalRef.current = 0
    latestVisibleRef.current = 0
    setJobId(null)
    setIsProcessing(false)
    setIsDone(false)
    setWsFrameBase64(null)
    setVisibleHens(0)
    setTotalHens(0)
    setFinalTotal(null)
    setProgress(0)
    setError(null)
    setIsLiveMode(false)
    setCameraError(null)
  }

  const handleVideoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (!file.type.includes('video') && !file.name.match(/\.(mp4|avi|mov|webm)$/i)) {
      toast.error('Please upload a valid video file.')
      return
    }

    reset()
    setIsProcessing(true)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await trackerApi.upload(formData)
      const { job_id } = response.data
      setJobId(job_id)

      // WebSocket — backend streams annotated frames at exactly video FPS
      let wsUrl: string
      const apiUrl = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
      if (apiUrl) {
        const cleanUrl = apiUrl.replace(/^http/, 'ws')
        wsUrl = `${cleanUrl}/api/tracker/ws_stream/${job_id}`
      } else {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        wsUrl = `${wsProtocol}//${window.location.host}/api/tracker/ws_stream/${job_id}`
      }

      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.frame) setWsFrameBase64(data.frame)
          if (data.visible_hens !== undefined) {
            const vis = Number(data.visible_hens)
            setVisibleHens(vis)
            latestVisibleRef.current = vis
          }
          if (data.total_hens !== undefined) {
            const tot = Number(data.total_hens)
            setTotalHens(tot)
            latestTotalRef.current = tot
            if (data.done) {
              setFinalTotal(tot)
              setIsDone(true)
              setIsProcessing(false)
            }
          }
          if (data.progress !== undefined) setProgress(data.progress)
        } catch { /* ignore */ }
      }

      ws.onerror = () => {
        setError('Connection failed. Make sure the backend is running.')
        setIsProcessing(false)
      }

      ws.onclose = () => {
        setIsProcessing(false)
        setIsDone(true)
        // Capture final total when stream ends
        setFinalTotal(prev => (prev !== null && prev > 0) ? prev : latestTotalRef.current)
      }

    } catch (err: any) {
      setError(`Error: ${err.response?.data?.detail || err.message || 'Upload failed.'}`)
      setIsProcessing(false)
    }
  }

  const startLiveCamera = async () => {
    reset()
    setIsLiveMode(true)
    setIsProcessing(true)
    setCameraError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        videoRef.current.play()
      }

      let wsUrl: string
      const apiUrl = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
      if (apiUrl) {
        wsUrl = `${apiUrl.replace(/^http/, 'ws')}/api/tracker/ws_live`
      } else {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        wsUrl = `${wsProtocol}//${window.location.host}/api/tracker/ws_live`
      }

      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        liveIntervalRef.current = window.setInterval(() => {
          if (videoRef.current && canvasRef.current && ws.readyState === WebSocket.OPEN) {
            const ctx = canvasRef.current.getContext('2d')
            const vw = videoRef.current.videoWidth
            const vh = videoRef.current.videoHeight
            if (vw && vh) {
              canvasRef.current.width = vw
              canvasRef.current.height = vh
              ctx?.drawImage(videoRef.current, 0, 0, vw, vh)
              const b64 = canvasRef.current.toDataURL('image/jpeg', 0.6)
              ws.send(b64)
            }
          }
        }, 200) // 5 FPS
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.frame) setWsFrameBase64(data.frame)
          if (data.visible_hens !== undefined) {
             setVisibleHens(Number(data.visible_hens))
             latestVisibleRef.current = Number(data.visible_hens)
          }
          if (data.total_hens !== undefined) {
             setTotalHens(Number(data.total_hens))
             latestTotalRef.current = Number(data.total_hens)
          }
        } catch {}
      }

      ws.onerror = () => {
        setError('Live WS connection failed.')
        setIsProcessing(false)
      }

      ws.onclose = () => {
        setIsProcessing(false)
        setIsDone(true)
        setFinalTotal(prev => (prev !== null && prev > 0) ? prev : latestTotalRef.current)
      }

    } catch (err: any) {
      setCameraError('Failed to access camera: ' + err.message)
      setIsProcessing(false)
    }
  }

  // Keep finalTotal updated when tracking completes
  useEffect(() => {
    if (isDone && finalTotal === null) {
      setFinalTotal(latestTotalRef.current)
    }
  }, [isDone, finalTotal])

  return (
    <div
      className="page-container page-with-bg"
      style={{
        backgroundImage: "linear-gradient(rgba(255,255,255,0.65),rgba(255,255,255,0.65)),url('/thermal-bg.jpg')",
        backgroundSize: 'cover', backgroundPosition: 'center',
      }}
    >
      <header className="page-header" style={{ marginBottom: '32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="page-icon-wrapper" style={{ background: '#3b82f6' }}>
            <Layers size={20} color="white" />
          </div>
          <div>
            <h1 className="page-title">Live Hen Tracking</h1>
            <p className="page-subtitle">
              Upload a video — AI tracks every hen and streams it at normal video speed.
            </p>
          </div>
        </div>
      </header>

      <video ref={videoRef} playsInline muted style={{ display: 'none' }} />
      <canvas ref={canvasRef} style={{ display: 'none' }} />

      <div style={{ display: 'flex', flexDirection: 'row', gap: '24px', flexWrap: 'wrap' }}>

        {/* ── Left: Video Panel ──────────────────────────────────── */}
        <div className="card" style={{ flex: '1 1 60%', padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Video size={20} className="text-brand" />
            {isDone ? 'Tracking Complete' : (jobId || isLiveMode) ? 'ML Tracking — Live Stream' : 'Start Tracking'}
          </h3>

          {/* IDLE */}
          {!jobId && !isLiveMode && (
            <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
              <label style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                border: '2px dashed var(--border)', borderRadius: '12px', padding: '40px',
                cursor: 'pointer', background: 'rgba(255,255,255,0.02)', flex: '1 1 200px'
              }}>
                <UploadCloud size={52} color="var(--brand-400)" style={{ marginBottom: '16px' }} />
                <span style={{ fontSize: '1.1rem', fontWeight: '500', marginBottom: '8px' }}>Upload Video</span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textAlign: 'center' }}>
                  AI processes every frame.
                </span>
                <input type="file" accept="video/*" onChange={handleVideoUpload} style={{ display: 'none' }} />
              </label>

              <div onClick={startLiveCamera} style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                border: '2px dashed var(--border)', borderRadius: '12px', padding: '40px',
                cursor: 'pointer', background: 'rgba(255,255,255,0.02)', flex: '1 1 200px'
              }}>
                <Video size={52} color="#22c55e" style={{ marginBottom: '16px' }} />
                <span style={{ fontSize: '1.1rem', fontWeight: '500', marginBottom: '8px' }}>Live Camera</span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textAlign: 'center' }}>
                  Track hens live using your camera.
                </span>
              </div>
            </div>
          )}
          {cameraError && <p style={{ color: 'red' }}>{cameraError}</p>}

          {/* Waiting for first frame */}
          {(jobId || isLiveMode) && !wsFrameBase64 && !isDone && (
            <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px', padding: '60px', border: '2px dashed var(--border)', borderRadius: '12px' }}>
              <div style={{ width: '44px', height: '44px', borderRadius: '50%', border: '4px solid rgba(59,130,246,0.15)', borderTop: '4px solid #3b82f6', animation: 'spin 0.9s linear infinite' }} />
              <p style={{ color: 'var(--text-muted)', fontWeight: '500', textAlign: 'center' }}>
                🤖 AI processing first frame…<br />
                <span style={{ fontSize: '0.85rem' }}>Stream starting shortly</span>
              </p>
            </div>
          )}

          {/* Live stream */}
          {wsFrameBase64 && (
            <div className="fade-in" style={{ position: 'relative', borderRadius: '12px', overflow: 'hidden', border: `2px solid ${isDone ? '#22c55e' : '#3b82f6'}`, background: '#000' }}>
              <img
                src={`data:image/jpeg;base64,${wsFrameBase64}`}
                alt="ML Tracking"
                style={{ width: '100%', height: 'auto', maxHeight: '550px', objectFit: 'contain', display: 'block' }}
              />

              {/* Badge */}
              <div style={{
                position: 'absolute', top: '14px', left: '14px',
                background: isDone ? 'rgba(34,197,94,0.92)' : 'rgba(239,68,68,0.92)',
                color: '#fff', padding: '4px 12px', borderRadius: '4px', fontSize: '0.85rem',
                fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '6px',
              }}>
                {isDone
                  ? <><CheckCircle2 size={14} /> DONE</>
                  : <><div style={{ width: '8px', height: '8px', background: '#fff', borderRadius: '50%', animation: 'pulse-dot 1.5s infinite' }} /> LIVE</>
                }
              </div>

              {/* Progress bar (only while processing a file) */}
              {!isDone && jobId && (
                <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: '5px', background: 'rgba(0,0,0,0.3)' }}>
                  <div style={{ height: '5px', background: 'linear-gradient(90deg,#3b82f6,#06b6d4)', width: `${progress}%`, transition: 'width 0.4s ease' }} />
                </div>
              )}

              {/* Reset */}
              <button onClick={reset} style={{ position: 'absolute', top: '12px', right: '12px', background: 'rgba(0,0,0,0.6)', border: 'none', color: '#fff', borderRadius: '50%', width: '36px', height: '36px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
                <RefreshCw size={18} />
              </button>
            </div>
          )}

          {error && (
            <div style={{ padding: '14px', background: 'rgba(239,68,68,0.1)', color: '#ef4444', borderRadius: '10px' }}>
              {error}
            </div>
          )}
        </div>

        {/* ── Right: Stats Panel ────────────────────────────────── */}
        <div className="card" style={{ flex: '1 1 30%', padding: '24px', display: 'flex', flexDirection: 'column' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '24px' }}>
            <Activity size={20} className="text-brand" />
            {isDone ? 'Final Result' : 'Live Count'}
          </h3>

          {!isProcessing && !isDone && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, opacity: 0.5 }}>
              <Layers size={64} color="var(--text-muted)" style={{ marginBottom: '16px' }} />
              <p style={{ textAlign: 'center' }}>Upload a video or use live camera to see tracking counts.</p>
            </div>
          )}

          {(isProcessing || isDone) && (
            <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', flex: 1, gap: '24px' }}>

              {/* Total Hens */}
              <div style={{
                background: isDone ? 'rgba(34,197,94,0.07)' : 'rgba(59,130,246,0.05)',
                border: `1px solid ${isDone ? 'rgba(34,197,94,0.3)' : 'rgba(59,130,246,0.2)'}`,
                padding: '32px', borderRadius: '16px', textAlign: 'center',
              }}>
                <div style={{ fontSize: '1rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: '600', marginBottom: '12px' }}>
                  {isDone ? '✅ Final Total Hens' : 'Total Hens (Live)'}
                </div>
                <div style={{ fontSize: '6rem', fontWeight: '900', color: isDone ? '#22c55e' : '#3b82f6', lineHeight: 1 }}>
                  {isDone ? (finalTotal ?? totalHens) : totalHens}
                </div>
              </div>

              {/* Visible Hens (only while live) */}
              {!isDone && (
                <div style={{ background: 'rgba(255,255,255,0.5)', border: '1px solid var(--border)', padding: '24px', borderRadius: '16px', textAlign: 'center' }}>
                  <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: '600', marginBottom: '12px' }}>
                    Currently Visible
                  </div>
                  <div style={{ fontSize: '3rem', fontWeight: '700', color: 'var(--text-primary)', lineHeight: 1 }}>
                    {visibleHens}
                  </div>
                </div>
              )}

              {/* Progress (while processing a file) */}
              {!isDone && jobId && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                    <span>ML Processing</span>
                    <strong style={{ color: '#3b82f6' }}>{progress}%</strong>
                  </div>
                  <div style={{ background: 'rgba(0,0,0,0.08)', borderRadius: '999px', height: '8px' }}>
                    <div style={{ height: '8px', borderRadius: '999px', background: 'linear-gradient(90deg,#3b82f6,#06b6d4)', width: `${progress}%`, transition: 'width 0.5s ease' }} />
                  </div>
                </div>
              )}

              {/* Done message */}
              {isDone && (
                <div style={{ textAlign: 'center', padding: '16px', background: 'rgba(34,197,94,0.08)', borderRadius: '12px', color: '#22c55e', fontWeight: '600' }}>
                  <CheckCircle2 size={20} style={{ marginBottom: '8px' }} />
                  <div>Tracking complete!</div>
                  <div style={{ fontSize: '0.85rem', opacity: 0.8, marginTop: '4px' }}>
                    All frames tracked. Final count shown above.
                  </div>
                </div>
              )}

            </div>
          )}
        </div>
      </div>

      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes pulse-dot { 0%,100%{opacity:1;}50%{opacity:0.2;} }
        .fade-in { animation: fadeIn 0.4s ease forwards; }
        @keyframes fadeIn { from{opacity:0;transform:translateY(8px);}to{opacity:1;transform:translateY(0);} }
        @keyframes spin { to{transform:rotate(360deg);} }
      ` }} />
    </div>
  )
}
