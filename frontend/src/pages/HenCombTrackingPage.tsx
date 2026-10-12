import React, { useState, useEffect, useRef } from 'react'
import { Camera, Upload, RefreshCw, Play, Pause, Layers } from 'lucide-react'

export default function HenCombTrackingPage() {
  const [streamMode, setStreamMode] = useState<'camera' | 'video' | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [totalCount, setTotalCount] = useState(0)
  const [visibleCount, setVisibleCount] = useState(0)
  const [aiFps, setAiFps] = useState<number | null>(null)
  const [isPlaying, setIsPlaying] = useState(true)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const overlayRef = useRef<HTMLCanvasElement | null>(null)
  const captureRef = useRef<HTMLCanvasElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const animationIdRef = useRef<number | null>(null)

  const runningRef = useRef(false)
  const sendingRef = useRef(false)
  const frameNumberRef = useRef(0)
  const lastSendRef = useRef(0)

  const latestResultsRef = useRef<any[]>([])
  const latestResultTimeRef = useRef(0)
  const previousRef = useRef<any>({})
  const velocitiesRef = useRef<any>({})

  const SEND_FPS = 10
  const apiUrl = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

  useEffect(() => {
    captureRef.current = document.createElement('canvas')
    return () => {
      stopStream()
    }
  }, [])

  const resetLocal = () => {
    latestResultsRef.current = []
    latestResultTimeRef.current = 0
    previousRef.current = {}
    velocitiesRef.current = {}
    frameNumberRef.current = 0
    lastSendRef.current = 0
    setTotalCount(0)
    setVisibleCount(0)
    setAiFps(null)
    if (overlayRef.current) {
      const ctx = overlayRef.current.getContext('2d')
      ctx?.clearRect(0, 0, overlayRef.current.width, overlayRef.current.height)
    }
  }

  const resetAIBackend = async () => {
    try {
      await fetch(`${apiUrl}/api/tracker/reset`, { method: 'POST' })
    } catch (e) {}
  }

  const contentRect = () => {
    const video = videoRef.current
    if (!video) return { x: 0, y: 0, width: 0, height: 0 }
    const dw = video.clientWidth
    const dh = video.clientHeight
    const sw = video.videoWidth
    const sh = video.videoHeight
    if (!dw || !dh || !sw || !sh) return { x: 0, y: 0, width: dw, height: dh }

    const sourceRatio = sw / sh
    const displayRatio = dw / dh
    if (sourceRatio > displayRatio) {
      const width = dw
      const height = width / sourceRatio
      return { x: 0, y: (dh - height) / 2, width, height }
    }
    const height = dh
    const width = height * sourceRatio
    return { x: (dw - width) / 2, y: 0, width, height }
  }

  const handleVideoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    stopStream()
    resetLocal()
    setErrorMsg(null)
    setIsProcessing(true)

    try {
      await resetAIBackend()
      const url = URL.createObjectURL(file)

      setStreamMode('video')
      setIsPlaying(true)

      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = null
          videoRef.current.src = url
          videoRef.current.muted = true
          videoRef.current.controls = true
          videoRef.current.playbackRate = 1.0

          videoRef.current.onloadedmetadata = () => {
            if (videoRef.current && overlayRef.current) {
              overlayRef.current.width = videoRef.current.clientWidth
              overlayRef.current.height = videoRef.current.clientHeight
            }
            runningRef.current = true
            startLoop()
            videoRef.current?.play().catch(() => {})
          }

          videoRef.current.onplay = () => {
            runningRef.current = true
            setIsPlaying(true)
            startLoop()
          }

          videoRef.current.onpause = () => {
            setIsPlaying(false)
          }

          videoRef.current.onseeking = () => {
            if (videoRef.current && videoRef.current.currentTime < 0.5) {
              resetAIBackend()
              frameNumberRef.current = 0
            }
          }
        }
        setIsProcessing(false)
      }, 100)
    } catch (err: any) {
      setErrorMsg('Failed to load video: ' + err.message)
      setIsProcessing(false)
    }
  }

  const startLiveCamera = async () => {
    stopStream()
    resetLocal()
    setErrorMsg(null)
    setIsProcessing(true)

    try {
      await resetAIBackend()
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false
      })

      streamRef.current = stream
      setStreamMode('camera')
      setIsPlaying(true)

      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.controls = false
          videoRef.current.muted = true
          videoRef.current.src = ""
          videoRef.current.srcObject = stream

          videoRef.current.onloadedmetadata = () => {
            if (videoRef.current && overlayRef.current) {
              overlayRef.current.width = videoRef.current.clientWidth
              overlayRef.current.height = videoRef.current.clientHeight
            }
            videoRef.current?.play().catch(() => {})
            runningRef.current = true
            startLoop()
          }
        }
        setIsProcessing(false)
      }, 100)
    } catch (err: any) {
      setErrorMsg('Camera access denied or unavailable: ' + err.message + '. Please ensure webcam permissions are allowed.')
      setIsProcessing(false)
    }
  }

  const stopStream = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    runningRef.current = false
    if (animationIdRef.current) {
      cancelAnimationFrame(animationIdRef.current)
      animationIdRef.current = null
    }
    if (videoRef.current) {
      videoRef.current.pause()
      videoRef.current.srcObject = null
      videoRef.current.src = ""
    }
    setStreamMode(null)
    resetLocal()
  }

  const startLoop = () => {
    if (animationIdRef.current) cancelAnimationFrame(animationIdRef.current)

    const loop = (timestamp: number) => {
      if (!runningRef.current) return
      draw()

      const video = videoRef.current
      if (video && video.readyState >= 2 && !video.paused && !video.ended) {
        if (timestamp - lastSendRef.current >= 1000 / SEND_FPS) {
          lastSendRef.current = timestamp
          frameNumberRef.current++
          if (!sendingRef.current) {
            sendFrame(frameNumberRef.current)
          }
        }
      }
      animationIdRef.current = requestAnimationFrame(loop)
    }
    animationIdRef.current = requestAnimationFrame(loop)
  }

  const sendFrame = async (number: number) => {
    const video = videoRef.current
    const capture = captureRef.current
    if (sendingRef.current || !video || !video.videoWidth || !capture) return

    sendingRef.current = true

    try {
      capture.width = Math.min(1280, video.videoWidth)
      capture.height = Math.round(capture.width * (video.videoHeight / video.videoWidth))
      const ctx = capture.getContext('2d')
      ctx?.drawImage(video, 0, 0, capture.width, capture.height)

      const blob = await new Promise<Blob | null>(resolve => capture.toBlob(resolve, 'image/jpeg', 0.80))
      if (!blob) {
        sendingRef.current = false
        return
      }

      const form = new FormData()
      form.append('frame', blob, 'frame.jpg')
      form.append('frame_number', String(number))
      form.append('video_time', String(video.currentTime || 0))

      const response = await fetch(`${apiUrl}/api/tracker/live_frame`, {
        method: 'POST',
        body: form
      })
      const data = await response.json()
      if (data && data.success) {
        updateResults(data)
      }
    } catch (e) {
      // Ignore transient network hiccups
    } finally {
      sendingRef.current = false
    }
  }

  const updateResults = (data: any) => {
    const detections = data.detections || []
    const video_time = Number(data.video_time || 0)
    latestResultsRef.current = detections
    latestResultTimeRef.current = video_time

    setTotalCount(data.total_hens || 0)
    setVisibleCount(data.visible_hens || detections.length)
    if (data.ai_fps) setAiFps(data.ai_fps)

    const newPrevious: any = {}
    const newVelocities: any = {}

    for (const item of detections) {
      const number = item.hen_number
      const box = item.box
      const old = previousRef.current[number]
      let vx = 0
      let vy = 0

      if (old && video_time > old.time) {
        const dt = Math.max(0.001, video_time - old.time)
        const oldCX = (old.box[0] + old.box[2]) / 2
        const oldCY = (old.box[1] + old.box[3]) / 2
        const newCX = (box[0] + box[2]) / 2
        const newCY = (box[1] + box[3]) / 2
        vx = (newCX - oldCX) / dt
        vy = (newCY - oldCY) / dt
        vx = Math.max(-2500, Math.min(2500, vx))
        vy = Math.max(-2500, Math.min(2500, vy))
      }
      newPrevious[number] = { box, time: video_time }
      newVelocities[number] = { vx, vy }
    }
    previousRef.current = newPrevious
    velocitiesRef.current = newVelocities
  }

  const draw = () => {
    const video = videoRef.current
    const overlay = overlayRef.current
    if (!video || !overlay) return

    if (overlay.width !== video.clientWidth || overlay.height !== video.clientHeight) {
      overlay.width = video.clientWidth
      overlay.height = video.clientHeight
    }

    const ctx = overlay.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, overlay.width, overlay.height)

    const detections = latestResultsRef.current
    if (!detections.length || !video.videoWidth) return

    const rect = contentRect()
    const sx = rect.width / video.videoWidth
    const sy = rect.height / video.videoHeight
    const age = Math.min(0.50, Math.max(0, (video.currentTime || 0) - latestResultTimeRef.current))

    for (const item of detections) {
      let box = [...item.box]
      const velocity = velocitiesRef.current[item.hen_number]

      if (velocity && age > 0) {
        box[0] += velocity.vx * age
        box[1] += velocity.vy * age
        box[2] += velocity.vx * age
        box[3] += velocity.vy * age
      }

      const x = rect.x + box[0] * sx
      const y = rect.y + box[1] * sy
      const width = (box[2] - box[0]) * sx
      const height = (box[3] - box[1]) * sy

      if (width <= 0 || height <= 0) continue

      // High-visibility glowing comb box (Vibrant Crimson & Emerald)
      ctx.shadowColor = '#ef4444'
      ctx.shadowBlur = 8
      ctx.strokeStyle = '#ef4444'
      ctx.lineWidth = 3
      ctx.strokeRect(x, y, width, height)
      ctx.shadowBlur = 0

      // Bounding box badge
      const label = `COMB #${item.hen_number}`
      ctx.font = 'bold 13px system-ui, sans-serif'
      const textWidth = ctx.measureText(label).width
      const labelY = Math.max(0, y - 22)

      ctx.fillStyle = 'rgba(239, 68, 68, 0.95)'
      ctx.fillRect(x, labelY, textWidth + 12, 20)

      ctx.fillStyle = '#ffffff'
      ctx.fillText(label, x + 6, labelY + 15)
    }
  }

  return (
    <div style={{ maxWidth: 1050, margin: '0 auto', padding: '24px 20px' }}>
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 16px', borderRadius: 20, background: 'rgba(239, 68, 68, 0.12)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#ef4444', fontSize: '0.85rem', fontWeight: 700, marginBottom: 12 }}>
          <Layers size={14} /> AI HEN COMB DETECTION & OPTICAL TRACKING
        </div>
        <h2 style={{ fontSize: '2.2rem', fontWeight: 800, margin: '0 0 8px', color: '#f8fafc', letterSpacing: '-0.5px' }}>
          Hen Comb AI Tracking
        </h2>
        <p style={{ color: '#94a3b8', margin: 0, fontSize: '1.05rem' }}>
          Real-time hen comb recognition, optical head tracking, and count verification across both cloud (Render) and local environments.
        </p>
      </div>

      {errorMsg && (
        <div style={{ padding: '16px 20px', background: 'rgba(239,68,68,0.1)', borderLeft: '4px solid #ef4444', borderRadius: 8, color: '#fca5a5', marginBottom: 24, fontSize: '0.95rem' }}>
          {errorMsg}
        </div>
      )}

      {!streamMode ? (
        <div className="card" style={{ padding: '48px 24px', display: 'flex', flexDirection: 'column', alignItems: 'center', background: 'rgba(15, 23, 42, 0.6)', border: '1px solid rgba(148, 163, 184, 0.1)', borderRadius: 20 }}>
          <h3 style={{ fontSize: '1.3rem', fontWeight: 700, marginBottom: 32, color: '#f8fafc' }}>
            Choose Input Stream
          </h3>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 24, width: '100%', maxWidth: 720 }}>
            {/* Upload Video Card */}
            <div
              className="ref-mode-btn"
              onClick={() => { if (!isProcessing) fileInputRef.current?.click() }}
              style={{
                padding: '36px 24px',
                borderRadius: 16,
                border: '2px dashed rgba(16,185,129,0.4)',
                background: 'rgba(16,185,129,0.05)',
                cursor: isProcessing ? 'wait' : 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 16,
                transition: 'all 0.25s ease'
              }}
            >
              <div style={{ width: 68, height: 68, borderRadius: '50%', background: 'linear-gradient(135deg,#10b981,#059669)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 8px 20px rgba(16,185,129,0.35)' }}>
                {isProcessing ? <RefreshCw className="animate-spin" size={32} color="white" /> : <Upload size={32} color="white" />}
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#f8fafc' }}>
                  {isProcessing ? 'Loading Video...' : 'Upload Video File'}
                </div>
                <div style={{ fontSize: '0.88rem', color: '#94a3b8', marginTop: 6, lineHeight: 1.4 }}>
                  MP4, WebM or MOV video. Plays instantly at smooth 1.0x normal speed with real-time AI comb tracking.
                </div>
              </div>
            </div>
            <input type="file" ref={fileInputRef} onChange={handleVideoUpload} accept="video/mp4,video/x-m4v,video/*" style={{ display: 'none' }} />

            {/* Live Camera Card */}
            <div
              className="ref-mode-btn"
              onClick={() => { if (!isProcessing) startLiveCamera() }}
              style={{
                padding: '36px 24px',
                borderRadius: 16,
                border: '2px solid rgba(59,130,246,0.4)',
                background: 'rgba(59,130,246,0.06)',
                cursor: isProcessing ? 'wait' : 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 16,
                transition: 'all 0.25s ease'
              }}
            >
              <div style={{ width: 68, height: 68, borderRadius: '50%', background: 'linear-gradient(135deg,#3b82f6,#1d4ed8)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 8px 20px rgba(59,130,246,0.35)' }}>
                {isProcessing ? <RefreshCw className="animate-spin" size={32} color="white" /> : <Camera size={32} color="white" />}
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#f8fafc' }}>
                  Live Camera (Webcam)
                </div>
                <div style={{ fontSize: '0.88rem', color: '#94a3b8', marginTop: 6, lineHeight: 1.4 }}>
                  Connects directly to your device camera (Laptop or Mobile) for live real-time hen comb detection.
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: 20, background: 'rgba(15, 23, 42, 0.7)', border: '1px solid rgba(148, 163, 184, 0.1)', borderRadius: 20 }}>
          {/* Top Bar with Live Stats */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 14, height: 14, borderRadius: '50%', background: '#ef4444', animation: 'live-pulse 1.2s infinite', boxShadow: '0 0 10px #ef4444' }} />
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f8fafc', margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                {streamMode === 'camera' ? 'LIVE CAMERA AI FEED' : 'AI VIDEO TRACKING (NORMAL SPEED)'}
              </h3>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <div style={{ padding: '8px 16px', background: 'rgba(16,185,129,0.12)', border: '1px solid rgba(16,185,129,0.4)', borderRadius: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: '0.85rem', color: '#94a3b8', fontWeight: 600 }}>Total Hens:</span>
                <span style={{ fontSize: '1.4rem', color: '#10b981', fontWeight: 800 }}>{totalCount}</span>
              </div>

              <div style={{ padding: '8px 16px', background: 'rgba(59,130,246,0.12)', border: '1px solid rgba(59,130,246,0.4)', borderRadius: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: '0.85rem', color: '#94a3b8', fontWeight: 600 }}>Visible:</span>
                <span style={{ fontSize: '1.4rem', color: '#60a5fa', fontWeight: 800 }}>{visibleCount}</span>
              </div>

              {aiFps && (
                <div style={{ padding: '8px 14px', background: 'rgba(148,163,184,0.1)', border: '1px solid rgba(148,163,184,0.25)', borderRadius: 12, color: '#94a3b8', fontSize: '0.85rem', fontWeight: 600 }}>
                  AI: {aiFps} FPS
                </div>
              )}

              <button
                onClick={stopStream}
                style={{ padding: '9px 20px', background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.4)', borderRadius: 10, color: '#ef4444', cursor: 'pointer', fontWeight: 600, fontSize: '0.9rem', transition: 'all 0.2s' }}
              >
                Close Stream
              </button>
            </div>
          </div>

          {/* Video & Canvas Overlay Viewport */}
          <div style={{ position: 'relative', borderRadius: 16, overflow: 'hidden', border: '2px solid rgba(239,68,68,0.3)', background: '#000', display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 450 }}>
            <video
              ref={videoRef}
              playsInline
              style={{ display: 'block', width: '100%', maxHeight: '72vh', objectFit: 'contain' }}
            />
            <canvas
              ref={overlayRef}
              style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
            />
          </div>
        </div>
      )}

      <style>{`
        @keyframes live-pulse { 0%,100% { opacity:1; box-shadow: 0 0 8px #ef4444; } 50% { opacity:0.4; box-shadow: 0 0 18px #ef4444; } }
        .ref-mode-btn:hover { transform: translateY(-4px); box-shadow: 0 12px 28px rgba(0,0,0,0.4) !important; }
        .animate-spin { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}