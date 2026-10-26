import { useState, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Activity, UploadCloud, Video, RefreshCw, Layers, Maximize2, Minimize2, X, Scan } from 'lucide-react'

export default function HenTrackingPage() {
  const [totalHens, setTotalHens] = useState(0)
  const [visibleHens, setVisibleHens] = useState(0)
  const [statusText, setStatusText] = useState('Select a video or start camera.')
  
  const [isLiveMode, setIsLiveMode] = useState(false)
  const [isCameraOpen, setIsCameraOpen] = useState(false)
  const [hasVideoUrl, setHasVideoUrl] = useState(false)
  const [facingMode, setFacingMode] = useState<'environment' | 'user'>('environment')
  const [isFullScreen, setIsFullScreen] = useState(false)
  const [fitMode, setFitMode] = useState<'cover' | 'contain'>('cover')

  const videoRef = useRef<HTMLVideoElement | null>(null)
  const overlayRef = useRef<HTMLCanvasElement | null>(null)
  const captureRef = useRef<HTMLCanvasElement | null>(null)
  
  const wsRef = useRef<WebSocket | null>(null)
  
  const runningRef = useRef(false)
  const sendingRef = useRef(false)
  const sendTimeoutRef = useRef<number | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const animationIdRef = useRef<number | null>(null)
  const frameNumberRef = useRef(0)
  const lastSendRef = useRef(0)
  const startTimeRef = useRef(0)
  
  const latestResultsRef = useRef<any[]>([])
  const latestResultTimeRef = useRef(0)
  const previousRef = useRef<any>({})
  const velocitiesRef = useRef<any>({})
  const animBoxesRef = useRef<Map<number, [number, number, number, number]>>(new Map())
  
  const SEND_FPS = 10

  useEffect(() => {
    captureRef.current = document.createElement('canvas')
    
    const handleResize = () => {
      if (videoRef.current && overlayRef.current) {
        overlayRef.current.width = videoRef.current.clientWidth
        overlayRef.current.height = videoRef.current.clientHeight
      }
    }
    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      stopCamera()
    }
  }, [])

  const resetLocal = () => {
    latestResultsRef.current = []
    latestResultTimeRef.current = 0
    previousRef.current = {}
    velocitiesRef.current = {}
    frameNumberRef.current = 0
    lastSendRef.current = 0
    setTotalHens(0)
    setVisibleHens(0)
    if (overlayRef.current) {
      const ctx = overlayRef.current.getContext('2d')
      ctx?.clearRect(0, 0, overlayRef.current.width, overlayRef.current.height)
    }
  }

  const resetAIBackend = async () => {
    try {
      const apiUrl = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
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
    stopCamera()
    resetLocal()
    setStatusText('Loading video locally...')
    
    try {
      await resetAIBackend()
      
      const url = URL.createObjectURL(file)
      if (videoRef.current) {
        videoRef.current.srcObject = null
        videoRef.current.controls = true
        videoRef.current.muted = true
        videoRef.current.onloadedmetadata = async () => {
          const video = videoRef.current
          if (!video) return
          if (overlayRef.current) {
            overlayRef.current.width = video.clientWidth
            overlayRef.current.height = video.clientHeight
          }
          // Play the video at normal 1.0x smooth speed!
          video.playbackRate = 1.0
          runningRef.current = true
          setHasVideoUrl(true)
          setStatusText('🟢 AI LIVE TRACKING (Normal Speed)')
          startLoop()
          try {
            await video.play()
          } catch (e) {
            console.log('Autoplay prevented, user can click play')
          }
        }

        videoRef.current.onplay = () => {
          if (!runningRef.current) {
            runningRef.current = true
            setStatusText('🟢 AI LIVE TRACKING (Normal Speed)')
            startLoop()
          }
        }

        videoRef.current.onseeking = () => {
          if (videoRef.current && videoRef.current.currentTime < 0.5) {
            resetAIBackend()
            frameNumberRef.current = 0
          }
        }

        videoRef.current.src = url
      }
    } catch (err: any) {
      setStatusText('❌ ' + err.message)
    }
  }

  const getBackCameraStream = async (desiredFacing: 'environment' | 'user' = 'environment') => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('Camera not supported in this browser. Ensure HTTPS is used.')
    }

    const isPortrait = window.innerHeight > window.innerWidth
    const targetW = isPortrait ? 720 : 1280
    const targetH = isPortrait ? 1280 : 720

    if (desiredFacing === 'environment') {
      // 1. Try finding rear/back camera via deviceId enumeration
      try {
        const devices = await navigator.mediaDevices.enumerateDevices()
        const videoDevices = devices.filter(d => d.kind === 'videoinput')
        const backDevice = videoDevices.find(d => /back|rear|environment|world|facing back|camera2 0/i.test(d.label))
          || (videoDevices.length > 1 ? videoDevices[videoDevices.length - 1] : null)

        if (backDevice && backDevice.deviceId) {
          try {
            return await navigator.mediaDevices.getUserMedia({
              video: {
                deviceId: { exact: backDevice.deviceId },
                width: { ideal: targetW },
                height: { ideal: targetH }
              },
              audio: false
            })
          } catch (e) {
            console.warn('getUserMedia exact deviceId failed:', e)
          }
        }
      } catch (e) {
        console.warn('enumerateDevices failed:', e)
      }

      // 2. Try exact environment constraint
      try {
        return await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { exact: 'environment' }, width: { ideal: targetW }, height: { ideal: targetH } },
          audio: false
        })
      } catch (e) {
        console.warn('exact environment facingMode failed:', e)
      }

      // 3. Fallback to ideal environment
      try {
        return await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment', width: { ideal: targetW }, height: { ideal: targetH } },
          audio: false
        })
      } catch (e) {
        console.warn('ideal environment failed:', e)
      }
    } else {
      // Front camera
      try {
        return await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'user', width: { ideal: targetW }, height: { ideal: targetH } },
          audio: false
        })
      } catch (e) {
        console.warn('user facingMode failed:', e)
      }
    }

    // 4. Fallback to generic video
    return await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
  }

  const startCamera = async (targetFacing: 'environment' | 'user' = 'environment') => {
    stopCamera()
    resetLocal()
    setIsLiveMode(true)
    setFacingMode(targetFacing)
    startTimeRef.current = Date.now()
    setStatusText('📷 Opening Back Camera...')
    try {
      await resetAIBackend()
      const stream = await getBackCameraStream(targetFacing)
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.controls = false
        videoRef.current.muted = true
        videoRef.current.onloadedmetadata = async () => {
          if (videoRef.current && overlayRef.current) {
            overlayRef.current.width = videoRef.current.clientWidth
            overlayRef.current.height = videoRef.current.clientHeight
          }
          try { await videoRef.current?.play() } catch (e) {}
          runningRef.current = true
          setIsCameraOpen(true)
          setStatusText('📷 CAMERA + AI LIVE')
          startLoop()
        }
        videoRef.current.srcObject = stream
        videoRef.current.src = ""
      }
    } catch (err: any) {
      setStatusText('❌ Camera error: ' + err.message)
    }
  }

  const handleFlipCamera = async () => {
    const nextFacing = facingMode === 'environment' ? 'user' : 'environment'
    setFacingMode(nextFacing)
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    try {
      const stream = await getBackCameraStream(nextFacing)
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play().catch(e => console.warn(e))
      }
    } catch (e: any) {
      console.warn('Flip camera failed:', e)
    }
  }

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    runningRef.current = false
    setIsLiveMode(false)
    setIsCameraOpen(false)
    setHasVideoUrl(false)
    if (animationIdRef.current) {
      cancelAnimationFrame(animationIdRef.current)
      animationIdRef.current = null
    }
    if (videoRef.current) {
      videoRef.current.pause()
      videoRef.current.srcObject = null
      videoRef.current.src = ""
    }
  }

  const resetAI = () => {
    stopCamera()
    resetLocal()
    resetAIBackend()
    setStatusText('🔄 Reset complete.')
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
      // Standardize capture to max 480px for ultra-low latency mobile upload (prevents video freeze)
      const maxDim = 480
      let cw = video.videoWidth
      let ch = video.videoHeight
      if (Math.max(cw, ch) > maxDim) {
        const s = maxDim / Math.max(cw, ch)
        cw = Math.round(cw * s)
        ch = Math.round(ch * s)
      }
      if (capture.width !== cw || capture.height !== ch) {
        capture.width = cw
        capture.height = ch
      }
      const ctx = capture.getContext('2d')
      ctx?.drawImage(video, 0, 0, cw, ch)
      
      const blob = await new Promise<Blob | null>(resolve => capture.toBlob(resolve, 'image/jpeg', 0.65))
      if (!blob) {
        sendingRef.current = false
        return
      }

      const curTime = isLiveMode ? (Date.now() - startTimeRef.current) / 1000 : (video.currentTime || 0)

      const form = new FormData()
      form.append('frame', blob, 'frame.jpg')
      form.append('frame_number', String(number))
      form.append('video_time', String(curTime))

      const apiUrl = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
      const response = await fetch(`${apiUrl}/api/tracker/live_frame`, {
        method: 'POST',
        body: form
      })
      const data = await response.json()
      if (data && data.success && !data.busy) {
        updateResults(data)
      }
    } catch (e) {
      console.warn(e)
    } finally {
      sendingRef.current = false
    }
  }

  const updateResults = (data: any) => {
    const rawDets = data.detections || []
    const fw = Number(data.frame_width) || 1
    const fh = Number(data.frame_height) || 1

    const detections = rawDets.map((item: any) => {
      const b = item.box || [0, 0, 0, 0]
      return {
        ...item,
        normBox: [
          b[0] / fw,
          b[1] / fh,
          b[2] / fw,
          b[3] / fh
        ]
      }
    })

    detections.sort((a: any, b: any) => (a.hen_number || 0) - (b.hen_number || 0))

    // Always update latest results: if a hen leaves or is no longer detected, it disappears immediately!
    latestResultsRef.current = detections
    latestResultTimeRef.current = performance.now()

    if (data.total_hens !== undefined) {
      setTotalHens(prev => Math.max(prev, Number(data.total_hens || 0), detections.length))
    }
    setVisibleHens(detections.length)
    setStatusText(`🟢 AI LIVE | UNIQUE HENS: ${Math.max(Number(data.total_hens || 0), detections.length)}`)

    // Clean up animBoxesRef for any hen that is no longer in detections
    const currentIds = new Set(detections.map((d: any) => Number(d.hen_number) || 0))
    for (const id of Array.from(animBoxesRef.current.keys())) {
      if (!currentIds.has(id)) {
        animBoxesRef.current.delete(id)
      }
    }
  }

  const draw = () => {
    const video = videoRef.current
    const overlay = overlayRef.current
    if (!video || !overlay || !video.videoWidth || !video.videoHeight) return

    const cw = overlay.clientWidth || window.innerWidth
    const ch = overlay.clientHeight || window.innerHeight

    if (overlay.width !== cw || overlay.height !== ch) {
      overlay.width = cw
      overlay.height = ch
    }

    const ctx = overlay.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, cw, ch)

    const detections = latestResultsRef.current || []
    if (performance.now() - latestResultTimeRef.current > 1200) {
      latestResultsRef.current = []
      animBoxesRef.current.clear()
    }

    const vw = video.videoWidth
    const vh = video.videoHeight

    const scale = fitMode === 'cover'
      ? Math.max(cw / vw, ch / vh)
      : Math.min(cw / vw, ch / vh)

    const renderedW = vw * scale
    const renderedH = vh * scale
    const offsetX = (cw - renderedW) / 2
    const offsetY = (ch - renderedH) / 2

    let liveCount = 0

    // Draw bounding boxes accurately on hen combs
    for (const item of detections) {
      const nb = item.normBox
      if (!nb || nb.length < 4) continue

      const targetX = offsetX + nb[0] * renderedW
      const targetY = offsetY + nb[1] * renderedH
      const targetW = (nb[2] - nb[0]) * renderedW
      const targetH = (nb[3] - nb[1]) * renderedH

      // Instant comb follow: exactly tracks rapid comb motion with zero lag
      const henId = Number(item.hen_number) || 0
      let x = targetX
      let y = targetY
      let width = targetW
      let height = targetH
      animBoxesRef.current.set(henId, [x, y, width, height])

      if (width <= 4 || height <= 4) continue
      // Head-only check: strictly reject oversized body boxes while capturing all head orientations (kutti box on head only)
      const wRatio = width / renderedW
      const hRatio = height / renderedH
      const isPortrait = renderedW < renderedH
      const maxWRatio = isPortrait ? 0.26 : 0.18
      const maxHRatio = isPortrait ? 0.26 : 0.22
      const maxAreaRatio = 0.030
      if (wRatio > maxWRatio || hRatio > maxHRatio || (wRatio * hRatio) > maxAreaRatio) continue
      const aspect = width / Math.max(height, 1)
      if (aspect < 0.30 || aspect > 1.85) continue
      if (x + width < 0 || x > cw || y + height < 0 || y > ch) continue

      // Tighten box to compact square-ish comb dimensions (kutti box on head only)
      if (width > height * 1.25) {
        const midX = x + width / 2
        width = height * 1.15
        x = midX - width / 2
      } else if (height > width * 1.35) {
        height = width * 1.25
      }
      
      liveCount++

      // Draw glowing green box
      ctx.strokeStyle = '#22c55e'
      ctx.lineWidth = 3
      ctx.shadowColor = 'rgba(34, 197, 94, 0.75)'
      ctx.shadowBlur = 8
      ctx.strokeRect(x, y, width, height)
      ctx.shadowBlur = 0

      // Viewfinder corner brackets
      const cornerLen = Math.min(10, width * 0.3, height * 0.3)
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(x, y + cornerLen); ctx.lineTo(x, y); ctx.lineTo(x + cornerLen, y)
      ctx.moveTo(x + width - cornerLen, y); ctx.lineTo(x + width, y); ctx.lineTo(x + width, y + cornerLen)
      ctx.moveTo(x, y + height - cornerLen); ctx.lineTo(x, y + height); ctx.lineTo(x + cornerLen, y + height)
      ctx.moveTo(x + width - cornerLen, y + height); ctx.lineTo(x + width, y + height); ctx.lineTo(x + width, y + height - cornerLen)
      ctx.stroke()

      // Draw label: Hen 1, Hen 2, Hen 3...
      const label = `Hen ${item.hen_number}`
      ctx.font = 'bold 13px Outfit, Arial, sans-serif'
      const textWidth = ctx.measureText(label).width
      const tagH = 20
      const tagY = Math.max(0, y - tagH - 2)
      
      ctx.fillStyle = '#22c55e'
      ctx.fillRect(x, tagY, textWidth + 8, tagH)
      
      ctx.fillStyle = '#000000'
      ctx.fillText(label, x + 4, tagY + 14)

      // Center tracking dot directly on comb
      const cx = x + width / 2
      const cy = y + height / 2
      ctx.beginPath()
      ctx.arc(cx, cy, 3.5, 0, Math.PI * 2)
      ctx.fillStyle = '#22c55e'
      ctx.fill()
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 1
      ctx.stroke()
    }

    // Draw HUD
    const hudW = Math.min(230, cw * 0.48)
    const hudH = 78
    const hudX = 14
    const hudY = 74

    ctx.fillStyle = 'rgba(0, 0, 0, 0.78)'
    if (typeof (ctx as any).roundRect === 'function') {
      (ctx as any).roundRect(hudX, hudY, hudW, hudH, 10)
      ctx.fill()
    } else {
      ctx.fillRect(hudX, hudY, hudW, hudH)
    }
    ctx.strokeStyle = 'rgba(34, 197, 94, 0.5)'
    ctx.lineWidth = 1.2
    ctx.stroke()

    const curTime = isLiveMode ? (Date.now() - startTimeRef.current) / 1000 : (video.currentTime || 0)
    ctx.font = 'bold 12px monospace'
    ctx.fillStyle = '#94a3b8'
    ctx.fillText(`TIME: ${curTime.toFixed(1)}s`, hudX + 12, hudY + 22)

    ctx.font = 'bold 13px sans-serif'
    ctx.fillStyle = '#22c55e'
    ctx.fillText(`VISIBLE HENS: ${liveCount}`, hudX + 12, hudY + 44)

    ctx.font = 'bold 15px sans-serif'
    ctx.fillStyle = '#00ffff'
    ctx.fillText(`TOTAL HENS: ${totalHens || liveCount}`, hudX + 12, hudY + 66)
  }

  return (
    <div className="page-container page-with-bg" style={{ backgroundImage: "linear-gradient(rgba(255,255,255,0.65),rgba(255,255,255,0.65)),url('/thermal-bg.jpg')", backgroundSize: 'cover', backgroundPosition: 'center' }}>
      <header className="page-header" style={{ marginBottom: '32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="page-icon-wrapper" style={{ background: '#3b82f6' }}>
            <Layers size={20} color="white" />
          </div>
          <div>
            <h1 className="page-title">Live Hen Tracking</h1>
            <p className="page-subtitle">Upload a video — AI tracks every hen and streams it at normal video speed.</p>
          </div>
        </div>
      </header>

      <div style={{ display: 'flex', flexDirection: 'row', gap: '24px', flexWrap: 'wrap' }}>
        <div className="card" style={{ flex: '1 1 60%', padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Video size={20} className="text-brand" />
            {(hasVideoUrl || isCameraOpen) ? 'ML Tracking — Live Stream' : 'Start Tracking'}
          </h3>

          {!hasVideoUrl && !isLiveMode && (
            <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
              <label style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', border: '2px dashed var(--border)', borderRadius: '12px', padding: '40px', cursor: 'pointer', background: 'rgba(255,255,255,0.02)', flex: '1 1 200px' }}>
                <UploadCloud size={52} color="var(--brand-400)" style={{ marginBottom: '16px' }} />
                <span style={{ fontSize: '1.1rem', fontWeight: '500', marginBottom: '8px' }}>Upload Video</span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textAlign: 'center' }}>AI processes every frame.</span>
                <input type="file" accept="video/*" onChange={handleVideoUpload} style={{ display: 'none' }} />
              </label>

              <div onClick={() => startCamera('environment')} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', border: '2px dashed var(--border)', borderRadius: '12px', padding: '40px', cursor: 'pointer', background: 'rgba(255,255,255,0.02)', flex: '1 1 200px' }}>
                <Video size={52} color="#22c55e" style={{ marginBottom: '16px' }} />
                <span style={{ fontSize: '1.1rem', fontWeight: '500', marginBottom: '8px' }}>Start Live Video</span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textAlign: 'center' }}>Track hens live using your camera.</span>
              </div>
            </div>
          )}

          {/* If Full Screen or Camera Open, render via Portal directly into document.body */}
          {(isFullScreen || isCameraOpen) && createPortal(
            <div
              style={{
                position: 'fixed',
                inset: 0,
                width: '100vw',
                height: '100dvh',
                zIndex: 2147483647,
                background: '#000',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden'
              }}
            >
              <video
                ref={videoRef}
                playsInline
                autoPlay
                muted
                style={{
                  position: 'absolute',
                  inset: 0,
                  width: '100%',
                  height: '100%',
                  objectFit: fitMode,
                  backgroundColor: '#000'
                }}
              />
              <canvas
                ref={overlayRef}
                style={{
                  position: 'absolute',
                  inset: 0,
                  width: '100%',
                  height: '100%',
                  pointerEvents: 'none',
                  zIndex: 2
                }}
              />

              {/* Viewfinder Controls Bar (Top-Right) */}
              <div style={{ position: 'absolute', top: '16px', right: '16px', display: 'flex', gap: '8px', zIndex: 10 }}>
                <button
                  type="button"
                  onClick={() => setFitMode(m => m === 'cover' ? 'contain' : 'cover')}
                  title={fitMode === 'cover' ? 'Fit (Letterbox)' : 'Fill (Full)'}
                  style={{ background: 'rgba(0,0,0,0.65)', border: '1px solid rgba(255,255,255,0.25)', color: '#fff', borderRadius: '20px', height: '38px', padding: '0 12px', display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontWeight: 700, fontSize: '0.8rem' }}
                >
                  <Scan size={15} />
                  <span>{fitMode === 'cover' ? 'FILL' : 'FIT'}</span>
                </button>

                {isCameraOpen && (
                  <button
                    type="button"
                    onClick={handleFlipCamera}
                    title="Switch Front/Back Camera"
                    style={{ background: 'rgba(0,0,0,0.65)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', borderRadius: '50%', width: '38px', height: '38px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
                  >
                    <RefreshCw size={18} />
                  </button>
                )}

                <button
                  type="button"
                  onClick={() => {
                    setIsFullScreen(false)
                    if (isCameraOpen) stopCamera()
                  }}
                  title="Close"
                  style={{ background: 'rgba(239,68,68,0.85)', border: 'none', color: '#fff', borderRadius: '50%', width: '38px', height: '38px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
                >
                  <X size={20} />
                </button>
              </div>
            </div>,
            document.body
          )}

          {/* Normal In-Card View for Local Video Upload (when not in fullscreen portal) */}
          {hasVideoUrl && !isFullScreen && (
            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                position: 'relative',
                borderRadius: '12px',
                overflow: 'hidden',
                border: `2px solid #3b82f6`,
                background: '#000',
                minHeight: 380
              }}
            >
              <div style={{ position: 'relative', display: 'inline-flex', justifyContent: 'center', alignItems: 'center', maxWidth: '100%', maxHeight: '550px', lineHeight: 0 }}>
                <video ref={videoRef} playsInline controls style={{ display: 'block', maxWidth: '100%', maxHeight: '550px', objectFit: 'contain' }} />
                <canvas ref={overlayRef} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' }} />
              </div>
              <div style={{ position: 'absolute', top: '12px', right: '12px', display: 'flex', gap: '8px', zIndex: 10 }}>
                <button
                  type="button"
                  onClick={() => setIsFullScreen(true)}
                  title="Full Screen"
                  style={{ background: 'rgba(0,0,0,0.65)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', borderRadius: '50%', width: '38px', height: '38px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
                >
                  <Maximize2 size={18} />
                </button>
                <button
                  type="button"
                  onClick={resetAI}
                  title="Reset / Stop"
                  style={{ background: 'rgba(239,68,68,0.7)', border: 'none', color: '#fff', borderRadius: '50%', width: '38px', height: '38px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
                >
                  <X size={18} />
                </button>
              </div>
            </div>
          )}

          {(hasVideoUrl || isCameraOpen) && (
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: '12px' }}>
              <button 
                onClick={resetAI} 
                style={{ background: '#ef4444', color: '#fff', padding: '12px 32px', borderRadius: '8px', border: 'none', fontWeight: 'bold', fontSize: '1.1rem', cursor: 'pointer', display: 'flex', gap: '8px', alignItems: 'center' }}
              >
                <RefreshCw size={20} />
                Stop Live Video
              </button>
            </div>
          )}

          <div style={{ padding: '14px', background: 'rgba(34,197,94,0.1)', color: '#22c55e', borderRadius: '10px' }}>
            {statusText}
          </div>
        </div>

        <div className="card" style={{ flex: '1 1 30%', padding: '24px', display: 'flex', flexDirection: 'column' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '24px' }}>
            <Activity size={20} className="text-brand" />
            Live Count
          </h3>
          
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', flex: 1, gap: '24px' }}>
            <div style={{ background: 'rgba(59,130,246,0.05)', border: '1px solid rgba(59,130,246,0.2)', padding: '32px', borderRadius: '16px', textAlign: 'center' }}>
              <div style={{ fontSize: '1rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: '600', marginBottom: '12px' }}>Total Hens (Live)</div>
              <div style={{ fontSize: '6rem', fontWeight: '900', color: '#3b82f6', lineHeight: 1 }}>{totalHens}</div>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.5)', border: '1px solid var(--border)', padding: '24px', borderRadius: '16px', textAlign: 'center' }}>
              <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: '600', marginBottom: '12px' }}>Currently Visible</div>
              <div style={{ fontSize: '3rem', fontWeight: '700', color: 'var(--text-primary)', lineHeight: 1 }}>{visibleHens}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
