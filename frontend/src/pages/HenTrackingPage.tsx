import { useState, useEffect, useRef } from 'react'
import { Activity, UploadCloud, Video, RefreshCw, Layers } from 'lucide-react'

export default function HenTrackingPage() {
  const [totalHens, setTotalHens] = useState(0)
  const [visibleHens, setVisibleHens] = useState(0)
  const [statusText, setStatusText] = useState('Select a video or start camera.')
  
  const [isLiveMode, setIsLiveMode] = useState(false)
  const [isCameraOpen, setIsCameraOpen] = useState(false)
  const [hasVideoUrl, setHasVideoUrl] = useState(false)

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
  
  const latestResultsRef = useRef<any[]>([])
  const latestResultTimeRef = useRef(0)
  const previousRef = useRef<any>({})
  const velocitiesRef = useRef<any>({})
  
  const SEND_FPS = 12

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
          if (videoRef.current && overlayRef.current) {
            overlayRef.current.width = videoRef.current.clientWidth
            overlayRef.current.height = videoRef.current.clientHeight
          }
          try { await videoRef.current?.play() } catch (e) {}
          runningRef.current = true
          setHasVideoUrl(true)
          setStatusText('🟢 VIDEO + AI LIVE')
          startLoop()
        }
        videoRef.current.src = url
      }
    } catch (err: any) {
      setStatusText('❌ ' + err.message)
    }
  }

  const startCamera = async () => {
    stopCamera()
    resetLocal()
    setIsLiveMode(true)
    setStatusText('📷 Opening Camera...')
    try {
      await resetAIBackend()
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false })
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
      capture.width = video.videoWidth
      capture.height = video.videoHeight
      const ctx = capture.getContext('2d')
      ctx?.drawImage(video, 0, 0, capture.width, capture.height)
      
      const blob = await new Promise<Blob | null>(resolve => capture.toBlob(resolve, 'image/jpeg', 0.82))
      if (!blob) {
        sendingRef.current = false
        return
      }

      const form = new FormData()
      form.append('frame', blob, 'frame.jpg')
      form.append('frame_number', String(number))
      form.append('video_time', String(video.currentTime || 0))

      const apiUrl = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
      const response = await fetch(`${apiUrl}/api/tracker/live_frame`, {
        method: 'POST',
        body: form
      })
      const data = await response.json()
      if (data.success) {
        updateResults(data)
      }
    } catch (e) {
      console.warn(e)
    } finally {
      sendingRef.current = false
    }
  }

  const updateResults = (data: any) => {
    const detections = data.detections || []
    const video_time = Number(data.video_time || 0)
    latestResultsRef.current = detections
    latestResultTimeRef.current = video_time
    
    setTotalHens(data.total_hens || 0)
    setVisibleHens(data.visible_hens || detections.length)
    setStatusText(`🟢 AI LIVE | UNIQUE HENS: ${data.total_hens || 0}`)

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

      ctx.strokeStyle = '#00ff00'
      ctx.lineWidth = item.predicted ? 2 : 3
      ctx.strokeRect(x, y, width, height)

      const label = `HEN ${item.hen_number}`
      ctx.font = 'bold 15px Arial'
      const textWidth = ctx.measureText(label).width
      const labelY = Math.max(0, y - 22)
      
      ctx.fillStyle = '#00ff00'
      ctx.fillRect(x, labelY, textWidth + 10, 22)
      ctx.fillStyle = '#000000'
      ctx.fillText(label, x + 5, labelY + 16)
    }
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

              <div onClick={startCamera} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', border: '2px dashed var(--border)', borderRadius: '12px', padding: '40px', cursor: 'pointer', background: 'rgba(255,255,255,0.02)', flex: '1 1 200px' }}>
                <Video size={52} color="#22c55e" style={{ marginBottom: '16px' }} />
                <span style={{ fontSize: '1.1rem', fontWeight: '500', marginBottom: '8px' }}>Live Camera</span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textAlign: 'center' }}>Track hens live using your camera.</span>
              </div>
            </div>
          )}

          <div style={{ display: (hasVideoUrl || isCameraOpen) ? 'block' : 'none', position: 'relative', borderRadius: '12px', overflow: 'hidden', border: `2px solid #3b82f6`, background: '#000' }}>
            <video ref={videoRef} playsInline style={{ display: 'block', width: '100%', height: 'auto', maxHeight: '550px', objectFit: 'contain' }} />
            <canvas ref={overlayRef} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' }} />
            
            <button onClick={resetAI} style={{ position: 'absolute', top: '12px', right: '12px', background: 'rgba(0,0,0,0.6)', border: 'none', color: '#fff', borderRadius: '50%', width: '36px', height: '36px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <RefreshCw size={18} />
            </button>
          </div>
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
